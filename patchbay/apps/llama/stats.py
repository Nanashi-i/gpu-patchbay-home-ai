"""llama-server の /metrics(Prometheus 形式)から、モニターに出す指標を読む。

ハブが起動する llama-server には、--metrics を自動で付けている。付いていない(ハブの外から起動した)ときは、
{"metrics": False} を返す。動いていなければ None。
"""
import json
import time
import urllib.request

from ...core.config import service
from ...core.process import port_open

_NCTX = {}   # ポート -> (取得時刻, n_ctx)。/slots の n_ctx は、頻繁に変わらないので、60秒キャッシュ


def collect(name):
    port = service(name).get("port")
    if not port or not port_open(port):
        return None
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(base + "/metrics", timeout=1.5) as r:
            text = r.read().decode()
    except Exception:  # noqa: BLE001
        return {"metrics": False}
    m = {}
    for line in text.splitlines():
        if line.startswith("llamacpp:"):
            k, _, v = line.partition(" ")
            try:
                m[k[9:]] = float(v)
            except ValueError:
                pass
    if port not in _NCTX or _NCTX[port][0] < time.time() - 60:
        try:
            with urllib.request.urlopen(base + "/slots", timeout=1.5) as r:
                _NCTX[port] = (time.time(), sum(s.get("n_ctx", 0) for s in json.load(r)))
        except Exception:  # noqa: BLE001
            _NCTX[port] = (time.time(), 0)
    g = m.get
    return {"metrics": True,
            "prompt_tokens": int(g("prompt_tokens_total", 0)), "gen_tokens": int(g("tokens_predicted_total", 0)),
            "cached_tokens": int(g("prompt_tokens_cached_total", 0)),
            "prompt_seconds": round(g("prompt_seconds_total", 0), 3), "gen_seconds": round(g("tokens_predicted_seconds_total", 0), 3),
            "processing": int(g("requests_processing", 0)), "deferred": int(g("requests_deferred", 0)),
            "ctx_peak": int(g("n_tokens_max", 0)), "n_ctx": _NCTX[port][1]}
