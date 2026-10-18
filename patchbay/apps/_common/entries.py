"""「フォルダ直下の項目」を一覧する、モデル置き場(Strata など、決まった種別のないもの)。"""
import glob
import shlex
from pathlib import Path

from ...core.config import models_dir, service, to_path
from .files import dir_size


def scan_entries(name):
    """直下の項目と、設定ファイル(refs_glob)からの参照を返す。削除はコマンドを見せるだけ。"""
    svc = service(name)
    root = models_dir(name)
    q = shlex.quote
    refs = {}
    if svc.get("refs_glob"):
        for cf in sorted(glob.glob(str(to_path(svc["dir"]) / svc["refs_glob"]))):
            try:
                refs[Path(cf).name] = Path(cf).read_text(errors="replace")
            except OSError:
                pass
    items = []
    if root.is_dir():
        for e in sorted(root.iterdir()):
            if e.name.startswith("."):
                continue
            isdir = e.is_dir()
            items.append({
                "name": e.name, "is_dir": isdir, "size": dir_size(e) if isdir else e.stat().st_size,
                "used_by": [n for n, t in refs.items() if f"/{e.name}/" in t or f"/{e.name}\"" in t],
                "rm": ("rm -rv -- " if isdir else "rm -v -- ") + q(str(e)), "rm_all": None, "rm_all_label": ""})
    return {"service": name, "dir": str(root), "kind": "entries", "items": items}
