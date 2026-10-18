#!/usr/bin/env python3
"""互換のための入口(systemd の登録や、これまでの起動方法を変えないため)。実体は patchbay/ パッケージで、
`python3 -m patchbay` と同じ。"""
from patchbay.server import main

if __name__ == "__main__":
    main()
