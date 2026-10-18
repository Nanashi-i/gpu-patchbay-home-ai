"""サービスの管理(導入の判定・自動検出・設定の保存・パスの確認)。アプリごとの違いは、apps/ に任せる。"""
import shutil
import time
from pathlib import Path

from . import schema
from .config import CFG, HOME, ROOTS, ensure_dirs, expand, service, to_path
from .errors import HubError
from .machine_schema import MACHINE
from .process import service_status
from .store import file_lock, load_json, save_json

_DET = {}   # 自動検出の結果(20秒キャッシュ)


def _app(name):
    from ..apps import app_for   # 循環を避けるため、使うときに読み込む
    return app_for(name)


def is_installed(name):
    return _app(name).installed(name)


def detect_candidates(name):
    """標準の場所に無いときに、よくある場所から、インストール済みのフォルダを探す。"""
    key = (name, int(time.time() // 20))
    if key in _DET:
        return _DET[key]
    svc = service(name)
    cur = to_path(svc["dir"])
    marker = _app(name).marker(name)
    names = svc.get("detect_names") or [Path(expand(svc["dir"])).name]
    bases = [Path(HOME), ROOTS.apps, ROOTS.root, Path(HOME, "apps"), Path(HOME, "src"), Path(HOME, "git"), Path(HOME, "projects"),
             Path(HOME, "Projects"), Path(HOME, "repos"), Path(HOME, "dev"), Path("/opt")]
    out = []
    for b in bases:
        for n in names:
            c = b / n
            ok = (c / marker).exists() if marker else c.is_dir()
            if ok and c != cur and str(c) not in out:
                out.append(str(c))
    _DET[key] = out[:4]
    return _DET[key]


def update_service_config(name, body):
    """画面の ⚙ からの保存。machine.json に書き込む(1つ前の版は machine.json.bak)。起動中は変更できない。"""
    with file_lock:   # 読んで・変えて・書くまでを、1つずつにする
        return _update_service_config(name, body)


def _update_service_config(name, body):
    service(name)
    if service_status(name)["state"] != "stopped":
        raise HubError("起動中は設定を変えられません。先に停止してください")
    mf = ROOTS.machine_file
    disk = load_json(mf, None)
    if not disk or name not in disk.get("services", {}):
        raise HubError("machine.json を読めません")
    sd, changes = disk["services"][name], {}
    for key in ("dir", "models_dir"):
        if key in body:
            v = str(body[key] or "").strip()
            if not v:
                raise HubError(f"{key} が空です")
            changes[key] = v
    if "port" in body:
        try:
            port = int(body["port"])
        except (TypeError, ValueError):
            raise HubError("ポートは数字で指定してください") from None
        if not 1 <= port <= 65535:
            raise HubError("ポートは 1〜65535 で指定してください")
        changes["port"] = port
    if "enabled" in body:
        changes["enabled"] = bool(body["enabled"])
    if not changes:
        return {"ok": True}
    sd.update(changes)
    schema.require(MACHINE, disk, "設定")   # 保存の前に、全体の形を確認する
    shutil.copyfile(mf, mf.with_name(mf.name + ".bak"))
    save_json(mf, disk)
    CFG["services"][name].update(changes)   # 再起動なしで反映
    _DET.clear()
    if "models_dir" in changes:
        ensure_dirs()
    return {"ok": True}


def resolve_path(name, raw, as_dir=False):
    """入力されたパスを解決して、存在を確認する。as_dir なら、インストール場所として正しいか(目印のファイル)まで。"""
    svc = service(name)
    p = to_path(raw or "", name)
    if not p.is_absolute():
        p = to_path(svc["dir"]) / p
    out = {"resolved": str(p), "exists": p.exists(), "is_file": p.is_file(), "is_dir": p.is_dir()}
    if as_dir:
        m = _app(name).marker(name)
        out["marker"] = m
        out["installed_here"] = (p / m).exists() if m else p.is_dir()
    return out
