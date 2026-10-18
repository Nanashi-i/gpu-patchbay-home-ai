"""ComfyUI: モデルセットを、extra_model_paths.yaml で伝える。

ComfyUI は、起動時に extra_model_paths.yaml を読んで、モデルの置き場を決める。ハブは、起動のたびに、
そのファイルを「全部見える(モデル置き場)」か「セットだけ見える(表示用フォルダ)」に書き換える(初回のみ .bak-patchbay)。
"""
import shutil

from ...core.config import service, to_path
from .._common.image import ImageApp


def _write_yaml(yaml_path, base, cats):
    lines = ["# managed by GPU Patchbay: 起動時にモデルセットに合わせて書き換えられます", "shared:", f"  base_path: {base}/"]
    lines += [f"  {c['key']}: {c.get('dir', c['key'])}/" for c in cats]
    yaml_path.write_text("\n".join(lines) + "\n")


class ComfyApp(ImageApp):
    app_id = "comfyui"

    def write_view_config(self, name, base_dir, cats):
        vc = service(name)["view"]
        if not vc.get("yaml"):
            return
        yaml_path = to_path(vc["yaml"])
        bak = yaml_path.with_name(yaml_path.name + ".bak-patchbay")
        if yaml_path.exists() and not bak.exists():
            shutil.copyfile(yaml_path, bak)
        _write_yaml(yaml_path, base_dir, cats)
