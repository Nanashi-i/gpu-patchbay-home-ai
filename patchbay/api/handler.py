"""HTTP の入口: 画面の配信 → 守りの確認 → 認証(token が設定されているときだけ)→ 入力の検証 → ルート表の呼び出し → JSON。

守りの確認(ブラウザ経由の攻撃への備え。ハブは、設定されたコマンドを実行するツールなので):
  - Host: IP アドレス・localhost・このPCのホスト名・allowed_hosts のどれかだけ(DNS リバインディング対策)
  - Origin: 付いていれば、Host と同じ(別のサイトの JavaScript から、API を呼べないようにする)
  - POST: Content-Type が application/json(別サイトの <form> や、単純なリクエストでは送れない形に限る)
"""
import hmac
import ipaddress
import json
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ..core import schema
from ..core.config import CFG
from ..core.errors import HubError
from . import static
from .routes import GET, POST


def _hostname_of(host_header):
    """Host ヘッダ('example:5000' / '[::1]:5000')から、ホスト名の部分を取り出す。"""
    h = (host_header or "").strip()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def host_allowed(host_header):
    name = _hostname_of(host_header).lower()
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True   # IP アドレスで開いているなら、DNS リバインディングではない
    except ValueError:
        pass
    mine = socket.gethostname().lower()
    allowed = {"localhost", mine, f"{mine}.local", *[h.lower() for h in CFG.get("allowed_hosts", [])]}
    return name in allowed


MAX_BODY = 4 << 20   # POST の本文の上限(4 MiB。プリセットやダウンロードの指定は、これよりずっと小さい)


class Handler(BaseHTTPRequestHandler):
    timeout = 30   # 本文を送ってこない接続を、いつまでも掴まない

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

    def authed(self):
        if not CFG.get("token"):   # token 未設定なら、認証なし
            return True
        # 文字コードに依存せず、バイト列で比べる(ASCII 以外が来ても、例外にしない)
        return hmac.compare_digest(self.headers.get("X-Token", "").encode("utf-8", "replace"), CFG["token"].encode("utf-8"))

    def _guard(self):
        """守りの確認。通らなければ、エラーを返して False。"""
        if not host_allowed(self.headers.get("Host")):
            self.send_json({"error": "この Host では使えません(machine.json の allowed_hosts に追加できます)"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin is not None:
            o = urllib.parse.urlparse(origin)
            # Host と同じ場所の http / https だけ(https は、リバースプロキシ越しの利用)
            if o.scheme not in ("http", "https") or o.netloc != self.headers.get("Host"):
                self.send_json({"error": "別のサイトからの要求は受け付けません"}, 403)
                return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        u = urllib.parse.urlparse(self.path)
        if not u.path.startswith("/api/"):   # 画面の部品(HTML / CSS / JS)は、認証なし
            res = static.serve(u.path)
            return self._send(*res) if res else self.send_json({"error": "not found"}, 404)
        if not self.authed():
            return self.send_json({"error": "unauthorized"}, 401)
        self._dispatch(GET, u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}, {})

    def do_POST(self):
        if not self._guard():
            return
        if not self.authed():
            return self.send_json({"error": "unauthorized"}, 401)
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.send_json({"error": "Content-Type は application/json にしてください"}, 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_json({"error": "Content-Length が正しくありません"}, 400)
        if n < 0:
            return self.send_json({"error": "Content-Length が正しくありません"}, 400)
        if n > MAX_BODY:
            return self.send_json({"error": f"本文が大きすぎます(最大 {MAX_BODY >> 20} MiB)"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.send_json({"error": "JSON を読めません"}, 400)
        self._dispatch(POST, urllib.parse.urlparse(self.path).path, {}, body)

    def _dispatch(self, table, path, query, body):
        route = table.get(path)
        if not route:
            return self.send_json({"error": "not found"}, 404)
        fn, spec = route
        try:
            schema.require(spec, query if table is GET else body, "入力")
            result = fn(query, body)
            self.send_json({"ok": True} if result is None else result)
        except HubError as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)
