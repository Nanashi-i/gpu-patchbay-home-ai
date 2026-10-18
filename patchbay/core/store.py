"""JSON ファイルの読み書き(書き込みは、一時ファイルに書いてから置き換えるアトミック方式)。"""
import json
import os
import threading

# presets / sets など、複数のスレッドから触るファイルの読み書きを直列化する
file_lock = threading.RLock()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")   # 同時に書いても、衝突しない名前
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
