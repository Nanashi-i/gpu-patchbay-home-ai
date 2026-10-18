"""webui 系のソフト(ComfyUI / Forge / A1111)を、起動スクリプト(webui.sh など)を通さず、
venv の python で、本体(launch.py / main.py)を直接起動する、ハブの方式(machine.json の launcher)。

webui.sh がやっていた事前処理(git・Python の確認、venv の作成、TCMalloc)は、prepare_webui が行う。
"""
import os
import re
import shlex
import shutil
import subprocess
import sys

from ...core.config import expand, to_path
from ...core.errors import HubError


def webui_command(svc):
    """webui 系(Forge / A1111)を webui.sh / webui-user.sh を通さず、venv の python で launch.py を直接起動するコマンド。"""
    lc = svc["launcher"]
    d = to_path(svc["dir"])
    script = d / lc.get("script", "launch.py")
    if not script.exists():
        raise HubError(f"起動スクリプトが見つかりません: {script}")
    py = d / lc.get("venv", "venv") / "bin" / "python"
    args = expand(lc.get("args", "")).replace("{port}", str(svc.get("port", "")))
    return [str(py), "-u", str(script)] + shlex.split(args), d


def prepare_webui(svc, env, say):
    """webui.sh がやっていた事前処理: git/Python の確認、venv の作成、TCMalloc の読み込み。"""
    lc = svc["launcher"]
    d = to_path(svc["dir"])
    venv = d / lc.get("venv", "venv")
    py = venv / "bin" / "python"
    if not shutil.which("git"):
        raise HubError("git が見つかりません。インストールしてください")
    if not py.exists() and lc.get("auto_venv", True) is False:
        raise HubError(f"venv が見つかりません: {venv}。{svc['label']} のインストール手順(依存パッケージの導入)を先に完了してください")
    if not py.exists():
        py_cfg = expand(lc.get("python", ""))
        base = (py_cfg if os.path.exists(os.path.expanduser(py_cfg)) else shutil.which(py_cfg)) if py_cfg else None
        base = os.path.expanduser(base) if base else shutil.which("python3")
        if not base:
            raise HubError("Python が見つかりません")
        say("venv を作成中…(初回のみ)")
        for c in ([base, "-m", "venv", str(venv)], [str(py), "-m", "pip", "install", "--upgrade", "pip"]):
            r = subprocess.run(c, capture_output=True, text=True)
            if r.returncode:
                shutil.rmtree(venv, ignore_errors=True)  # 作りかけの venv を残さない(次回に「作成済み」と誤認しないため)
                raise HubError(f"venv の作成に失敗: {(r.stderr or r.stdout).strip()[-200:]} "
                               f"(Python は {base}。python3-venv が必要、または launcher.python で別の Python を指定してください)")
    ver = subprocess.run([str(py), "-c", "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                         capture_output=True, text=True).stdout.strip()
    allowed = lc.get("python_versions")
    if allowed and ver not in allowed and "--skip-python-version-check" not in expand(lc.get("args", "")):
        raise HubError(f"venv の Python {ver} は未対応です({'/'.join(allowed)} 推奨)。続行するなら args に --skip-python-version-check を付けてください")
    env.update({k: expand(str(v)) for k, v in lc.get("env", {}).items()})
    if sys.platform.startswith("linux") and not env.get("NO_TCMALLOC") and not env.get("LD_PRELOAD"):
        try:
            out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=10,
                                 env={**os.environ, "PATH": "/sbin:/usr/sbin:" + os.environ.get("PATH", "")}).stdout
            m = re.search(r"libtcmalloc(?:_minimal)?\.so\.\d+.*=>\s*(\S+)", out)
            if m:
                env["LD_PRELOAD"] = m.group(1)
        except Exception:  # noqa: BLE001
            pass
