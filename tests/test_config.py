import json
import unittest

from helpers import Env, EnvTest, config  # noqa: F401

from patchbay.core.errors import HubError


class ConfigTest(EnvTest):
    def test_expand_variables(self):
        self.assertEqual(config.expand("{apps_root}/x"), f"{self.env.apps}/x")
        self.assertEqual(config.expand("{models_root}/x"), f"{self.env.models}/x")
        self.assertEqual(config.expand("{models_dir}/a", "llama"), f"{self.env.models}/llama/a")
        self.assertEqual(config.expand("{home}/z"), f"{config.HOME}/z")

    def test_roots_defaults_follow_root(self):
        self.assertEqual(self.env.apps, self.env.tmp / "ai-apps")
        self.assertEqual(self.env.models, self.env.tmp / "ai-models")

    def test_service_dirs(self):
        self.assertEqual(config.models_dir("llama"), self.env.models / "llama")
        self.assertEqual(config.cat_dir("comfy", "vae"), self.env.models / "comfyui" / "vae")
        with self.assertRaises(HubError):
            config.cat_dir("comfy", "nothing")
        with self.assertRaises(HubError):
            config.service("nothing")

    def test_ensure_dirs_creates_category_folders(self):
        config.ensure_dirs()
        self.assertTrue((self.env.models / "forge" / "VAE").is_dir())
        self.assertTrue((self.env.models / "llama").is_dir())


class RootPriorityTest(unittest.TestCase):
    def test_apps_root_overrides_root_and_service_overrides_both(self):
        env = Env(apps_root="{root}/custom-apps")
        self.addCleanup(env.close)
        self.assertEqual(config.ROOTS.apps, env.tmp / "custom-apps")
        self.assertEqual(config.to_path("{apps_root}/a"), env.tmp / "custom-apps" / "a")

    def test_first_run_copies_examples(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        (d / "machine.example.json").write_text(json.dumps({"state_dir": str(d / "s"), "services": {}}))
        (d / "presets.example.json").write_text("[]")
        config.init(d / "machine.json")
        self.assertTrue((d / "machine.json").exists() and (d / "presets.json").exists())
        with self.assertRaises(HubError):
            config.init(d / "nothing" / "machine.json")


if __name__ == "__main__":
    unittest.main()
