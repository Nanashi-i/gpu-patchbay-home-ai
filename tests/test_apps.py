import json
import os
import unittest
from unittest import mock

from helpers import EnvTest, make_executable

from patchbay.apps import app_for, app_id_of
from patchbay.core import secrets as secret_store
from patchbay.core.errors import HubError


class RegistryTest(EnvTest):
    def test_app_ids(self):
        self.assertEqual([app_id_of(n) for n in ("llama", "strata", "comfy", "forge")], ["llama", "strata", "comfyui", "forge"])

    def test_explicit_app_key_wins_and_unknown_falls_back(self):
        from patchbay.core import config
        config.CFG["services"]["strata"]["app"] = "forge"
        self.assertEqual(app_id_of("strata"), "forge")
        config.CFG["services"]["strata"]["app"] = "nothing"
        self.assertEqual(app_id_of("strata"), "script")


class LlamaCommandTest(EnvTest):
    def setUp(self):
        super().setUp()
        self.env.touch("llama/test.gguf")
        self.app = app_for("llama")

    def cmd(self, **p):
        c, cwd, env = self.app.build_command("llama", {"service": "llama", "model": "test.gguf", **p})
        return c

    def test_basic_arguments_and_metrics_added(self):
        c = self.cmd(ctx=4096, temp=0.7, top_k=20, reasoning="off")
        self.assertEqual(c[c.index("-c") + 1], "4096")
        self.assertEqual(c[c.index("--port") + 1], "18080")
        self.assertIn("-np", c)                                   # base_args
        self.assertEqual(c[c.index("--temp") + 1], "0.7")
        self.assertEqual(c[c.index("-rea") + 1], "off")
        self.assertEqual(c.count("--metrics"), 1)                 # ハブが自動で付ける

    def test_reasoning_budget(self):
        c = self.cmd(reasoning="100")
        self.assertEqual(c[c.index("--reasoning-budget") + 1], "100")
        self.assertNotIn("-rea", self.cmd(reasoning="auto"))

    def test_flags_dedupe_and_unknown(self):
        self.assertEqual(self.cmd(flags=["--jinja"], extra="--jinja -a x").count("--jinja"), 1)
        c = self.cmd(flags=["--cpu-moe"], extra="-cmoe")            # 別名も重複させない
        self.assertEqual(c.count("--cpu-moe") + c.count("-cmoe"), 1)
        with self.assertRaises(HubError):
            self.cmd(flags=["--evil"])

    def test_extra_is_split_on_whitespace_only(self):
        c = self.cmd(extra=r"-ot blk\.(0|1)\.ffn_.*=CPU")
        self.assertIn(r"blk\.(0|1)\.ffn_.*=CPU", c)               # 正規表現を壊さない

    def test_missing_model_and_binary(self):
        with self.assertRaises(HubError):
            self.app.build_command("llama", {"service": "llama", "model": "nothing.gguf"})
        with self.assertRaises(HubError):
            self.app.build_command("llama", {"service": "llama", "model": "test.gguf", "server_dir": str(self.env.tmp / "nope")})

    def test_metrics_can_be_disabled_by_config(self):
        from patchbay.core import config
        config.CFG["services"]["llama"]["metrics"] = False
        self.assertNotIn("--metrics", self.cmd())

    def test_version_parses_binary_output(self):
        self.assertEqual(self.app.version("llama")["short"], "build 4242")

    def test_models_listing_shards_and_mmproj(self):
        self.env.touch("llama/big-00001-of-00002.gguf", 5)
        self.env.touch("llama/big-00002-of-00002.gguf", 7)
        self.env.touch("llama/mmproj-x.gguf", 3)
        items = {i["path"]: i for i in self.app.models("llama")["items"]}
        self.assertIn("test.gguf", items)
        self.assertIn("big-00001-of-00002.gguf", items)
        self.assertNotIn("big-00002-of-00002.gguf", items)         # 分割は先頭だけ
        self.assertEqual(items["big-00001-of-00002.gguf"]["size"], 12)
        self.assertNotIn("mmproj-x.gguf", items)                   # mmproj は、モデルとして出さない
        self.assertTrue(items["big-00001-of-00002.gguf"]["rm"].startswith("rm -v -- "))   # 削除はコマンドを見せるだけ


class ScriptCommandTest(EnvTest):
    def test_relative_cmd_resolves_against_service_dir(self):
        c, cwd, env = app_for("strata").build_command("strata", {"service": "strata", "cmd": "run-a.sh"}) if self._with_key() else (None, None, None)
        self.assertEqual(c, [str(self.env.apps / "Strata/run-a.sh")])
        self.assertEqual(env["STRATA_API_KEY"], "k123")

    def _with_key(self):
        secret_store.set_secret("strata", {"key": "k123"})
        return True

    def test_api_key_required(self):
        with self.assertRaises(HubError) as cm:
            app_for("strata").build_command("strata", {"service": "strata", "cmd": "run-a.sh"})
        self.assertIn("APIキー", str(cm.exception))

    def test_missing_script(self):
        secret_store.set_secret("strata", {"key": "k"})
        with self.assertRaises(HubError):
            app_for("strata").build_command("strata", {"service": "strata", "cmd": "nothing.sh"})

    def test_launcher_command_uses_port_placeholder(self):
        forge = self.env.apps / "forge"
        (forge).mkdir(parents=True)
        (forge / "launch.py").write_text("")
        c, cwd, env = app_for("forge").build_command("forge", {"service": "forge"})
        self.assertEqual(c[-3:], ["--port", "17860", "--api"])
        self.assertTrue(c[0].endswith("venv/bin/python"))

    def test_installed_uses_marker(self):
        self.assertTrue(app_for("strata").installed("strata"))
        self.assertTrue(app_for("llama").installed("llama"))
        self.assertFalse(app_for("forge").installed("forge"))


class SecretsTest(EnvTest):
    def test_secret_file_permissions_and_generate(self):
        r = secret_store.set_secret("strata", {"generate": True})
        self.assertTrue(r["key"])
        self.assertEqual(oct(os.stat(secret_store.secrets_file()).st_mode)[-3:], "600")
        self.assertEqual(secret_store.set_secret("strata", {"key": "abc"})["key"], None)   # 生成したとき以外は返さない
        secret_store.set_secret("strata", {"clear": True})
        self.assertNotIn("strata", secret_store.load_secrets())

    def test_service_without_api_key_is_rejected(self):
        with self.assertRaises(HubError):
            secret_store.set_secret("llama", {"key": "x"})

    def test_token_source_priority(self):
        from patchbay.core import config
        config.CFG["hf_token"] = "from-config"
        self.assertEqual(secret_store.token_source("hf"), "config")
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            secret_store.set_token("hf", {"token": "from-app"})   # 通信できなくても、保存はする
        self.assertEqual(secret_store.token_source("hf"), "app")
        self.assertEqual(secret_store.get_token("hf"), "from-app")


if __name__ == "__main__":
    unittest.main()
