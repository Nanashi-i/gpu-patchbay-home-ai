"""ファイル探索の共通の道具。"""
import os
from pathlib import Path


def rel_files(root, exts):
    """root 以下の対象拡張子のファイル(隠しフォルダ・.part は除く)。シンボリックリンクも含む。"""
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".")]
        for fn in fns:
            if not fn.startswith(".") and Path(fn).suffix.lower() in exts:
                out.append(Path(dp) / fn)
    return sorted(out)


def dir_size(path):
    total = 0
    for dp, _dns, fns in os.walk(path):
        for fn in fns:
            try:
                total += os.stat(os.path.join(dp, fn)).st_size
            except OSError:
                pass
    return total
