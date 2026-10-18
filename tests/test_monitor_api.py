import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from helpers import EnvTest

from patchbay.apps.llama import stats as llama_stats
from patchbay.core import config
from patchbay.monitor import sampler, system


class FakeLlama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/metrics":
            body = "# HELP x\nllamacpp:prompt_tokens_total 27\nllamacpp:tokens_predicted_total 14\nllamacpp:prompt_seconds_total 0.5\n" \
                   "llamacpp:tokens_predicted_seconds_total 0.25\nllamacpp:n_tokens_max 40\nllamacpp:requests_processing 1\n"
        else:
            body = json.dumps([{"id": 0, "n_ctx": 8192}, {"id": 1, "n_ctx": 8192}])
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())


class LlamaStatsTest(EnvTest):
    def test_metrics_are_parsed_and_unavailable_is_none(self):
        self.assertIsNone(llama_stats.collect("llama"))                       # 動いていない
        srv = HTTPServer(("127.0.0.1", 0), FakeLlama)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        config.CFG["services"]["llama"]["port"] = srv.server_address[1]
        s = llama_stats.collect("llama")
        self.assertEqual((s["metrics"], s["prompt_tokens"], s["gen_tokens"], s["ctx_peak"], s["processing"]), (True, 27, 14, 40, 1))
        self.assertEqual(s["n_ctx"], 16384)                                    # スロットの n_ctx の合計


class SamplerTest(EnvTest):
    def test_sample_has_named_fields(self):
        sm = sampler.Sampler(interval=1, hours=0.01)
        sm.prime()
        time.sleep(0.05)
        s = sm.sample()
        for k in ("t", "cpu", "mem", "swap", "disk_read", "disk_write", "disk_used", "gpus", "apps"):
            self.assertIn(k, s)
        self.assertTrue(0 <= s["cpu"] <= 100 and s["mem"] > 0)
        self.assertIsInstance(s["gpus"], list)
        self.assertIn("pc", sm.meta)

    def test_snapshot_filters_by_time_and_history_is_bounded(self):
        sm = sampler.Sampler(interval=10, hours=1)                             # 1時間 / 10秒 = 360 点が上限
        for t in range(1, 401):
            sm.samples.append({"t": t})
        self.assertEqual(len(sm.samples), 360)
        self.assertEqual(sm.snapshot(0)["samples"][0]["t"], 41)                 # 古い点から捨てられる
        self.assertEqual([s["t"] for s in sm.snapshot(398)["samples"]], [399, 400])

    def test_cpu_times_and_meminfo_are_readable(self):
        total, idle = system.cpu_times()
        self.assertTrue(total >= idle > 0)
        self.assertGreater(system.meminfo()["MemTotal"], system.meminfo()["MemAvailable"] // 2)

    def test_pc_info(self):
        info = system.pc_info()
        self.assertTrue(info["hostname"] and info["kernel"])


class ApiTest(EnvTest):
    def setUp(self):
        super().setUp()
        from patchbay.server import create_server
        self.srv = create_server("127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        sm = sampler.Sampler(interval=5, hours=0.01)
        sm.samples.append({"t": 1.0})
        sampler.SAMPLER = sm

    def call(self, path, body=None, token=None, headers=None, raw=None):
        h = {"X-Token": token} if token else {}
        if body is not None or raw is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(self.base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers.get("Content-Type"), e.read()

    def jcall(self, path, body=None, token=None):
        code, _, data = self.call(path, body, token)
        return code, json.loads(data)

    def test_state_and_static(self):
        code, d = self.jcall("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(sorted(d["services"]), ["comfy", "forge", "llama", "strata"])
        self.assertEqual(self.call("/")[0], 200)
        self.assertEqual(self.call("/css/base.css")[1].split(";")[0], "text/css")
        self.assertEqual(self.call("/js/core.js")[1].split(";")[0], "text/javascript")
        themes = json.loads(self.call("/themes.json")[2])
        self.assertEqual(themes[0]["id"], "")                                      # デフォルトが先頭
        self.assertIn("dark", [t["id"] for t in themes])

    def test_static_cannot_escape_web_dir(self):
        for p in ("/../hub.py", "/css/../../hub.py", "/%2e%2e/hub.py", "/js/nothing.js", "/css/themes"):
            self.assertEqual(self.call(p)[0], 404, p)

    def test_token_protects_only_the_api(self):
        config.CFG["token"] = "secret"
        self.assertEqual(self.call("/api/state")[0], 401)
        self.assertEqual(self.call("/api/state", token="wrong")[0], 401)
        self.assertEqual(self.call("/api/state", token="secret")[0], 200)
        self.assertEqual(self.call("/api/preset", {"name": "x", "service": "llama"})[0], 401)
        self.assertEqual(self.call("/")[0], 200)                                   # 画面の部品は、認証なし

    def test_errors_map_to_http_codes(self):
        self.assertEqual(self.jcall("/api/nothing")[0], 404)
        code, d = self.jcall("/api/preset", {"name": "", "service": "llama"})
        self.assertEqual(code, 400)
        self.assertIn("error", d)
        self.assertEqual(self.call("/api/preset", raw=b"not json")[0], 400)
        self.assertEqual(self.call("/api/preset", raw=b"[1, 2]")[0], 400)          # JSON でも、オブジェクトでなければ拒否

    def test_preset_roundtrip_and_models_and_resolve(self):
        code, p = self.jcall("/api/preset", {"name": "T", "service": "llama", "model": "a.gguf", "ctx": 2048})
        self.assertEqual(code, 200)
        self.assertEqual([x["id"] for x in self.jcall("/api/state")[1]["presets"]], [p["id"]])
        self.env.touch("llama/a.gguf")
        items = self.jcall("/api/models?service=llama")[1]["items"]
        self.assertEqual(items[0]["used_by"], ["T"])
        self.assertEqual(self.jcall("/api/models?service=nothing")[0], 400)
        r = self.jcall("/api/resolve?service=llama&path=build/bin/llama-server")[1]       # 相対パスは、サービスのフォルダから
        self.assertTrue(r["exists"] and r["resolved"].startswith(str(self.env.apps / "llama.cpp")))
        self.assertFalse(self.jcall("/api/resolve?service=llama&path=nothing")[1]["exists"])
        self.assertEqual(self.jcall("/api/preset/delete", {"id": p["id"]})[1], {"ok": True})

    def test_monitor_route(self):
        code, d = self.jcall("/api/monitor?since=0")
        self.assertEqual((code, d["samples"]), (200, [{"t": 1.0}]))

    def test_service_config_saves_and_validates(self):
        self.assertEqual(self.jcall("/api/service/config", {"service": "llama", "port": 99999})[0], 400)
        self.assertEqual(self.jcall("/api/service/config", {"service": "llama", "port": "80"})[0], 400)      # 文字列は拒否
        self.assertEqual(self.jcall("/api/service/config", {"service": "llama", "port": 18999})[0], 200)
        self.assertEqual(json.loads(self.env.machine.read_text())["services"]["llama"]["port"], 18999)
        self.assertTrue((self.env.tmp / "machine.json.bak").exists())              # 1つ前の版
        self.assertEqual(config.CFG["services"]["llama"]["port"], 18999)           # 再起動なしで反映


if __name__ == "__main__":
    unittest.main()
