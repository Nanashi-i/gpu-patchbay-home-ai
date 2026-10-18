import unittest

from test_monitor_api import ApiTest

from patchbay.core import config


class GuardTest(ApiTest):
    """ブラウザ経由の攻撃(別のサイトからの要求・DNS リバインディング・単純なリクエスト)への備え。"""

    def post(self, body=None, **kw):
        return self.call("/api/preset", body if body is not None else {"name": "x", "service": "llama"}, **kw)

    def test_post_requires_json_content_type(self):
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            code, _, _ = self.call("/api/preset", raw=b'{"name":"x","service":"llama"}', headers={"Content-Type": ctype})
            self.assertEqual(code, 415, ctype)                       # 別サイトの <form> や、事前確認のないリクエストでは、送れない形
        self.assertEqual(self.post()[0], 200)

    def test_foreign_origin_is_rejected(self):
        port = self.srv.server_address[1]
        for origin in ("https://evil.example", "http://evil.example:5000", f"http://localhost.evil.example:{port}", "null"):
            self.assertEqual(self.post(headers={"Origin": origin})[0], 403, origin)
            self.assertEqual(self.call("/api/state", headers={"Origin": origin})[0], 403, origin)
        self.assertEqual(self.post(headers={"Origin": f"http://127.0.0.1:{port}"})[0], 200)          # 同じ場所なら、通る

    def test_rebinding_hosts_are_rejected(self):
        for host in ("evil.example", "evil.example:5000", "127.0.0.1.evil.example", "localhost.evil.example"):
            self.assertEqual(self.call("/api/state", headers={"Host": host})[0], 403, host)
            self.assertEqual(self.call("/", headers={"Host": host})[0], 403, host)
        for host in ("localhost", "localhost:5000", "127.0.0.1:5000", "192.168.1.10:5000", "[::1]:5000"):
            self.assertEqual(self.call("/api/state", headers={"Host": host})[0], 200, host)

    def test_own_hostname_is_allowed_without_setting(self):
        import socket
        me = socket.gethostname()
        for host in (me, f"{me}:5000", f"{me}.local:5000"):
            self.assertEqual(self.call("/api/state", headers={"Host": host})[0], 200, host)

    def test_allowed_hosts_setting(self):
        self.assertEqual(self.call("/api/state", headers={"Host": "my-pc"})[0], 403)
        config.CFG["allowed_hosts"] = ["my-pc"]
        self.assertEqual(self.call("/api/state", headers={"Host": "my-pc:5000"})[0], 200)

    def test_bad_input_types_are_rejected_before_use(self):
        cases = [("/api/start", {"preset": ["x"]}), ("/api/start", {"preset": "a b"}), ("/api/stop", {"service": "../x"}),
                 ("/api/stop", {}), ("/api/preset/delete", {"id": "../../x"}), ("/api/service/config", {"service": "llama", "dir": 5}),
                 ("/api/set", {"name": "x", "service": "comfy", "files": {"vae": "notalist"}}),
                 ("/api/set", {"name": "x", "service": "comfy", "files": {"vae": [5]}}),
                 ("/api/token", {"kind": "evil", "token": "x"}), ("/api/secret", {"service": "strata", "key": 5}),
                 ("/api/dl/inspect", {"url": "file:///etc/passwd", "service": "llama"}),
                 ("/api/dl/start", {"service": "llama", "files": "a.gguf"}), ("/api/dl/start", {"service": "llama", "files": [{"path": 5}]})]
        for path, body in cases:
            code, _, data = self.call(path, body)
            self.assertEqual(code, 400, f"{path} {body} -> {code} {data[:80]}")

    def test_query_values_are_checked(self):
        self.assertEqual(self.call("/api/log?service=../etc/passwd")[0], 400)
        self.assertEqual(self.call("/api/monitor?since=abc")[0], 400)
        self.assertEqual(self.call("/api/models?service=../x")[0], 400)

    def test_oversized_and_control_characters_in_preset(self):
        self.assertEqual(self.post({"name": "x" * 200, "service": "llama"})[0], 400)
        self.assertEqual(self.post({"name": "x", "service": "llama", "extra": "-a b\n--evil"})[0], 400)
        self.assertEqual(self.post({"name": "x", "service": "llama", "extra": "a" * 5000})[0], 400)


if __name__ == "__main__":
    unittest.main()
