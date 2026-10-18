"""ComfyUI と Forge の共通部分: 種別フォルダのモデル・モデルセット(表示用フォルダ)・モデル置き場の引数(dir_args)。

派生クラス(apps/comfyui, apps/forge)が、アプリごとの違いだけを、次のフックで書く:
  write_view_config(name, base_dir, cats)  アプリが見るフォルダの設定を書く(ComfyUI: extra_model_paths.yaml)
  after_view(name, view_dir, cats)         セットを適用した後の処理(Forge: 前回の VAE/TE の選択を整理)
"""
from pathlib import Path

from ...core.config import categories, models_dir, service
from ...core.schema import Str
from ..base import ScriptApp
from .downloads import CategoryRules
from .image_models import scan_categories
from .sets import build_view


class ImageApp(ScriptApp):
    preset_fields = {**ScriptApp.preset_fields, "model_set": Str(1, 64, pattern=r"[A-Za-z0-9_.-]+")}

    # ---- モデル・ダウンロード
    def models(self, name):
        return scan_categories(name)

    def download_rules(self, name):
        return CategoryRules(name)

    # ---- モデルセット(表示用フォルダ)
    def write_view_config(self, name, base_dir, cats):
        """アプリが見るフォルダの設定(base_dir を見るようにする)。既定では何もしない。"""

    def after_view(self, name, view_dir, cats):
        """セットを適用した後の処理。戻り値は、ログに出す情報(なければ None)。"""
        return None

    def apply_view(self, name, set_id):
        """set_id があれば、そのセットだけが見えるようにする。空なら、全部見える状態に戻す。"""
        svc = service(name)
        if not svc.get("view"):
            return None
        cats = categories(name)
        if not set_id:
            self.write_view_config(name, models_dir(name), cats)
            return None
        info = build_view(name, set_id)
        vdir = Path(info["view_dir"])
        self.write_view_config(name, vdir, cats)
        info["env"] = {svc["view"]["env"]: str(vdir)} if svc["view"].get("env") else {}   # 起動スクリプトが読む環境変数
        info["cleaned"] = self.after_view(name, vdir, cats)
        return info

    def prepare(self, name, preset, cmd, env, say):
        svc = service(name)
        info = self.apply_view(name, preset.get("model_set")) if svc.get("view") else None
        if info:
            env.update(info.get("env", {}))
        prepared = super().prepare(name, preset, cmd, env, say)   # launcher の事前処理
        if svc.get("launcher") and not preset.get("cmd") and svc.get("dir_args"):   # モデル置き場を引数で渡す
            base = Path(info["view_dir"]) if info else models_dir(name)
            dn = {c["key"]: c.get("dir", c["key"]) for c in categories(name)}
            for flag, key in svc["dir_args"]:
                cmd.extend([flag, str(base / dn[key])])
        if svc.get("view"):
            prepared.log += self._view_log(info)
        prepared.set_name = info["name"] if info else None
        return prepared

    @staticmethod
    def _view_log(info):
        lines = [f"# model set: {info['name']} ({info['count']} files, missing {len(info['missing'])})" if info
                 else "# model set: すべて表示"]
        if info and info.get("cleaned"):
            keep, drop = info["cleaned"]
            lines.append(f"# 前回のVAE/TE選択を整理: 残す {len(keep)} / 除外 {len(drop)}")
            lines += [f"#   removed: {d}" for d in drop]
        lines += [f"#   missing: {m}" for m in (info or {}).get("missing", [])]
        return lines

    def after_stop(self, name):
        if service(name).get("view"):   # ハブ外から起動されても、全部見えるように戻す
            self.apply_view(name, None)
