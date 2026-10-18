import json
import time
import unittest
from unittest import mock

from helpers import EnvTest, make_executable

from patchbay.core import lifecycle, process, secrets as secret_store
from patchbay.core.errors import HubError
from patchbay.core.presets import upsert_preset


def wait_until(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class ProcessTest(EnvTest):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.stop_all)
        make_executable(self.env.apps / "ComfyUI/run-b.sh", "#!/bin/sh\nexec sleep 30\n")
        secret_store.set_secret("strata", {"key": "k"})

    def stop_all(self):
        for name in list(process.RUN):
            process.stop_service(name)

    def start(self, preset):
        lifecycle.start_preset(preset["id"])
        self.assertTrue(wait_until(lambda: not process.OPS["busy"]), "操作が終わらない")
        self.assertEqual(process.OPS["error"], "")

    def test_spawn_status_and_stop(self):
        process.spawn("strata", ["sleep", "30"], self.env.tmp, {}, {"preset": "p", "pname": "N", "model": None, "set": None}, ["# header"])
        st = process.service_status("strata")
        self.assertEqual((st["state"], st["pname"]), ("starting", "N"))      # ポートが開くまでは「起動中」
        self.assertIn("# header", (self.env.tmp / "state/strata.log").read_text())
        process.stop_service("strata")
        self.assertEqual(process.service_status("strata")["state"], "stopped")
        self.assertNotIn("strata", process.RUN)

    def test_start_preset_records_and_group_exclusion(self):
        a = upsert_preset({"name": "A", "service": "strata", "cmd": "run-a.sh"})
        b = upsert_preset({"name": "B", "service": "comfy", "cmd": "run-b.sh"})
        self.start(a)
        self.assertEqual(process.service_status("strata")["preset"], a["id"])
        self.start(b)                                                        # 同じグループなので、strata は止まる
        self.assertTrue(wait_until(lambda: process.service_status("strata")["state"] == "stopped"))
        self.assertEqual(process.service_status("comfy")["pname"], "B")

    def test_adhoc_params_start(self):
        lifecycle.start_preset(None, {"service": "comfy", "cmd": "run-b.sh", "evil": 1}, "一時")
        self.assertTrue(wait_until(lambda: not process.OPS["busy"]))
        self.assertEqual(process.service_status("comfy")["pname"], "一時")

    def test_validation_errors_are_synchronous(self):
        with self.assertRaises(HubError):
            lifecycle.start_preset("nothing")
        p = upsert_preset({"name": "X", "service": "strata", "cmd": "nothing.sh"})
        with self.assertRaises(HubError):
            lifecycle.start_preset(p["id"])
        from patchbay.core import config
        config.CFG["services"]["strata"]["enabled"] = False
        q = upsert_preset({"name": "Y", "service": "strata", "cmd": "run-a.sh"})
        with self.assertRaises(HubError) as cm:
            lifecycle.start_preset(q["id"])
        self.assertIn("使わない", str(cm.exception))

    def test_only_one_operation_at_a_time(self):
        self.assertTrue(process.op_lock.acquire(blocking=False))
        try:
            with self.assertRaises(HubError):
                process.run_op("x", lambda: None)
        finally:
            process.op_lock.release()

    def test_shared_port_does_not_confuse_status(self):
        from patchbay.core import config
        config.CFG["services"]["comfy"]["port"] = config.CFG["services"]["strata"]["port"]      # 同じポート
        process.spawn("strata", ["sleep", "30"], self.env.tmp, {}, {"preset": "p", "pname": "N", "model": None, "set": None})
        with mock.patch.object(process, "port_open", return_value=True):
            self.assertEqual(process.service_status("strata")["state"], "running")
            st = process.service_status("comfy")
            self.assertEqual((st["state"], st["external"]), ("stopped", False))   # ハブの記録上、動いているのは strata だけ

    def test_restore_run_keeps_only_live_processes(self):
        import os
        (self.env.tmp / "state/running.json").write_text(json.dumps({
            "strata": {"pid": os.getpid(), "preset": "p", "started": 1}, "comfy": {"pid": 2 ** 22 + 12345, "preset": "q", "started": 1}}))
        process.RUN.clear()
        process.restore_run()
        self.assertEqual(sorted(process.RUN), ["strata"])
        process.RUN.clear()


if __name__ == "__main__":
    unittest.main()
