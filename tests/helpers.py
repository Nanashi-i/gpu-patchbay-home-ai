"""テストの道具: 一時フォルダに、設定とダミーのアプリを作って、config を初期化する(実際の設定には触れない)。"""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from patchbay.core import config  # noqa: E402


def make_executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def default_services(tmp):
    cats_comfy = [
        {"key": "checkpoints", "label": "チェックポイント", "roles": ["checkpoint"], "link": {"forge": "Stable-diffusion"}},
        {"key": "diffusion_models", "label": "拡散モデル", "roles": ["diffusion"]},
        {"key": "text_encoders", "label": "テキストエンコーダ", "roles": ["textenc"]},
        {"key": "vae", "label": "VAE", "roles": ["vae"], "link": {"forge": "VAE"}},
        {"key": "loras", "label": "LoRA", "roles": ["lora"], "link": {"forge": "Lora"}},
    ]
    cats_forge = [
        {"key": "Stable-diffusion", "label": "チェックポイント", "roles": ["checkpoint", "diffusion"], "link": {"comfy": "checkpoints"}},
        {"key": "Lora", "label": "LoRA", "roles": ["lora"], "link": {"comfy": "loras"}},
        {"key": "VAE", "label": "VAE", "roles": ["vae"], "link": {"comfy": "vae"}},
        {"key": "text_encoder", "label": "テキストエンコーダ", "roles": ["textenc", "clip"]},
    ]
    img_exts = [".safetensors", ".ckpt", ".gguf"]
    return {
        "llama": {"label": "llama.cpp", "type": "llama", "group": "gpu", "port": 18080, "dir": "{apps_root}/llama.cpp",
                  "bin": "build/bin/llama-server", "base_args": "-np 1", "models_dir": "{models_root}/llama", "exts": [".gguf"]},
        "strata": {"label": "Strata", "type": "script", "group": "gpu", "port": 18081, "dir": "{apps_root}/Strata", "scan": "run-*.sh",
                   "marker": "serve/server.py", "api_key": {"env": "STRATA_API_KEY"}, "models_dir": "{models_root}/strata",
                   "exts": [".gguf"], "refs_glob": "strata-*.json"},
        "comfy": {"label": "ComfyUI", "type": "script", "group": "gpu", "port": 18188, "dir": "{apps_root}/ComfyUI", "marker": "main.py",
                  "models_dir": "{models_root}/comfyui", "exts": img_exts, "categories": cats_comfy,
                  "view": {"yaml": "{apps_root}/ComfyUI/extra_model_paths.yaml", "dir": "{models_root}/.view/comfyui"}},
        "forge": {"label": "Forge", "type": "script", "group": "gpu", "port": 17860, "dir": "{apps_root}/forge", "marker": "launch.py",
                  "launcher": {"venv": "venv", "script": "launch.py", "args": "--port {port} --api", "env": {"NO_TCMALLOC": "True"}},
                  "models_dir": "{models_root}/forge", "exts": img_exts, "categories": cats_forge,
                  "view": {"dir": "{models_root}/.view/forge",
                           "saved_modules": {"file": "{apps_root}/forge/config.json", "key": "forge_additional_modules",
                                             "categories": ["VAE", "text_encoder"]}},
                  "dir_args": [["--ckpt-dir", "Stable-diffusion"], ["--vae-dir", "VAE"]]},
    }


class Env:
    """一時フォルダの設定・ダミーのアプリ一式。close() で消す。"""

    def __init__(self, services=None, **top):
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-test-"))
        self.machine = self.tmp / "machine.json"
        data = {"host": "127.0.0.1", "port": 5000, "token": "", "root": str(self.tmp), "state_dir": str(self.tmp / "state"),
                "services": services or default_services(self.tmp)}
        data.update(top)
        self.machine.write_text(json.dumps(data))
        (self.tmp / "presets.json").write_text("[]")
        config.init(self.machine)
        self._reset_state()
        # ダミーのアプリ
        make_executable(self.apps / "llama.cpp/build/bin/llama-server", "#!/bin/sh\necho 'version: 0.9.9 (build 4242, commit abcdef0)'\n")
        (self.apps / "Strata/serve").mkdir(parents=True, exist_ok=True)
        (self.apps / "Strata/serve/server.py").write_text("")
        make_executable(self.apps / "Strata/run-a.sh", "#!/bin/sh\nexec sleep 30\n")
        (self.apps / "ComfyUI").mkdir(parents=True, exist_ok=True)
        (self.apps / "ComfyUI/main.py").write_text("")

    @property
    def apps(self):
        return config.ROOTS.apps

    @property
    def models(self):
        return config.ROOTS.models

    def _reset_state(self):
        from patchbay.core import process
        from patchbay.downloads import engine
        process.RUN.clear()
        engine.DL.clear()

    def touch(self, rel, size=10):
        p = self.models / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)
        return p

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class EnvTest(unittest.TestCase):
    """setUp で Env を作り、tearDown で消す。"""
    services = None

    def setUp(self):
        self.env = Env(self.services)
        self.addCleanup(self.env.close)
