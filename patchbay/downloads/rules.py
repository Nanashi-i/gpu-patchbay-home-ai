"""ダウンロードの「ルール」(アプリごとに違う部分)。仕組み(キュー・再開)は engine.py にある。

アプリは、App.download_rules() で、このクラス(または、その派生)を返す。
  FolderRules   : フォルダに、そのまま保存する(llama.cpp / Strata)
  CategoryRules : 種別フォルダ(checkpoints / vae / loras …)に振り分ける(ComfyUI / Forge。apps/_common/downloads.py)
"""
from ..core.config import exts, models_dir
from .safety import safe_dest


class FolderRules:
    """リポジトリ名のフォルダを既定にして、models_dir の下に保存する。"""

    def __init__(self, service):
        self.service = service

    def exts(self):
        return exts(self.service)

    def categories(self):
        """画面に出す種別の一覧([{key, label}])。種別のないアプリは空。"""
        return []

    def guess(self, path):
        """ファイルのパスから、種別を推定する(種別のないアプリは None)。"""
        return None

    def default_folder(self, repo_name):
        return repo_name

    def job_options(self, body):
        """ジョブに付ける追加の設定(共有リンク・セット)。{link, set}"""
        return {"link": False, "set": None}

    def dest(self, item, folder):
        """保存先と種別を返す: (保存先の Path, 種別 or None)。"""
        path = item["path"] if isinstance(item, dict) else item
        return safe_dest(self.service, models_dir(self.service) / folder, path), None

    def on_done(self, job, dest):
        """ダウンロードが完了したあとの処理。"""
