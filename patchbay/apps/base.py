"""アプリの「約束」。アプリごとの違いは、このクラスの派生(apps/<名前>/app.py)に閉じ込める。

core / downloads / monitor / api は、アプリの中身を知らず、ここに並ぶメソッドだけを呼ぶ。
新しいアプリを足すには、apps/ にフォルダを作り、App(または ScriptApp)の派生クラスを書いて、
apps/__init__.py の APPS に登録する。

  役割                          メソッド
  ───────────────────────────  ──────────────────────────────
  導入の判定                    marker / installed
  起動コマンドを作る            build_command / validate
  起動の前の準備                prepare(→ Prepared)
  停止の後の後始末              after_stop
  モデルの一覧                  models
  ダウンロードのルール          download_rules
  モニターに出す固有の指標      stats
  バージョン表示                version
  プリセットの項目              preset_fields
  /api/state への追加項目       extra_state
"""
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field

from ..core.config import expand, service, to_path
from ..core.errors import HubError
from ..core.schema import Str
from ..core.secrets import load_secrets
from ..downloads.rules import FolderRules
from ._common.entries import scan_entries
from ._common.launcher import prepare_webui, webui_command


@dataclass
class Prepared:
    """prepare() の結果。log は、ログの先頭に書く行、set_name は、画面に出すモデルセット名。"""
    log: list = field(default_factory=list)
    set_name: str = None


class App:
    app_id = "generic"
    preset_fields = {}            # このアプリのプリセットで使う項目と、その型(共通の項目は除く。core/schema.py の部品で書く)
    default_marker = ""           # 導入済みの目印のファイル(dir からの相対)

    # ---- 導入の判定
    def marker(self, name):
        m = service(name).get("marker")
        return m if m is not None else self.default_marker

    def installed(self, name):
        d = to_path(service(name)["dir"])
        m = self.marker(name)
        return (d / m).exists() if m else d.is_dir()

    # ---- 起動
    def build_command(self, name, preset):
        """(コマンドの配列, 作業フォルダ, 環境変数)を返す。見つからないものは HubError(起動前に画面へ出る)。"""
        raise NotImplementedError

    def validate(self, name, preset):
        """build_command のほかに、起動前(同期)に確認したいこと。"""

    def prepare(self, name, preset, cmd, env, say):
        """起動の直前(別スレッド)の準備。cmd と env は、その場で書き換えてよい。"""
        return Prepared()

    def after_stop(self, name):
        """停止の後の後始末。"""

    # ---- 情報
    def models(self, name):
        """モデルタブ用の一覧。{service, dir, kind, items | categories}"""
        return scan_entries(name)

    def download_rules(self, name):
        return FolderRules(name)

    def stats(self, name):
        """モニターに出す固有の指標。動いていなければ None。"""
        return None

    def version(self, name, preset=None):
        """{short, full} か None。既定は git の情報(タグ・日付)。"""
        return git_version(to_path(service(name).get("version_dir") or service(name).get("dir", "")))

    def extra_state(self, name):
        """/api/state のサービスの項目への、追加分。"""
        return {}


class ScriptApp(App):
    """起動スクリプト、または launcher(venv の python で本体を直接起動)で動くアプリ。"""
    preset_fields = {"cmd": Str(1, 1000), "args": Str(0, 2000)}

    def marker(self, name):
        svc = service(name)
        if svc.get("marker") is not None:
            return svc["marker"]
        return (svc.get("launcher") or {}).get("script", "")

    def build_command(self, name, preset):
        svc = service(name)
        env = dict(os.environ)
        env["PATH"] = f"{os.path.expanduser('~')}/.local/bin:" + env.get("PATH", "")
        if svc.get("launcher") and not preset.get("cmd"):
            cmd, cwd = webui_command(svc)
            return cmd + shlex.split(expand(preset.get("args", ""))), cwd, env
        ak = svc.get("api_key")
        if ak:
            key = load_secrets().get(name)
            if not key:
                raise HubError(f"{svc['label']} のAPIキーが未登録です")
            env[ak["env"]] = key
        script = to_path(preset.get("cmd", ""), name)
        if not script.is_absolute():   # 相対パスは、そのサービスのフォルダからの相対
            script = to_path(svc["dir"]) / script
        if not script.exists():
            raise HubError(f"コマンドが見つかりません: {script}")
        cmd = [str(script)] if os.access(script, os.X_OK) else ["bash", str(script)]
        cmd += shlex.split(expand(preset.get("args", "")))
        return cmd, to_path(svc.get("dir", os.path.expanduser("~"))), env

    def prepare(self, name, preset, cmd, env, say):
        svc = service(name)
        if svc.get("launcher") and not preset.get("cmd"):
            prepare_webui(svc, env, say)
        return Prepared()


# ---------------------------------------------------------------- 共通の小さな道具
def run_text(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception:  # noqa: BLE001
        return ""


_GIT = {}


def git_version(d):
    """フォルダの git 情報から、バージョン表示を作る(30秒キャッシュ)。git でなければ None。"""
    if not (d / ".git").exists():
        return None
    key = (str(d), int(time.time() // 30))
    if key not in _GIT:
        desc = run_text(["git", "-C", str(d), "describe", "--tags", "--always"])
        date = run_text(["git", "-C", str(d), "log", "-1", "--format=%cs"])
        m = re.match(r"^(v?[\d.]+)-(\d+)-g([0-9a-f]+)$", desc)
        short = f"{m.group(1)} +{m.group(2)}" if m else desc
        _GIT[key] = {"short": short, "full": f"{desc} ({date}) — {d}"} if desc else None
    return _GIT[key]
