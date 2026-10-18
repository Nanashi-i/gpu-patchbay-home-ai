"""サービスのプロセス管理(仕組みだけ。アプリごとの知識は apps/ にある)。

- RUN  : ハブが起動したサービスの記録(PID・プリセット・起動時刻)。state_dir/running.json に保存し、ハブの再起動後に復元する
- OPS  : いま実行中の操作(起動・停止)の進捗。画面の上部に出る
- 状態 : 記録した PID の生存と、ポートへの接続の、両方で判定する(ハブの外から起動したものも「外部起動」として見える)
"""
import os
import re
import shlex
import signal
import socket
import subprocess
import threading
import time

from .config import ROOTS, service, services
from .errors import HubError
from .store import load_json, save_json

RUN = {}      # サービス名 -> {pid, preset, pname, model, set, started}
OPS = {"busy": False, "msg": "", "error": ""}
op_lock = threading.Lock()   # 起動・停止は、同時に1つだけ
run_lock = threading.RLock()  # RUN の更新と保存(状態の確認のスレッドからも、書き換わるため)


def _run_file():
    return ROOTS.state / "running.json"


def save_run():
    with run_lock:
        save_json(_run_file(), dict(RUN))


def restore_run():
    """ハブの再起動後に、まだ生きているプロセスの記録を戻す(PID が、別のプロセスに使い回されていないことも確認)。"""
    with run_lock:
        RUN.update({k: v for k, v in load_json(_run_file(), {}).items() if _same_process(v)})


# ---------------------------------------------------------------- 低レベルの調べもの
def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _proc_start(pid):
    """プロセスの開始時刻(/proc/<pid>/stat の22番目。起動からのクロック数)。取れなければ None。"""
    try:
        with open(f"/proc/{int(pid)}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def _same_process(rec):
    """記録した PID が、いまも、ハブが起動したそのプロセスか(PID の使い回しを除く)。"""
    pid = rec.get("pid", 0)
    if not pid or not pid_alive(pid):
        return False
    want = rec.get("ticks")
    return want is None or _proc_start(pid) in (None, want)   # 記録が古い形式・取れない環境では、PID の生存だけ見る


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=0.3).close()
        return True
    except OSError:
        return False


def pid_on_port(port):
    try:
        out = subprocess.run(["ss", "-ltnpH", f"sport = :{port}"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"pid=(\d+)", out)
    return int(m.group(1)) if m else None


def _tracked_alive(name):
    rec = RUN.get(name)
    return bool(rec) and _same_process(rec)


def _port_shared_with_running(name):
    """同じポートを使う、別のサービスが、ハブの記録上で動いているか。"""
    port = service(name).get("port")
    return any(o != name and osvc.get("port") == port and _tracked_alive(o) for o, osvc in services().items())


# ---------------------------------------------------------------- 状態
def service_status(name):
    svc = service(name)
    rec = RUN.get(name)
    alive = bool(rec) and _same_process(rec)
    if rec and not alive:
        with run_lock:
            RUN.pop(name, None)
            save_run()
    up = port_open(svc["port"]) if svc.get("port") else alive
    if up and not alive and svc.get("port") and _port_shared_with_running(name):
        up = False   # 同じポートの別サービスが動いているなら、こちらは動いていない
    state = "running" if up else ("starting" if alive else "stopped")
    return {"state": state, "preset": rec["preset"] if alive else None,
            "pname": rec.get("pname") if alive else None, "set": rec.get("set") if alive else None,
            "model": rec.get("model") if alive else None, "external": up and not alive,
            "started": rec["started"] if alive else None}


# ---------------------------------------------------------------- 起動と停止
def spawn(name, cmd, cwd, env, record, header_lines=()):
    """新しいセッションでプロセスを起動し、記録する(ハブが落ちても、サービスは落ちない)。"""
    with open(ROOTS.state / f"{name}.log", "wb") as logf:
        for line in header_lines:
            logf.write((line + "\n").encode())
        logf.write((" ".join(shlex.quote(c) for c in cmd) + "\n\n").encode())
        logf.flush()
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=logf,
                                stderr=subprocess.STDOUT, start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()   # ゾンビの回収
    with run_lock:
        RUN[name] = {"pid": proc.pid, "ticks": _proc_start(proc.pid), **record, "started": time.time()}
        save_run()


def stop_service(name):
    """SIGTERM → 最大30秒待つ → SIGKILL。ポートを使っているプロセスも対象(ハブの外から起動したもの)。"""
    from ..apps import app_for   # 循環を避けるため、使うときに読み込む
    svc = service(name)
    pids = set()
    if _tracked_alive(name):
        pids.add(RUN[name]["pid"])
    if svc.get("port") and not _port_shared_with_running(name):   # 同じポートの別サービスを、巻き込まない
        p = pid_on_port(svc["port"])
        if p:
            pids.add(p)

    def sig(s):
        for pid in pids:
            try:
                pg = os.getpgid(pid)
                if pg == pid and pg != os.getpgrp():
                    os.killpg(pg, s)
                else:
                    os.kill(pid, s)
            except ProcessLookupError:
                pass

    if pids:
        sig(signal.SIGTERM)
        end = time.time() + 30
        while time.time() < end:
            if not any(pid_alive(p) for p in pids) and not (svc.get("port") and port_open(svc["port"])):
                break
            time.sleep(0.5)
        if any(pid_alive(p) for p in pids):
            sig(signal.SIGKILL)
            time.sleep(1)
    with run_lock:
        RUN.pop(name, None)
        save_run()
    try:
        app_for(name).after_stop(name)
    except Exception as e:  # noqa: BLE001
        print(f"[patchbay] 停止後の処理に失敗 {name}: {e}", flush=True)


def run_op(msg, fn):
    """起動・停止を、別スレッドで実行する(同時に1つだけ)。進捗は OPS に出る。"""
    if not op_lock.acquire(blocking=False):
        raise HubError("別の操作を実行中です")

    def work():
        try:
            OPS.update(busy=True, msg=msg, error="")
            fn()
        except Exception as e:  # noqa: BLE001
            OPS["error"] = str(e)
        finally:
            OPS.update(busy=False, msg="")
            op_lock.release()

    threading.Thread(target=work, daemon=True).start()


def say(msg):
    OPS["msg"] = msg


def stop_request(name):
    if name not in services():
        raise HubError("不明なサービス")
    run_op(f"{service(name)['label']} を停止中…", lambda: stop_service(name))


def stop_group_of(name):
    """name と同じ排他グループのサービス(と name 自身)のうち、動いているものを止める。"""
    svc = service(name)
    for other, osvc in services().items():
        same_group = osvc.get("group") and osvc.get("group") == svc.get("group")
        if (other == name or same_group) and service_status(other)["state"] != "stopped":
            say(f"{osvc['label']} を停止中…")
            stop_service(other)
