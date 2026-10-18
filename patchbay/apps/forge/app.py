"""Forge: モデル置き場の引数(dir_args)で、セットの表示用フォルダを渡す。前回選んだ VAE / テキストエンコーダも整理する。

Forge は、最後に選んだ VAE / テキストエンコーダを、config.json に絶対パスで覚えている。セット指定で起動したときに、
セット外のファイルが、前回の選択として引き継がれないよう、セットの範囲に整理する(初回のみ .bak-patchbay)。
"""
import json
import shutil
from pathlib import Path

from ...core.config import service, to_path
from .._common.files import rel_files
from .._common.image import ImageApp


def clean_saved_modules(cfg_file, key, vdir, dir_names):
    """Forge の config.json に残っている「前回選んだ VAE/テキストエンコーダ」を、表示用フォルダのものだけに整理する。
    セット外のファイルが、前回の選択として引き継がれるのを防ぐ。戻り値: (残したパス, 除いたパス)。"""
    f = Path(cfg_file)
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # 読めなければ触らない
    cur = cfg.get(key)
    if not isinstance(cur, list):
        return None  # Forge 側の設定名が変わっていたら何もしない
    avail = {}
    for dn in dir_names:
        d = vdir / dn
        if d.is_dir():
            for p in rel_files(d, {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft"}):
                avail.setdefault(p.name, str(p))
    keep, drop = [], []
    for p in cur:
        new = avail.get(Path(str(p)).name)
        (keep if new else drop).append(new or p)
    if drop or keep != cur:
        bak = f.with_name(f.name + ".bak-patchbay")
        if not bak.exists():
            shutil.copyfile(f, bak)
        cfg[key] = keep
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
        tmp.replace(f)
    return keep, drop



class ForgeApp(ImageApp):
    app_id = "forge"

    def after_view(self, name, view_dir, cats):
        sm = service(name)["view"].get("saved_modules")
        if not sm:
            return None
        dirs = {c["key"]: c.get("dir", c["key"]) for c in cats}
        return clean_saved_modules(to_path(sm["file"]), sm["key"], view_dir, [dirs[k] for k in sm["categories"]])
