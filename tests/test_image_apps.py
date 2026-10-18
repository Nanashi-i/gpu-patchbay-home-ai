import json
import os
import unittest
from unittest import mock

from helpers import EnvTest

from patchbay.apps import app_for
from patchbay.apps._common import sets
from patchbay.core import config
from patchbay.core.errors import HubError


class SetsTest(EnvTest):
    def setUp(self):
        super().setUp()
        for rel in ("comfyui/checkpoints/a.safetensors", "comfyui/diffusion_models/m.safetensors", "comfyui/vae/v1.safetensors",
                    "comfyui/vae/v2.safetensors", "comfyui/loras/l.safetensors"):
            self.env.touch(rel)

    def make_set(self, **files):
        return sets.upsert_set({"id": "s1", "name": "Qwen", "service": "comfy", "files": files})

    def test_upsert_validates(self):
        with self.assertRaises(HubError):
            sets.upsert_set({"name": "", "service": "comfy"})
        with self.assertRaises(HubError):
            sets.upsert_set({"name": "x", "service": "llama"})            # view のないサービス
        with self.assertRaises(HubError):
            sets.upsert_set({"name": "x", "service": "comfy", "files": {"vae": ["../../etc/passwd"]}})
        with self.assertRaises(HubError):
            sets.upsert_set({"name": "x", "service": "comfy", "files": {"nothing": ["a"]}})

    def test_build_view_links_only_the_set_plus_common(self):
        self.make_set(diffusion_models=["m.safetensors"], vae=["v1.safetensors"])
        sets.set_common("comfy", {"vae": ["v2.safetensors"]})
        info = sets.build_view("comfy", "s1")
        vdir = self.env.models / ".view/comfyui"
        links = sorted(str(p.relative_to(vdir)) for p in vdir.rglob("*") if p.is_symlink())
        self.assertEqual(links, ["diffusion_models/m.safetensors", "vae/v1.safetensors", "vae/v2.safetensors"])
        self.assertEqual((info["count"], info["missing"]), (3, []))
        # 作り直すと、セットから外したものは消える
        self.make_set(vae=["v1.safetensors"])
        sets.set_common("comfy", {})
        sets.build_view("comfy", "s1")
        self.assertEqual([p.name for p in vdir.rglob("*") if p.is_symlink()], ["v1.safetensors"])

    def test_missing_files_are_reported(self):
        self.make_set(vae=["gone.safetensors"])
        self.assertEqual(sets.build_view("comfy", "s1")["missing"], ["vae/gone.safetensors"])

    def test_view_refuses_real_files(self):
        self.make_set(vae=["v1.safetensors"])
        vdir = self.env.models / ".view/comfyui/vae"
        vdir.mkdir(parents=True)
        (vdir / "real.safetensors").write_text("x")
        with self.assertRaises(HubError):
            sets.build_view("comfy", "s1")

    def test_add_to_set_and_common(self):
        self.make_set()
        sets.add_to_set("comfy", "s1", "vae", "v1.safetensors")
        sets.add_to_set("comfy", "_common", "loras", "l.safetensors")
        d = sets.load_sets()
        self.assertEqual(d["sets"][0]["files"], {"vae": ["v1.safetensors"]})
        self.assertEqual(d["common"]["comfy"], {"loras": ["l.safetensors"]})


class ComfyAppTest(EnvTest):
    def setUp(self):
        super().setUp()
        self.env.touch("comfyui/vae/v1.safetensors")
        sets.upsert_set({"id": "s1", "name": "S", "service": "comfy", "files": {"vae": ["v1.safetensors"]}})
        self.app = app_for("comfy")
        self.yaml = self.env.apps / "ComfyUI/extra_model_paths.yaml"

    def test_yaml_points_to_view_then_back_to_all(self):
        self.yaml.write_text("original: 1\n")
        info = self.app.apply_view("comfy", "s1")
        self.assertEqual(info["name"], "S")
        self.assertIn(f"base_path: {self.env.models}/.view/comfyui/", self.yaml.read_text())
        self.assertEqual((self.yaml.parent / "extra_model_paths.yaml.bak-patchbay").read_text(), "original: 1\n")   # 初回だけ元を残す
        self.app.after_stop("comfy")                                    # 停止後は「全部見える」へ戻す
        self.assertIn(f"base_path: {self.env.models}/comfyui/", self.yaml.read_text())

    def test_prepare_returns_set_name_and_log(self):
        prepared = self.app.prepare("comfy", {"model_set": "s1"}, [], {}, lambda m: None)
        self.assertEqual(prepared.set_name, "S")
        self.assertTrue(prepared.log[0].startswith("# model set: S"))
        self.assertEqual(self.app.prepare("comfy", {}, [], {}, lambda m: None).log, ["# model set: すべて表示"])

    def test_models_listing_shows_sets_and_links(self):
        self.env.touch("forge/Stable-diffusion/x.safetensors")
        (self.env.models / "comfyui/checkpoints").mkdir(parents=True, exist_ok=True)
        (self.env.models / "comfyui/checkpoints/x.safetensors").symlink_to(self.env.models / "forge/Stable-diffusion/x.safetensors")
        cats = {c["key"]: c for c in self.app.models("comfy")["categories"]}
        self.assertEqual(cats["vae"]["items"][0]["sets"], ["S"])
        self.assertEqual(cats["checkpoints"]["items"][0]["link"], str(self.env.models / "forge/Stable-diffusion/x.safetensors"))


class ForgeAppTest(EnvTest):
    def setUp(self):
        super().setUp()
        forge = self.env.apps / "forge"
        forge.mkdir(parents=True)
        (forge / "launch.py").write_text("")
        self.cfg = forge / "config.json"
        self.env.touch("forge/VAE/sdxl.safetensors")
        self.env.touch("forge/Stable-diffusion/p.safetensors")
        sets.upsert_set({"id": "f1", "name": "SDXL", "service": "forge",
                         "files": {"Stable-diffusion": ["p.safetensors"], "VAE": ["sdxl.safetensors"]}})
        self.app = app_for("forge")
        patcher = mock.patch("patchbay.apps.base.prepare_webui")   # git・venv の確認は、ここでは行わない(launcher のテストは別)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saved_modules_are_limited_to_the_set(self):
        self.cfg.write_text(json.dumps({"other": 1, "forge_additional_modules": [
            "/old/forge/VAE/qwen.safetensors", "/old/forge/VAE/sdxl.safetensors"]}))
        prepared = self.app.prepare("forge", {"model_set": "f1"}, [], {}, lambda m: None)
        saved = json.loads(self.cfg.read_text())
        self.assertEqual(saved["other"], 1)
        self.assertEqual([os.path.basename(p) for p in saved["forge_additional_modules"]], ["sdxl.safetensors"])
        self.assertIn(".view/forge/VAE/", saved["forge_additional_modules"][0])
        self.assertTrue((self.cfg.parent / "config.json.bak-patchbay").exists())
        self.assertTrue(any("removed: /old/forge/VAE/qwen.safetensors" in l for l in prepared.log))

    def test_all_mode_does_not_touch_config(self):
        self.cfg.write_text(json.dumps({"forge_additional_modules": ["/x/qwen.safetensors"]}))
        self.app.prepare("forge", {}, [], {}, lambda m: None)
        self.assertEqual(json.loads(self.cfg.read_text())["forge_additional_modules"], ["/x/qwen.safetensors"])

    def test_unreadable_or_renamed_setting_is_left_alone(self):
        self.cfg.write_text("not json")
        self.app.prepare("forge", {"model_set": "f1"}, [], {}, lambda m: None)
        self.assertEqual(self.cfg.read_text(), "not json")
        self.cfg.write_text(json.dumps({"renamed_key": []}))
        self.app.prepare("forge", {"model_set": "f1"}, [], {}, lambda m: None)
        self.assertEqual(json.loads(self.cfg.read_text()), {"renamed_key": []})

    def test_dir_args_point_to_view_or_real_dirs(self):
        cmd = ["python", "launch.py"]
        self.app.prepare("forge", {"model_set": "f1"}, cmd, {}, lambda m: None)
        self.assertEqual(cmd[2:], ["--ckpt-dir", f"{self.env.models}/.view/forge/Stable-diffusion",
                                   "--vae-dir", f"{self.env.models}/.view/forge/VAE"])
        cmd = ["python", "launch.py"]
        self.app.prepare("forge", {}, cmd, {}, lambda m: None)
        self.assertEqual(cmd[2:], ["--ckpt-dir", f"{self.env.models}/forge/Stable-diffusion",
                                   "--vae-dir", f"{self.env.models}/forge/VAE"])


class StrataModelsTest(EnvTest):
    def test_entries_and_references(self):
        self.env.touch("strata/packs/dense.bin", 4)
        self.env.touch("strata/model.gguf", 6)
        (self.env.apps / "Strata/strata-a.json").write_text(json.dumps({"p": f"{self.env.models}/strata/packs/x"}))
        r = app_for("strata").models("strata")
        items = {i["name"]: i for i in r["items"]}
        self.assertEqual(r["kind"], "entries")
        self.assertEqual(items["packs"]["used_by"], ["strata-a.json"])
        self.assertEqual(items["model.gguf"]["used_by"], [])
        self.assertTrue(items["packs"]["rm"].startswith("rm -rv -- "))


if __name__ == "__main__":
    unittest.main()
