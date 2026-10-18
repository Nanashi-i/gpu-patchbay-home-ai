"""秘密情報: サービスの API キーと、ダウンロード用のトークン(Hugging Face / Civitai)。

保存先は、state_dir の secrets.json(本人だけが読める権限 600)。リポジトリの外なので、公開されない。
画面には、キー本体を表示しない(生成した直後の1回だけ返す)。
"""
import json
import os
import secrets
import urllib.error
import urllib.request

from .config import CFG, ROOTS, to_path
from .errors import HubError
from .store import file_lock, load_json


def secrets_file():
    return ROOTS.state / "secrets.json"


def load_secrets():
    return load_json(secrets_file(), {})


def set_secret(name, body):
    with file_lock:   # 読んで・変えて・書くまでを、1つずつにする
        return _set_secret(name, body)


def _set_secret(name, body):
    ak = CFG["services"].get(name, {}).get("api_key")
    if not ak:
        raise HubError("このサービスはAPIキーを使いません")
    data = load_secrets()
    shown = None
    if body.get("clear"):
        data.pop(name, None)
    else:
        if body.get("generate"):
            key = shown = secrets.token_urlsafe(24)
        elif body.get("import"):
            f = to_path(ak.get("import_file", ""))
            if not f.is_file():
                raise HubError(f"取り込み元がありません: {f}")
            key = f.read_text().strip()
        else:
            key = (body.get("key") or "").strip()
        if not key:
            raise HubError("APIキーが空です")
        data[name] = key
    _write_secrets(data)
    return {"ok": True, "key": shown}  # 生成したときだけ、その場で1回表示する


def _write_secrets(data):
    """権限 600 の一時ファイルに書いてから、置き換える(読む側が、書きかけを見ない。既存ファイルの権限も、600 になる)。"""
    path = secrets_file()
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


TOKENS = {"hf": ("@hf", "hf_token"), "civitai": ("@civitai", "civitai_token")}


def token_source(kind):
    """どこから取れたか: app(画面で登録) / config(machine.json) / ''"""
    key, cfg_key = TOKENS[kind]
    if load_secrets().get(key):
        return "app"
    if CFG.get(cfg_key):
        return "config"
    return ""


def get_token(kind):
    """画面で登録したトークン(secrets.json) > machine.json の値(旧方式)。hf コマンドのログインは使わない。"""
    key, cfg_key = TOKENS[kind]
    return load_secrets().get(key) or CFG.get(cfg_key) or ""


def set_token(kind, body):
    if kind not in TOKENS:
        raise HubError("不明なトークン種別")
    if body.get("clear"):
        with file_lock:
            data = load_secrets()
            data.pop(TOKENS[kind][0], None)
            _write_secrets(data)
        return {"ok": True, "user": None}
    tok = (body.get("token") or "").strip()
    if not tok:
        raise HubError("トークンが空です")
    user = _verify_hf(tok) if kind == "hf" else None   # ネットワークの確認は、ロックの外で
    with file_lock:
        data = load_secrets()
        data[TOKENS[kind][0]] = tok
        _write_secrets(data)
    return {"ok": True, "user": user}


def _verify_hf(tok):
    """有効性を確認する。ネットワークに繋がらないときは確認できないまま保存する(None を返す)。"""
    try:
        req = urllib.request.Request("https://huggingface.co/api/whoami-v2", headers={"Authorization": "Bearer " + tok, "User-Agent": "gpu-patchbay-home-ai"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get("name")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise HubError("このトークンは無効です(HF に拒否されました)") from None
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return None
