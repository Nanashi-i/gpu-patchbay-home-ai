"""設定(machine.json)の読み込みと、パス・変数の展開。

読み込みは init() で行う(import しただけでは、何も読まない)。CFG は同じ辞書を、その場で更新するので、
`from patchbay.core.config import CFG` で、どこからでも同じものを参照できる。

置き場所の決まり方(優先順位): サービスごとの dir / models_dir  >  apps_root / models_root  >  root
使える変数: {home} {root} {apps_root} {models_root}、プリセットの extra では、さらに {models_dir}。
"""
import os
import shutil
from pathlib import Path

from . import schema
from .errors import HubError
from .machine_schema import MACHINE
from .store import load_json

HOME = str(Path.home())
REPO_DIR = Path(__file__).resolve().parents[2]   # このリポジトリのフォルダ(設定の雛形・web/ がある場所)

CFG = {}


class Roots:
    """init() が設定する、置き場所とファイルの場所。"""
    root = apps = models = state = Path(HOME)
    machine_file = presets_file = sets_file = Path("")


ROOTS = Roots()


def _first_run(target):
    """実物の設定が無ければ、同梱の *.example.json から作る(実物は .gitignore で除外されている)。"""
    example = target.with_name(target.stem + ".example.json")
    if not target.exists() and example.exists():
        shutil.copyfile(example, target)
        print(f"[patchbay] {target.name} を {example.name} から作成しました。内容を環境に合わせて編集してください", flush=True)


def init(machine_file=None):
    """設定を読み込む。環境変数 PATCHBAY_MACHINE で、別の設定ファイルを指定できる(テスト用)。"""
    mf = Path(machine_file or os.environ.get("PATCHBAY_MACHINE") or REPO_DIR / "machine.json")
    _first_run(mf)
    _first_run(mf.parent / "presets.json")
    data = load_json(mf, None)
    if data is None:
        raise HubError(f"{mf} がありません")
    for w in schema.require(MACHINE, data, f"{mf.name} "):   # 型の誤りは、起動を止める。未知のキーは、警告だけ
        print(f"[patchbay] 警告 {mf.name}: {w}", flush=True)
    CFG.clear()
    CFG.update(data)
    ROOTS.machine_file, ROOTS.presets_file, ROOTS.sets_file = mf, mf.parent / "presets.json", mf.parent / "sets.json"
    ROOTS.root = Path(os.path.expanduser(_home(CFG.get("root", str(REPO_DIR.parent)))))   # 既定: 本体のフォルダの1つ上
    ROOTS.apps = Path(os.path.expanduser(_under_root(CFG.get("apps_root", "{root}/apps"))))
    ROOTS.models = Path(os.path.expanduser(_under_root(CFG.get("models_root", "{root}/models"))))
    ROOTS.state = Path(os.path.expanduser(_home(CFG.get("state_dir", "{home}/.local/state/gpu-patchbay-home-ai"))))
    ROOTS.state.mkdir(parents=True, exist_ok=True)


# ---- 変数の展開(下ほど、使える変数が多い)
def _home(s):
    return str(s).replace("{home}", HOME)


def _under_root(s):
    return _home(s).replace("{root}", str(ROOTS.root))


def _under_roots(s):
    return _under_root(s).replace("{apps_root}", str(ROOTS.apps)).replace("{models_root}", str(ROOTS.models))


def expand(s, service=None):
    """文字列の変数({home} {root} {apps_root} {models_root}、service があれば {models_dir})を展開する。"""
    s = _under_roots(s or "")
    if service:
        s = s.replace("{models_dir}", str(models_dir(service)))
    return s


def to_path(s, service=None):
    """変数と ~ を展開して Path にする。"""
    return Path(os.path.expanduser(expand(s, service)))


# ---- サービスの設定への入口
def services():
    return CFG["services"]


def service(name):
    try:
        return CFG["services"][name]
    except KeyError:
        raise HubError("不明なサービス") from None


def enabled(name):
    return service(name).get("enabled", True)


def models_dir(name):
    """サービス専用のモデル置き場。"""
    return Path(os.path.expanduser(_under_roots(service(name)["models_dir"])))


def exts(name):
    return {e.lower() for e in service(name).get("exts", [".gguf"])}


def categories(name):
    return service(name).get("categories", [])


def cat_dir(name, key):
    c = next((c for c in categories(name) if c["key"] == key), None)
    if not c:
        raise HubError(f"不明な種別: {key}")
    return models_dir(name) / c.get("dir", c["key"])


def cat_meta(name):
    return [{"key": c["key"], "label": c["label"]} for c in categories(name)]


def ensure_dirs():
    for name, svc in CFG["services"].items():
        try:
            models_dir(name).mkdir(parents=True, exist_ok=True)
            for c in svc.get("categories", []):
                cat_dir(name, c["key"]).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[patchbay] mkdir 失敗 {name}: {e}", flush=True)
