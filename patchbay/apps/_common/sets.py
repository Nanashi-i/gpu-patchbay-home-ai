"""モデルセット: ComfyUI / Forge で、ドロップダウンに出すモデルを絞るための、ファイルのまとまり。

保存先は sets.json:  { "common": {サービス: {種別: [パス]}}, "sets": [ {id, name, note, service, files} ] }
「共通」セットは、どのセットで起動しても足される。起動時に、選んだセットのファイルへのシンボリックリンクだけを集めた
「表示用フォルダ」を作り(build_view)、アプリがそのフォルダを見るように仕向ける。
"""
import os
import secrets
from pathlib import Path

from ...core.config import CFG, ROOTS, cat_dir, categories, to_path
from ...core.config import service as service_cfg
from ...core.errors import HubError
from ...core.store import file_lock, load_json, save_json

def load_sets():
    with file_lock:
        d = load_json(ROOTS.sets_file, {})
    d.setdefault("common", {})
    d.setdefault("sets", [])
    return d


def _save_sets(d):
    with file_lock:
        save_json(ROOTS.sets_file, d)


def _view_service(service):
    if not CFG["services"].get(service, {}).get("view"):
        raise HubError("このサービスはモデルセットに対応していません")


def _clean_files(service, files):
    out = {}
    for cat, paths in (files or {}).items():
        cat_dir(service, cat)  # 種別名の検証
        ps = []
        for p in paths:
            n = os.path.normpath(str(p))
            if n.startswith("..") or os.path.isabs(n):
                raise HubError(f"不正なパス: {p}")
            if n not in ps:
                ps.append(n)
        if ps:
            out[cat] = sorted(ps)
    return out


def get_set(service, set_id):
    for s in load_sets()["sets"]:
        if s["id"] == set_id and s["service"] == service:
            return s
    raise HubError("モデルセットが見つかりません")


def upsert_set(body):
    with file_lock:
        return _upsert_set(body)


def _upsert_set(body):
    service = body.get("service")
    _view_service(service)
    name = (body.get("name") or "").strip()
    if not name:
        raise HubError("セット名は必須です")
    d = load_sets()
    item = {"id": body.get("id") or f"set-{secrets.token_hex(3)}", "name": name, "note": (body.get("note") or "").strip(),
            "service": service, "files": _clean_files(service, body.get("files"))}
    for i, s in enumerate(d["sets"]):
        if s["id"] == item["id"]:
            d["sets"][i] = item
            break
    else:
        d["sets"].append(item)
    _save_sets(d)
    return item


def delete_set(set_id):
    with file_lock:
        d = load_sets()
        d["sets"] = [s for s in d["sets"] if s["id"] != set_id]
        _save_sets(d)


def set_common(service, files):
    _view_service(service)
    with file_lock:
        d = load_sets()
        d["common"][service] = _clean_files(service, files)
        _save_sets(d)


def add_to_set(service, set_id, cat, rel):
    with file_lock:
        d = load_sets()
        if set_id == "_common":
            target = d["common"].setdefault(service, {})
        else:
            target = next((s["files"] for s in d["sets"] if s["id"] == set_id), None)
            if target is None:
                return
        lst = target.setdefault(cat, [])
        if rel not in lst:
            lst.append(rel)
            lst.sort()
        _save_sets(d)


def _inside_models(path):
    """リンクを解決した先が、モデル置き場(models_root か、どれかのサービスの models_dir)の中か。
    サービス間の共有リンク(ComfyUI のモデルを Forge で使う、など)は、置き場の中どうしなので通る。"""
    real = Path(path).resolve()
    roots = [ROOTS.models.resolve(), *(to_path(s["models_dir"]).resolve() for s in CFG["services"].values())]
    return any(r == real or r in real.parents for r in roots)


def _clear_view(vdir):
    if vdir.is_symlink():
        raise HubError(f"表示用フォルダがリンクになっています。削除してから、やり直してください: {vdir}")
    if not vdir.exists():
        return
    for dp, dns, fns in os.walk(vdir, topdown=False):
        for fn in fns:
            p = Path(dp) / fn
            if not p.is_symlink():
                raise HubError(f"表示用フォルダに実ファイルがあります(手で置かないでください): {p}")
            p.unlink()
        for dn in dns:
            p = Path(dp) / dn
            if p.is_symlink():   # フォルダへのリンクは、辿らずに、リンクごと消す
                p.unlink()
                continue
            try:
                p.rmdir()
            except OSError:
                pass


def build_view(service, set_id):
    """選んだセット(+共通)のファイルへのリンクだけを集めた表示用フォルダを作り直す。
    戻り値: {name, count, missing[], view_dir}(set_id が空なら呼ばない)。"""
    st = get_set(service, set_id)
    vdir = to_path(service_cfg(service)["view"]["dir"])
    cats = categories(service)
    _clear_view(vdir)
    for c in cats:
        (vdir / c.get("dir", c["key"])).mkdir(parents=True, exist_ok=True)
    data = load_sets()
    missing, count = [], 0
    for files in (data["common"].get(service, {}), st["files"]):
        for cat, paths in files.items():
            for rel in paths:
                src = cat_dir(service, cat) / rel
                if not src.exists() or not _inside_models(src):   # 無い、または、リンク先がモデル置き場の外
                    missing.append(f"{cat}/{rel}")
                    continue
                dst = vdir / next(c.get("dir", c["key"]) for c in cats if c["key"] == cat) / rel
                if dst.is_symlink() or dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.symlink_to(src)
                count += 1
    return {"name": st["name"], "count": count, "missing": missing, "view_dir": str(vdir)}
