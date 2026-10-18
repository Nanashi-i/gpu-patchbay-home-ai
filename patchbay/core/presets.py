"""プリセット: 「サービス + 起動するときの設定」の保存。

保存先は presets.json(ハブのフォルダ)。項目は、全サービス共通の項目と、アプリごとの項目の和集合で、
アプリごとの項目は、各アプリが preset_fields で宣言する(apps/*/app.py)。
"""
import re
import secrets

from .config import CFG, ROOTS
from .errors import HubError
from .schema import Bool, Obj, Str, require
from .store import file_lock, load_json, save_json

ID = Str(1, 64, pattern=r"[A-Za-z0-9_.-]+")
# 全サービス共通の項目(アプリごとの項目は、各アプリが preset_fields で、型つきで宣言する)
COMMON_FIELDS = {"id": ID, "name": Str(1, 100), "service": Str(1, 40, pattern=r"[A-Za-z0-9_-]+"), "note": Str(0, 500), "favorite": Bool()}


def fields_for(service_name):
    """そのサービスのプリセットで使える項目と型(共通 + アプリの宣言)。"""
    from ..apps import app_for   # 循環を避けるため、使うときに読み込む
    return {**COMMON_FIELDS, **app_for(service_name).preset_fields}


def clean(p):
    """入力のプリセットから、そのアプリで使える項目だけを残して(空の値は捨てる)、型を検証する。HubError で、誤りを返す。"""
    if not isinstance(p, dict):
        raise HubError("プリセットの形が正しくありません")
    name = p.get("service")
    if not isinstance(name, str) or name not in CFG["services"]:
        raise HubError("name と service は必須です")
    spec = fields_for(name)
    out = {k: v for k, v in p.items() if k in spec and v not in ("", None, [])}
    if not out.get("name"):
        raise HubError("name と service は必須です")
    require(Obj(spec, extra="ignore"), out, "プリセット")
    return out


# ---------------------------------------------------------------- presets
def load_presets():
    with file_lock:
        return load_json(ROOTS.presets_file, [])


def upsert_preset(p):
    p = clean(p)
    if not p.get("id"):
        slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-") or "preset"
        p["id"] = f"{slug}-{secrets.token_hex(2)}"
    with file_lock:
        items = load_presets()
        for i, q in enumerate(items):
            if q["id"] == p["id"]:
                items[i] = p
                break
        else:
            items.append(p)
        if p.get("favorite") and p.get("model"):  # お気に入り(既定)はモデルごとに1つ
            for q in items:
                if q["id"] != p["id"] and q.get("service") == p["service"] and q.get("model") == p["model"]:
                    q.pop("favorite", None)
        save_json(ROOTS.presets_file, items)
    return p


def delete_preset(pid):
    with file_lock:
        items = [q for q in load_presets() if q["id"] != pid]
        save_json(ROOTS.presets_file, items)


def get_preset(pid):
    for p in load_presets():
        if p["id"] == pid:
            return clean(p)   # 手で書き換えたファイルでも、型を確認してから使う
    raise HubError("プリセットが見つかりません")
