"""種別フォルダ(checkpoints / vae / loras …)を持つ、ComfyUI / Forge のモデルの一覧と、サービス間の共有リンク。"""
import os
import shlex

from ...core.config import CFG, ROOTS, cat_dir, categories, exts, models_dir
from .files import rel_files
from .sets import load_sets


def link_index():
    """実体ファイル -> それを指しているシンボリックリンク(サービス間の共有)。"""
    idx = {}
    for name in CFG["services"]:
        for c in categories(name):
            d = cat_dir(name, c["key"])
            if d.is_dir():
                for f in rel_files(d, exts(name)):
                    if f.is_symlink():
                        idx.setdefault(os.path.realpath(f), []).append(f)
    return idx


def _set_membership(service):
    """(種別, 相対パス) -> それを含むセット名の一覧(「共通」を含む)。"""
    sd = load_sets()
    member = {}
    for nm, files in [("共通", sd["common"].get(service, {}))] + [(x["name"], x["files"]) for x in sd["sets"] if x["service"] == service]:
        for cat_, ps_ in files.items():
            for p_ in ps_:
                member.setdefault((cat_, p_), []).append(nm)
    return member


def scan_categories(service):
    """モデルタブ用: 種別ごとのファイル一覧(共有リンク・所属セット・削除コマンド付き)。"""
    q = shlex.quote
    idx, member = link_index(), _set_membership(service)
    cats_out = []
    for c in categories(service):
        d = cat_dir(service, c["key"])
        items = []
        for f in (rel_files(d, exts(service)) if d.is_dir() else []):
            is_link = f.is_symlink()
            broken = is_link and not f.exists()
            real = os.path.realpath(f)
            links = [x for x in idx.get(real, []) if x != f] if not is_link else []
            item = {"cat": c["key"], "path": str(f.relative_to(d)), "size": 0 if broken else f.stat().st_size,
                    "link": real if is_link else None, "broken": broken, "sets": member.get((c["key"], str(f.relative_to(d))), []),
                    "linked_by": [str(x.relative_to(ROOTS.models)) for x in links],
                    "rm": "rm -v -- " + q(str(f)), "rm_all": None, "rm_all_label": "リンクも一緒に消す"}
            if links:
                item["rm_all"] = "rm -v -- " + " ".join(q(str(x)) for x in [f] + links)
            items.append(item)
        cats_out.append({"key": c["key"], "label": c["label"], "hint": c.get("hint", ""),
                         "count": len(items), "size": sum(i["size"] for i in items), "items": items})
    return {"service": service, "dir": str(models_dir(service)), "kind": "categories", "categories": cats_out}


def make_links(service, cat_key, dest):
    """もう一方のサービスの、対応する種別フォルダに、共有用のシンボリックリンクを作る。"""
    c = next((c for c in categories(service) if c["key"] == cat_key), None)
    made = []
    for other, okey in ((c or {}).get("link") or {}).items():
        if other in CFG["services"]:
            ld = cat_dir(other, okey)
            ld.mkdir(parents=True, exist_ok=True)
            lp = ld / dest.name
            if not lp.exists() and not lp.is_symlink():
                lp.symlink_to(dest)
                made.append(str(lp))
    return made
