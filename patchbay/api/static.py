"""画面(web/)の配信と、テーマの一覧。

テーマは、web/css/themes/<id>.css の1ファイル=1テーマ。ファイルの先頭に、次の形式のコメントを書くと、
画面のテーマメニューに自動で出る(ファイルを置くだけで、テーマを増やせる):
    /* name: ダーク | swatch: #0f1115 #181b21 #4f9dff | note: 説明(省略可) | order: 10(省略可) */
default.css は、既定のテーマ(OS の設定に合わせる)で、常に先頭に読み込む。
"""
import re

from ..core.config import REPO_DIR

WEB = REPO_DIR / "web"
THEMES = WEB / "css" / "themes"
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


def _theme_meta(path):
    head = path.read_text(encoding="utf-8").split("\n", 1)[0]
    m = re.match(r"/\*\s*(.*?)\s*\*/", head)
    meta = {}
    if m:
        for part in m.group(1).split("|"):
            k, _, v = part.partition(":")
            meta[k.strip()] = v.strip()
    return {"id": "" if path.stem == "default" else path.stem, "name": meta.get("name", path.stem),
            "swatch": meta.get("swatch", "").split(), "note": meta.get("note", ""), "order": int(meta.get("order", 50) or 50)}


def themes_list():
    items = [_theme_meta(p) for p in THEMES.glob("*.css")] if THEMES.is_dir() else []
    return sorted(items, key=lambda t: (t["id"] != "", t["order"], t["name"]))


def themes_css():
    """全テーマの CSS を、default → 他の順につなげたもの。"""
    if not THEMES.is_dir():
        return ""
    files = sorted(THEMES.glob("*.css"), key=lambda p: (p.stem != "default", p.stem))
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def serve(path):
    """(状態コード, Content-Type, 本文) か None。web/ の外には出ない。"""
    if path in ("/", "/index.html"):
        path = "/index.html"
    if path == "/css/themes.css":
        return 200, MIME[".css"], themes_css().encode()
    if path == "/themes.json":
        import json
        return 200, MIME[".json"], json.dumps(themes_list(), ensure_ascii=False).encode()
    f = (WEB / path.lstrip("/")).resolve()
    if WEB.resolve() not in f.parents or not f.is_file() or f.suffix not in MIME:
        return None
    return 200, MIME[f.suffix], f.read_bytes()
