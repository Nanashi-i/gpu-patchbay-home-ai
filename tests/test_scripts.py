import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(shutil.which("setsid") and Path("/proc/self/stat").exists(), "Linux の setsid が必要です")
class StartStopScriptsTest(unittest.TestCase):
    """start.sh / stop.sh を、別の設定(PATCHBAY_MACHINE)・別のポートで、実際に動かして確認する(本物のハブには触れない)。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-scripts-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.port = free_port()
        (self.tmp / "machine.json").write_text(json.dumps({"host": "127.0.0.1", "port": self.port, "state_dir": str(self.tmp / "state"),
                                                           "root": str(self.tmp / "root"), "services": {}}))
        self.env = {**os.environ, "PATCHBAY_MACHINE": str(self.tmp / "machine.json")}
        self.addCleanup(lambda: self.run_sh("stop.sh"))

    def run_sh(self, name, *args, env=None):
        return subprocess.run([str(ROOT / name), *args], env=env or self.env, capture_output=True, text=True, timeout=60)

    def state_ok(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/state", timeout=5) as r:
            return r.status == 200

    def test_start_in_background_then_stop(self):
        r = self.run_sh("start.sh")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("起動しました", r.stdout)
        self.assertIn(f"http://127.0.0.1:{self.port}", r.stdout)
        self.assertRegex(r.stdout, r"PID: \d+")
        self.assertTrue(self.state_ok())
        pid = int((self.tmp / "state" / "hub.pid").read_text())

        again = self.run_sh("start.sh")                                   # 二重に起動しない
        self.assertEqual(again.returncode, 0)
        self.assertIn(f"PID: {pid}", again.stdout)
        self.assertIn("すでに起動", again.stdout)
        self.assertIn("稼働中", self.run_sh("start.sh", "--status").stdout)

        stop = self.run_sh("stop.sh")
        self.assertEqual(stop.returncode, 0, stop.stdout + stop.stderr)
        self.assertIn(f"PID: {pid}", stop.stdout)
        with self.assertRaises(OSError):
            self.state_ok()
        self.assertFalse((self.tmp / "state" / "hub.pid").exists())
        self.assertIn("起動していません", self.run_sh("stop.sh").stdout)

    def test_port_in_use_and_broken_config_are_reported(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", self.port))
            s.listen()
            r = self.run_sh("start.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ポート", r.stderr)
        (self.tmp / "machine.json").write_text('{"port": "x", "services": {}}')
        r = self.run_sh("start.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("port", r.stderr)

    def test_a_stale_pid_file_is_not_trusted(self):
        (self.tmp / "state").mkdir()
        (self.tmp / "state" / "hub.pid").write_text(str(os.getpid()))        # 生きているが、ハブではないプロセス
        self.assertIn("起動していません", self.run_sh("stop.sh").stdout)
        self.assertEqual(os.kill(os.getpid(), 0), None)                    # 無関係なプロセスを、止めていない


if __name__ == "__main__":
    unittest.main()
