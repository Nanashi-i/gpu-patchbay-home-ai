"""llama.cpp のモデル一覧: GGUF(分割ファイルは先頭だけ)、mmproj、使っているプリセット、削除コマンド。"""
import glob
import re
import shlex

from ...core.config import CFG, models_dir, to_path
from ...core.presets import load_presets
from .._common.files import rel_files


# ---------------------------------------------------------------- GPU / models
SPLIT = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$")


def scan_llama():
    root = models_dir("llama")
    used = {}
    for p in load_presets():
        if CFG["services"].get(p["service"], {}).get("type") == "llama" and p.get("model"):
            m = to_path(p["model"], p["service"])
            m = m if m.is_absolute() else models_dir(p["service"]) / m
            used.setdefault(str(m), []).append(p["name"])
    out = []
    if not root.is_dir():
        return out
    for f in rel_files(root, {".gguf"}):
        n = f.name
        if n.lower().startswith("mmproj"):
            continue
        m = SPLIT.search(n)
        if m and m.group(1) != "00001":
            continue
        files = [f]
        if m:
            files = sorted(f.parent.glob(glob.escape(n[:m.start()]) + f"-*-of-{m.group(2)}.gguf"))
        mm = sorted(f.parent.glob("mmproj*.gguf"))
        q = shlex.quote
        out.append({
            "path": str(f.relative_to(root)), "size": sum(x.stat().st_size for x in files),
            "shards": len(files), "used_by": used.get(str(f), []), "mmproj": [x.name for x in mm],
            "rm": "rm -v -- " + " ".join(q(str(x)) for x in files),
            "rm_all": "rm -v -- " + " ".join(q(str(x)) for x in files + mm) if mm else None,
            "rm_all_label": "mmproj込み",
        })
    return out
