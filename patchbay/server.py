"""起動: 設定を読み込み、バックグラウンドのスレッド(モニター・ダウンロード)を動かして、HTTP サーバーを立てる。

import しただけでは、何も読み込まない(設定の読込・フォルダの作成・実行状態の復元は、setup() が行う)。
"""
import sys
import threading
from http.server import ThreadingHTTPServer

from .core import config
from .core.errors import HubError


def setup(machine_file=None, background=True):
    """設定を読み込み、必要な準備をする。background=False なら、スレッドは起動しない(テスト用)。"""
    from .core.process import restore_run
    from .downloads import engine
    from .monitor import sampler
    config.init(machine_file)
    config.ensure_dirs()
    restore_run()
    if background:
        sampler.start()
        threading.Thread(target=engine.dl_worker, daemon=True).start()


def create_server(host, port):
    from .api.handler import Handler
    return ThreadingHTTPServer((host, port), Handler)


def print_info():
    """start.sh / stop.sh のための、設定の表示(HUB_キー=値)。設定に誤りがあれば、その内容を出して終了する。"""
    try:
        config.init()
        config.ensure_dirs()
    except HubError as e:
        sys.exit(str(e))
    print(f"HUB_STATE={config.ROOTS.state}")
    print(f"HUB_HOST={config.CFG.get('host', '127.0.0.1')}")
    print(f"HUB_PORT={int(config.CFG.get('port', 5000))}")
    print(f"HUB_AUTH={'token' if config.CFG.get('token') else 'none'}")


def main(argv=None):
    if (argv if argv is not None else sys.argv[1:])[:1] == ["--info"]:
        return print_info()
    try:
        setup()
    except HubError as e:
        sys.exit(str(e))
    host, port = config.CFG.get("host", "127.0.0.1"), int(config.CFG.get("port", 5000))
    srv = create_server(host, port)
    print(f"patchbay: http://{host}:{port}  ({'token認証あり' if config.CFG.get('token') else '認証なし'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
