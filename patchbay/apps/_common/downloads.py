"""ComfyUI / Forge のダウンロードのルール: 種別フォルダへの振り分け・共有リンク・モデルセットへの追加。"""
from pathlib import Path

from ...core.config import cat_dir, cat_meta, service
from ...downloads.rules import FolderRules
from ...downloads.safety import safe_dest
from .categories import guess_category
from .image_models import make_links
from .sets import add_to_set, get_set, upsert_set


class CategoryRules(FolderRules):
    def categories(self):
        return cat_meta(self.service)

    def guess(self, path):
        return guess_category(self.service, path)

    def default_folder(self, repo_name):
        return ""

    def job_options(self, body):
        set_id = body.get("set_id") or None
        if service(self.service).get("view"):
            new_name = (body.get("new_set") or "").strip()
            if new_name:
                set_id = upsert_set({"name": new_name, "service": self.service, "files": {}})["id"]
            elif set_id and set_id != "_common":
                get_set(self.service, set_id)
        else:
            set_id = None
        return {"link": bool(body.get("link")), "set": set_id}

    def dest(self, item, folder):
        path = item["path"] if isinstance(item, dict) else item
        cat = item.get("category") if isinstance(item, dict) else None
        return safe_dest(self.service, cat_dir(self.service, cat), Path(path).name), cat

    def on_done(self, job, dest):
        if job["link"]:
            make_links(job["service"], job["category"], dest)
        if job.get("set"):
            add_to_set(job["service"], job["set"], job["category"], str(dest.relative_to(cat_dir(job["service"], job["category"]))))
