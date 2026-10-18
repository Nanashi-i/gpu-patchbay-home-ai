import json
import unittest
from pathlib import Path

from helpers import Env, EnvTest, config  # noqa: F401

from patchbay.core import schema
from patchbay.core.errors import HubError
from patchbay.core.machine_schema import MACHINE
from patchbay.core.schema import Bool, DictOf, Int, ListOf, Nullable, Num, Obj, OneOf, Pair, Str


def errors(spec, value):
    return schema.check(spec, value)[0]


class PartsTest(unittest.TestCase):
    def test_str(self):
        self.assertEqual(errors(Str(1, 5), "abc"), [])
        for bad in ("", "abcdef", 1, None, ["a"], "a\nb", "a\x00b", "a\x7f"):
            self.assertTrue(errors(Str(1, 5), bad), repr(bad))
        self.assertEqual(errors(Str(0, 10, multiline=True), "a\nb"), [])
        self.assertTrue(errors(Str(enum=["x", "y"]), "z"))
        self.assertTrue(errors(Str(pattern=r"[a-z]+"), "A1"))
        self.assertEqual(errors(Str(pattern=r"[a-z]+"), "abc"), [])

    def test_numbers_do_not_accept_bool_or_strings(self):
        self.assertEqual(errors(Int(1, 10), 5), [])
        for bad in (True, "5", 5.5, 0, 11, None):
            self.assertTrue(errors(Int(1, 10), bad), repr(bad))
        self.assertEqual(errors(Num(0, 1), 0.5), [])
        for bad in (True, "0.5", 2, float("nan"), float("inf")):
            self.assertTrue(errors(Num(0, 1), bad), repr(bad))

    def test_containers(self):
        self.assertEqual(errors(ListOf(Str(1, 3)), ["a", "bc"]), [])
        self.assertTrue(errors(ListOf(Str(1, 3)), "ab"))
        self.assertTrue(errors(ListOf(Str(1, 3)), ["a", 1]))
        self.assertTrue(errors(ListOf(Int(), 2), [1, 2, 3]))
        self.assertEqual(errors(Pair(Str(), Str()), ["a", "b"]), [])
        self.assertTrue(errors(Pair(Str(), Str()), ["a"]))
        self.assertTrue(errors(DictOf(Int()), {"a": "x"}))
        self.assertEqual(errors(OneOf(Int(), Str(pattern="auto")), "auto"), [])
        self.assertTrue(errors(OneOf(Int(), Str(pattern="auto")), "other"))
        self.assertEqual(errors(Nullable(Int()), None), [])

    def test_obj_required_and_unknown_keys(self):
        spec = Obj({"a": Int()}, required=["a"])
        e, w = schema.check(spec, {"b": 1})
        self.assertEqual((len(e), len(w)), (1, 1))                      # 必須の欠落はエラー、未知のキーは警告
        self.assertEqual(schema.check(Obj({}, extra="ignore"), {"x": 1}), ([], []))
        self.assertTrue(schema.check(Obj({}, extra="error"), {"x": 1})[0])

    def test_require_collects_messages(self):
        with self.assertRaises(HubError) as cm:
            schema.require(Obj({"a": Int(), "b": Int()}), {"a": "x", "b": "y"}, "設定")
        self.assertIn("a:", str(cm.exception))
        self.assertIn("b:", str(cm.exception))


class MachineSchemaTest(unittest.TestCase):
    def machine(self, **patch):
        base = json.loads((Path(__file__).resolve().parents[1] / "machine.example.json").read_text())
        for k, v in patch.items():
            base[k] = v
        return base

    def test_example_config_is_valid_without_warnings(self):
        self.assertEqual(schema.check(MACHINE, self.machine()), ([], []))

    def test_type_errors_are_rejected(self):
        bad = {"port": "5000", "host": 1, "token": None, "services": []}
        for k, v in bad.items():
            self.assertTrue(errors(MACHINE, self.machine(**{k: v})), k)

    def test_service_fields(self):
        m = self.machine()
        svc = m["services"]["llama"]
        svc["port"] = 99999
        svc["dir"] = ["not", "a", "string"]
        svc["launcher"] = {"env": {"bad name": "x"}}
        svc["exts"] = ["gguf"]
        e = errors(MACHINE, m)
        self.assertTrue(any("port" in x for x in e) and any("dir" in x for x in e) and any("exts" in x for x in e))

    def test_names_cannot_escape_folders(self):
        m = self.machine()
        m["services"]["../evil"] = m["services"]["llama"]
        self.assertTrue(errors(MACHINE, m))
        m = self.machine()
        m["services"]["comfy"]["categories"][0]["key"] = "../../etc"
        self.assertTrue(errors(MACHINE, m))
        m = self.machine()
        m["services"]["comfy"]["categories"][0]["dir"] = "a/b"
        self.assertTrue(errors(MACHINE, m))

    def test_control_characters_are_rejected(self):
        m = self.machine()
        m["services"]["llama"]["base_args"] = "-np 1\n--evil"
        self.assertTrue(errors(MACHINE, m))

    def test_unknown_keys_are_warnings_not_errors(self):
        m = self.machine()
        m["services"]["llama"]["porrt"] = 1
        e, w = schema.check(MACHINE, m)
        self.assertEqual(e, [])
        self.assertTrue(any("porrt" in x for x in w))


class InitValidationTest(unittest.TestCase):
    def test_init_refuses_wrong_types_and_prints_warnings(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        d = Path(tempfile.mkdtemp())
        data = {"state_dir": str(d / "s"), "port": "oops", "services": {}}
        (d / "machine.json").write_text(json.dumps(data))
        with self.assertRaises(HubError) as cm:
            config.init(d / "machine.json")
        self.assertIn("port", str(cm.exception))
        data = {"state_dir": str(d / "s"), "typo_key": 1, "services": {}}
        (d / "machine.json").write_text(json.dumps(data))
        buf = io.StringIO()
        with redirect_stdout(buf):
            config.init(d / "machine.json")
        self.assertIn("typo_key", buf.getvalue())


class SaveValidationTest(EnvTest):
    def test_saved_settings_are_validated_as_a_whole(self):
        from patchbay.core.services import update_service_config
        with self.assertRaises(HubError):
            update_service_config("llama", {"dir": "x\nbad"})
        self.assertEqual(json.loads(self.env.machine.read_text())["services"]["llama"]["dir"], "{apps_root}/llama.cpp")   # 保存されない
        update_service_config("llama", {"dir": "~/elsewhere"})
        self.assertEqual(json.loads(self.env.machine.read_text())["services"]["llama"]["dir"], "~/elsewhere")


if __name__ == "__main__":
    unittest.main()
