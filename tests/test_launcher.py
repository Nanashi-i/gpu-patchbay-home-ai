import unittest
from unittest import mock

from helpers import EnvTest

from patchbay.apps._common import launcher
from patchbay.core import config
from patchbay.core.errors import HubError


class LauncherTest(EnvTest):
    def setUp(self):
        super().setUp()
        self.svc = config.service("forge")
        self.dir = self.env.apps / "forge"
        self.dir.mkdir(parents=True)
        (self.dir / "launch.py").write_text("")

    def make_venv(self, version="3.11"):
        py = self.dir / "venv/bin/python"
        py.parent.mkdir(parents=True)
        py.write_text(f"#!/bin/sh\necho {version}\n")
        py.chmod(0o755)

    def test_command_and_missing_script(self):
        cmd, cwd = launcher.webui_command(self.svc)
        self.assertEqual(cmd[1:3], ["-u", str(self.dir / "launch.py")])
        (self.dir / "launch.py").unlink()
        with self.assertRaises(HubError):
            launcher.webui_command(self.svc)

    def test_git_is_required(self):
        with mock.patch("shutil.which", return_value=None), self.assertRaises(HubError) as cm:
            launcher.prepare_webui(self.svc, {}, lambda m: None)
        self.assertIn("git", str(cm.exception))

    def test_venv_not_created_when_auto_venv_is_false(self):
        self.svc["launcher"]["auto_venv"] = False
        with mock.patch("shutil.which", return_value="/usr/bin/git"), self.assertRaises(HubError) as cm:
            launcher.prepare_webui(self.svc, {}, lambda m: None)
        self.assertIn("venv が見つかりません", str(cm.exception))
        self.assertFalse((self.dir / "venv").exists())

    def test_failed_venv_creation_leaves_nothing_behind(self):
        failed = mock.Mock(returncode=1, stderr="no ensurepip", stdout="")
        with mock.patch("shutil.which", return_value="/usr/bin/git"), mock.patch("subprocess.run", return_value=failed):
            with self.assertRaises(HubError):
                launcher.prepare_webui(self.svc, {}, lambda m: None)
        self.assertFalse((self.dir / "venv").exists())

    def test_python_version_check_and_env(self):
        self.make_venv("3.14")
        self.svc["launcher"]["python_versions"] = ["3.10", "3.11"]
        with mock.patch("shutil.which", return_value="/usr/bin/git"), self.assertRaises(HubError):
            launcher.prepare_webui(self.svc, {}, lambda m: None)
        self.svc["launcher"]["args"] += " --skip-python-version-check"   # 引数で許可すれば、続行する
        env = {}
        with mock.patch("shutil.which", return_value="/usr/bin/git"):
            launcher.prepare_webui(self.svc, env, lambda m: None)
        self.assertEqual(env["NO_TCMALLOC"], "True")


if __name__ == "__main__":
    unittest.main()
