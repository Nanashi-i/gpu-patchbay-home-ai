"""サービスの起動の流れ(アプリごとの違いは、apps/ のフックに任せる)。

  検証(同期) → [操作スレッド] 排他(同じグループを停止) → アプリの準備 → 起動 → 記録
"""
from .config import enabled
from .errors import HubError
from .presets import clean, get_preset
from .process import run_op, say, spawn, stop_group_of


def _resolve_preset(pid, params, label):
    if params:   # 保存していない設定での、一時起動
        p = {**params, "id": pid or "_adhoc", "name": label or "一時設定"}
        return clean(p)   # アプリで使える項目だけを残して、型を検証する
    return get_preset(pid)


def start_preset(pid, params=None, label=None):
    from ..apps import app_for   # 循環を避けるため、使うときに読み込む
    p = _resolve_preset(pid, params, label)
    name = p["service"]
    if not enabled(name):
        raise HubError("このサービスは「使わない」に設定されています(⚙ 設定から戻せます)")
    app = app_for(name)
    cmd, cwd, env = app.build_command(name, p)   # 事前検証(同期): ここで失敗すると、すぐ画面にエラーが出る
    app.validate(name, p)

    def go():
        stop_group_of(name)
        say(f"{p['name']} を起動中…")
        prepared = app.prepare(name, p, cmd, env, say)
        spawn(name, cmd, cwd, env,
              {"preset": p["id"], "pname": p["name"], "model": p.get("model"), "set": prepared.set_name},
              prepared.log)

    run_op(f"{p['name']} を起動準備中…", go)
