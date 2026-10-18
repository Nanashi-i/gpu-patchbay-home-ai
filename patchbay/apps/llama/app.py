"""llama.cpp(llama-server): ハブが、引数を組み立てて起動する。

プリセットの項目: model ctx reasoning temp top_p top_k min_p ngl server_dir extra flags
  extra は、空白区切りのまま渡す(-ot の正規表現を壊さないため)。flags は、flags.py にあるものだけを受け付ける。
"""
import os
import re

from ...core.config import expand, models_dir, service, to_path
from ...core.errors import HubError
from ...core.schema import Int, ListOf, Num, OneOf, Str
from ..base import App, run_text
from .flags import llama_flags
from .models import scan_llama
from . import stats

_VER = {}


class LlamaApp(App):
    app_id = "llama"
    preset_fields = {
        "model": Str(1, 500), "ctx": Int(128, 4194304), "reasoning": Str(0, 20, pattern=r"auto|off|-?[0-9]{1,6}"),
        "temp": Num(0, 10), "top_p": Num(0, 1), "top_k": Int(0, 100000), "min_p": Num(0, 1),
        "ngl": OneOf(Int(0, 1000), Str(0, 10, pattern=r"auto|[0-9]{1,4}")),
        "server_dir": Str(1, 1000), "extra": Str(1, 4000), "flags": ListOf(Str(1, 100), 50),
    }

    def marker(self, name):
        m = service(name).get("marker")
        return m if m is not None else service(name).get("bin", "build/bin/llama-server")

    def build_command(self, name, p):
        svc = service(name)
        env = dict(os.environ)
        env["PATH"] = f"{os.path.expanduser('~')}/.local/bin:" + env.get("PATH", "")
        d = to_path(p.get("server_dir") or svc["dir"])
        binp = d / svc.get("bin", "build/bin/llama-server")
        if not binp.exists():
            raise HubError(f"llama-server が見つかりません: {binp}")
        model = to_path(p.get("model", ""), name)
        if not model.is_absolute():
            model = models_dir(name) / model
        if not model.is_file():
            raise HubError(f"モデルが見つかりません: {model}")
        cmd = [str(binp), "-m", str(model), "--host", "0.0.0.0", "--port", str(svc["port"]),
               "-ngl", str(p.get("ngl", 999)), "-c", str(p.get("ctx", 8192))]
        cmd += expand(svc.get("base_args", "")).split()
        for key, flag in (("temp", "--temp"), ("top_p", "--top-p"), ("top_k", "--top-k"), ("min_p", "--min-p")):
            if p.get(key) is not None:
                cmd += [flag, str(p[key])]
        r = str(p.get("reasoning", "auto"))
        if r == "off":
            cmd += ["-rea", "off"]
        elif r != "auto":
            cmd += ["--reasoning-budget", r]
        extra = expand(p.get("extra", ""), name).split()
        known = {}
        for f in llama_flags(svc):
            for a in [f["flag"]] + f.get("aliases", []):
                known[a] = f["flag"]
        for fl in p.get("flags") or []:
            if fl not in known:
                raise HubError(f"未対応のフラグです: {fl}")
            if not any(known.get(t) == fl for t in extra):   # 追加フラグ欄に同じものがあれば、重複させない
                cmd.append(fl)
        cmd += extra
        if svc.get("metrics", True) and "--metrics" not in cmd:   # モニターの「LLM 使用状況」用
            cmd.append("--metrics")
        return cmd, d, env

    def models(self, name):
        return {"service": name, "dir": str(models_dir(name)), "kind": "llama", "items": scan_llama()}

    def stats(self, name):
        return stats.collect(name)

    def version(self, name, preset=None):
        svc = service(name)
        d = to_path((preset or {}).get("server_dir") or svc["dir"])
        binp = d / svc.get("bin", "build/bin/llama-server")
        try:
            key = (str(binp), binp.stat().st_mtime)
        except OSError:
            return None
        if key not in _VER:
            m = re.search(r"version:\s*(\S+)\s*\(build (\d+), commit (\w+)\)", run_text([str(binp), "--version"], 20))
            _VER[key] = {"short": f"build {m.group(2)}",
                         "full": f"{m.group(1)} (build {m.group(2)}, commit {m.group(3)}) — {binp}"} if m else None
        return _VER[key]

    def extra_state(self, name):
        return {"flag_catalog": llama_flags(service(name))}
