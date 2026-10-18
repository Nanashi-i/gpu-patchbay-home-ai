"""外部レビュー(Codex)の指摘への対策の、回帰テスト。"""
import http.client
import io
import json
import os
import re
import stat
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from helpers import EnvTest
from test_monitor_api import ApiTest

from patchbay.apps._common import sets
from patchbay.core import config, process, schema, secrets as secret_store
from patchbay.core.errors import HubError
from patchbay.core.machine_schema import MACHINE
from patchbay.core.store import save_json
from patchbay.downloads import engine, hf

ROOT = Path(__file__).resolve().parents[1]


class TokenTargetTest(EnvTest):
    """H1: トークンは、正規のドメインへの https にだけ付ける。"""

    def headers(self, url):
        with mock.patch.object(hf, "get_token", lambda kind: "DUMMY-" + kind):
            return hf.auth_headers(url)

    def test_only_real_hosts_over_https_get_the_token(self):
        for url in ("https://huggingface.co/a/b", "https://hf.co/a", "https://cdn-lfs.huggingface.co/x", "https://HuggingFace.CO/a",
                    "https://huggingface.co:443/a", "https://civitai.com/api/download/models/1"):
            self.assertIn("Authorization", self.headers(url), url)
        for url in ("https://evil-huggingface.co/a", "https://evilhf.co/a", "https://evilcivitai.com/a",
                    "https://huggingface.co.evil.com/a", "https://huggingface.co@evil.com/a", "http://huggingface.co/a",
                    "http://civitai.com/x", "file:///etc/passwd"):
            self.assertNotIn("Authorization", self.headers(url), url)

    def test_each_service_gets_its_own_token(self):
        self.assertEqual(self.headers("https://civitai.com/x")["Authorization"], "Bearer DUMMY-civitai")
        self.assertEqual(self.headers("https://huggingface.co/x")["Authorization"], "Bearer DUMMY-hf")

    def test_redirects_are_checked(self):
        redir = hf._Redir()
        req = urllib.request.Request("https://huggingface.co/a", headers={"Authorization": "Bearer X"})
        with self.assertRaises(urllib.error.HTTPError) as cm:                        # https → http は断る
            redir.redirect_request(req, io.BytesIO(), 302, "Found", {}, "http://huggingface.co/b")
        cm.exception.close()
        new = redir.redirect_request(req, None, 302, "Found", {}, "https://cdn.example.com/b")
        self.assertNotIn("Authorization", {k.title() for k in new.headers} | {k.title() for k in new.unredirected_hdrs})
        with self.assertRaises(HubError):                                            # 内部アドレスへの転送は断る
            redir.redirect_request(req, None, 302, "Found", {}, "https://127.0.0.1:8080/x")


class PrivateAddressTest(EnvTest):
    """M1: 内部のアドレスへは、既定で接続しない。"""

    def test_private_addresses_are_refused(self):
        for url in ("http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.5/x", "http://192.168.1.10:5000/x",
                    "http://169.254.169.254/latest/meta-data", "http://[::1]/x", "http://[::ffff:127.0.0.1]/x", "http://0.0.0.0/x"):
            with self.assertRaises(HubError, msg=url):
                hf.check_public_host(url)
        hf.check_public_host("http://8.8.8.8/x")

    def test_can_be_allowed_for_lan_use(self):
        config.CFG["allow_private_downloads"] = True
        hf.check_public_host("http://192.168.1.10/model.gguf")

    def test_inspect_and_enqueue_apply_it(self):
        with self.assertRaises(HubError):
            engine.inspect("http://127.0.0.1:5000/x.gguf", "llama")
        with self.assertRaises(HubError):
            engine.enqueue({"service": "llama", "url": "http://192.168.1.10/x.gguf", "files": [{"path": "x.gguf"}]})
        self.assertEqual(engine.DL, {})


class DownloadIntegrityTest(EnvTest):
    def setUp(self):
        super().setUp()
        engine.ALLOWED_SCHEMES = ("http", "https", "file")
        self.addCleanup(setattr, engine, "ALLOWED_SCHEMES", ("http", "https"))
        self.src = self.env.tmp / "src.safetensors"
        self.src.write_bytes(b"NEW")
        self.url = self.src.as_uri()
        while not engine.DL_Q.empty():
            engine.DL_Q.get()

    def item(self, name="a.safetensors"):
        return {"path": name, "category": "vae"}

    def run_all(self):
        while not engine.DL_Q.empty():
            engine.run_next()

    def test_part_symlink_is_not_followed(self):          # H2
        outside = self.env.tmp / "outside.txt"
        outside.write_text("ORIGINAL")
        part = self.env.models / "comfyui/vae/s.safetensors.part"
        part.parent.mkdir(parents=True)
        part.symlink_to(outside)
        engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item("s.safetensors")]})
        self.run_all()
        job = next(iter(engine.DL.values()))
        self.assertEqual(job["state"], "error")
        self.assertEqual(outside.read_text(), "ORIGINAL")
        self.assertFalse((self.env.models / "comfyui/vae/s.safetensors").exists())

    def test_same_destination_cannot_be_queued_twice(self):   # M3
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item(), self.item()]})
        self.assertEqual(engine.DL, {})
        engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item()]})
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item()]})
        self.assertEqual(len(engine.DL), 1)

    def test_file_that_appears_meanwhile_is_not_overwritten(self):   # M3
        engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item("late.safetensors")]})
        dest = self.env.models / "comfyui/vae/late.safetensors"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PRECIOUS")
        self.run_all()
        self.assertEqual(dest.read_bytes(), b"PRECIOUS")
        self.assertEqual(next(iter(engine.DL.values()))["state"], "error")

    def test_failed_request_changes_nothing(self):        # M5
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [], "new_set": "Ghost"})
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": "ftp://x/a.safetensors", "files": [self.item()], "new_set": "Ghost"})
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "a.safetensors", "category": "nope"}], "new_set": "Ghost"})
        self.assertEqual(sets.load_sets()["sets"], [])
        self.assertEqual(engine.DL, {})

    def test_one_broken_job_does_not_stop_the_next(self):   # M6
        (self.env.models / "comfyui/vae").parent.mkdir(parents=True, exist_ok=True)
        (self.env.models / "comfyui/vae").write_text("I am a file, not a folder")   # 保存先の親が作れない
        engine.enqueue({"service": "comfy", "url": self.url, "files": [self.item("a.safetensors")]})
        engine.enqueue({"service": "llama", "url": self.url, "files": [{"path": "b.gguf"}]})
        self.run_all()
        states = {j["name"]: j["state"] for j in engine.DL.values()}
        self.assertEqual(states, {"a.safetensors": "error", "b.gguf": "done"})
        with mock.patch.object(engine, "_download", side_effect=RuntimeError("boom")):   # 想定外の例外でも
            engine.DL["z"] = {"id": "z", "state": "queued"}
            engine.DL_Q.put(("z", "x", Path("y")))
            engine.run_next()
        self.assertEqual(engine.DL["z"]["state"], "error")

    def test_job_limit(self):
        with mock.patch.object(engine, "MAX_ACTIVE_JOBS", 2):
            with self.assertRaises(HubError):
                engine.enqueue({"service": "llama", "url": self.url, "files": [{"path": f"{i}.gguf"} for i in range(3)]})


class SetSafetyTest(EnvTest):
    def test_links_pointing_outside_the_model_area_are_not_exposed(self):     # M7
        outside = self.env.tmp / "elsewhere"
        outside.mkdir()
        (outside / "secret.safetensors").write_text("x")
        vae = self.env.models / "comfyui/vae"
        vae.mkdir(parents=True)
        (vae / "escape.safetensors").symlink_to(outside / "secret.safetensors")
        self.env.touch("comfyui/vae/ok.safetensors")
        sets.upsert_set({"id": "s", "name": "S", "service": "comfy", "files": {"vae": ["escape.safetensors", "ok.safetensors"]}})
        res = sets.build_view("comfy", "s")
        self.assertEqual((res["count"], res["missing"]), (1, ["vae/escape.safetensors"]))

    def test_links_between_services_still_work(self):
        self.env.touch("forge/VAE/shared.safetensors")
        (self.env.models / "comfyui/vae").mkdir(parents=True)
        (self.env.models / "comfyui/vae/shared.safetensors").symlink_to(self.env.models / "forge/VAE/shared.safetensors")
        sets.upsert_set({"id": "s", "name": "S", "service": "comfy", "files": {"vae": ["shared.safetensors"]}})
        self.assertEqual(sets.build_view("comfy", "s")["count"], 1)

    def test_folder_links_inside_the_view_are_unlinked_not_followed(self):
        outside = self.env.tmp / "elsewhere"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        vdir = self.env.models / ".view/comfyui"
        vdir.mkdir(parents=True)
        (vdir / "vae").symlink_to(outside, target_is_directory=True)
        self.env.touch("comfyui/vae/a.safetensors")
        sets.upsert_set({"id": "s", "name": "S", "service": "comfy", "files": {"vae": ["a.safetensors"]}})
        sets.build_view("comfy", "s")
        self.assertEqual((outside / "keep.txt").read_text(), "keep")
        self.assertEqual(list(outside.iterdir()), [outside / "keep.txt"])        # 外に、何も作っていない

    def test_view_dir_itself_as_a_link_is_refused(self):
        outside = self.env.tmp / "elsewhere"
        outside.mkdir()
        vdir = self.env.models / ".view/comfyui"
        vdir.parent.mkdir(parents=True)
        vdir.symlink_to(outside, target_is_directory=True)
        sets.upsert_set({"id": "s", "name": "S", "service": "comfy", "files": {}})
        with self.assertRaises(HubError):
            sets.build_view("comfy", "s")


class StateFilesTest(EnvTest):
    def test_secrets_file_gets_private_permissions_again(self):               # M11
        f = secret_store.secrets_file()
        f.write_text("{}")
        f.chmod(0o644)
        with mock.patch.object(secret_store, "_verify_hf", return_value=None):
            secret_store.set_token("hf", {"token": "DUMMY"})
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(f.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads(f.read_text()), {"@hf": "DUMMY"})

    def test_concurrent_writers_do_not_lose_updates(self):                    # M4
        def work(kind):
            for i in range(25):
                secret_store.set_token(kind, {"token": f"{kind}-{i}"})

        with mock.patch.object(secret_store, "_verify_hf", return_value=None):
            ts = [threading.Thread(target=work, args=(k,)) for k in ("hf", "civitai")]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(json.loads(secret_store.secrets_file().read_text()), {"@hf": "hf-24", "@civitai": "civitai-24"})

    def test_save_json_survives_simultaneous_writers(self):
        target = self.env.tmp / "x.json"
        errors = []

        def work(n):
            try:
                for i in range(30):
                    save_json(target, {"n": n, "i": i})
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        ts = [threading.Thread(target=work, args=(n,)) for n in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        json.loads(target.read_text())

    def test_concurrent_set_edits_are_all_kept(self):
        def work(n):
            for i in range(10):
                sets.upsert_set({"name": f"s{n}-{i}", "service": "comfy"})

        ts = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(sets.load_sets()["sets"]), 40)


class ProcessIdentityTest(EnvTest):
    def test_reused_pid_is_not_taken_for_the_service(self):                   # M8
        me = os.getpid()
        ticks = process._proc_start(me)
        self.assertTrue(ticks)
        self.assertTrue(process._same_process({"pid": me, "ticks": ticks}))
        self.assertFalse(process._same_process({"pid": me, "ticks": "1"}))     # 同じ PID でも、開始時刻が違えば別のプロセス
        self.assertTrue(process._same_process({"pid": me}))                    # 古い形式の記録は、PID の生存だけ
        self.assertFalse(process._same_process({"pid": 0}))

    def test_restore_drops_records_of_other_processes(self):
        save_json(process._run_file(), {"llama": {"pid": os.getpid(), "ticks": "1", "preset": "p"},
                                        "strata": {"pid": os.getpid(), "ticks": process._proc_start(os.getpid()), "preset": "q"}})
        process.RUN.clear()
        process.restore_run()
        self.assertEqual(list(process.RUN), ["strata"])

    def test_spawn_records_the_start_time(self):
        process.spawn("strata", ["sleep", "5"], self.env.tmp, dict(os.environ), {"preset": "p"})
        self.addCleanup(lambda: os.killpg(process.RUN["strata"]["pid"], 15))
        self.assertEqual(process.RUN["strata"]["ticks"], process._proc_start(process.RUN["strata"]["pid"]))


class SchemaTokenTest(EnvTest):
    def test_token_must_be_ascii(self):                                       # M9
        base = {"services": {}}
        self.assertEqual(schema.check(MACHINE, {**base, "token": "abc-XYZ_123"})[0], [])
        self.assertEqual(schema.check(MACHINE, {**base, "token": ""})[0], [])
        for bad in ("好きな合言葉", "has space", "tab\t"):
            self.assertTrue(schema.check(MACHINE, {**base, "token": bad})[0], bad)

    def test_allow_private_downloads_is_a_known_boolean(self):
        self.assertEqual(schema.check(MACHINE, {"services": {}, "allow_private_downloads": True}), ([], []))
        self.assertTrue(schema.check(MACHINE, {"services": {}, "allow_private_downloads": "yes"})[0])


class HandlerHardeningTest(ApiTest):
    def raw(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        c.putrequest(method, path)
        for k, v in (headers or {}).items():
            c.putheader(k, v)
        c.endheaders(body)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_non_ascii_token_header_is_a_401_not_a_crash(self):               # M9
        config.CFG["token"] = "secret"
        self.assertEqual(self.call("/api/state", headers={"X-Token": "sécret"})[0], 401)
        self.assertEqual(self.call("/api/state", token="secret")[0], 200)
        self.assertEqual(self.call("/api/state")[0], 401)

    def test_content_type_must_match_exactly(self):                           # L1
        for ctype in ("application/jsonBAD", "application/json2", "text/json"):
            self.assertEqual(self.call("/api/preset", raw=b"{}", headers={"Content-Type": ctype})[0], 415, ctype)
        self.assertNotEqual(self.call("/api/preset", raw=b'{"name":"x","service":"llama"}', headers={"Content-Type": "application/json; charset=utf-8"})[0], 415)

    def test_origin_scheme_must_be_http_or_https(self):                       # L1
        host = f"127.0.0.1:{self.srv.server_address[1]}"
        self.assertEqual(self.call("/api/state", headers={"Origin": f"ftp://{host}"})[0], 403)
        self.assertEqual(self.call("/api/state", headers={"Origin": f"https://{host}"})[0], 200)      # リバースプロキシ越し

    def test_body_size_limits(self):                                          # M2
        h = {"Content-Type": "application/json"}
        self.assertEqual(self.raw("POST", "/api/stop", {**h, "Content-Length": "-5"})[0], 400)
        self.assertEqual(self.raw("POST", "/api/stop", {**h, "Content-Length": "abc"})[0], 400)
        self.assertEqual(self.raw("POST", "/api/stop", {**h, "Content-Length": str(50 << 20)})[0], 413)   # 本文を読む前に、断る

    def test_log_reads_only_the_tail(self):
        from patchbay.api.routes import _tail
        f = self.env.tmp / "big.log"
        f.write_text("".join(f"line {i}\n" for i in range(400000)))              # 約 4 MB
        out = _tail(f, 3)
        self.assertEqual(out.splitlines(), ["line 399997", "line 399998", "line 399999"])
        self.assertEqual(_tail(self.env.tmp / "none.log"), "")


class ClientServerContractTest(unittest.TestCase):
    """画面が呼ぶ API の道筋が、サーバーに実在するか(名前の食い違い・消し忘れを防ぐ)。"""

    def test_every_api_path_used_by_the_web_exists(self):
        from patchbay.api.routes import GET, POST
        known = set(GET) | set(POST)
        used = set()
        for p in (ROOT / "web" / "js").glob("*.js"):
            used |= set(re.findall(r"['\"`](/api/[a-z/_]+)", p.read_text()))
        self.assertTrue(used)
        self.assertEqual(sorted(u for u in used if u not in known and not u.endswith("/")), [])

    def test_service_config_payload_types(self):
        """⚙ の保存の送り方(ポートは数値)が、サーバーの型と合うこと。"""
        spec = __import__("patchbay.api.routes", fromlist=["POST"]).POST["/api/service/config"][1]
        body = {"service": "llama", "dir": "~/x", "models_dir": "~/m", "enabled": True, "port": 2000}
        self.assertEqual(schema.check(spec, body)[0], [])
        self.assertTrue(schema.check(spec, {**body, "port": "2000"})[0])
        js = (ROOT / "web" / "js" / "script-panel.js").read_text()
        self.assertIn("Number(portText)", js)


if __name__ == "__main__":
    unittest.main()
