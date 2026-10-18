import unittest

from helpers import EnvTest

from patchbay.core import presets
from patchbay.core.errors import HubError


class PresetTest(EnvTest):
    def test_upsert_filters_unknown_fields_and_makes_id(self):
        p = presets.upsert_preset({"name": "My Model", "service": "llama", "model": "a.gguf", "ctx": 4096,
                                   "evil": "x", "note": "", "flags": []})
        self.assertNotIn("evil", p)
        self.assertNotIn("note", p)    # 空の値は保存しない
        self.assertNotIn("flags", p)   # 空のリストも保存しない
        self.assertTrue(p["id"].startswith("my-model-"))
        self.assertEqual(presets.get_preset(p["id"])["ctx"], 4096)

    def test_requires_name_and_known_service(self):
        with self.assertRaises(HubError):
            presets.upsert_preset({"name": "", "service": "llama"})
        with self.assertRaises(HubError):
            presets.upsert_preset({"name": "x", "service": "nothing"})

    def test_favorite_is_unique_per_model(self):
        a = presets.upsert_preset({"name": "A", "service": "llama", "model": "m.gguf", "favorite": True})
        b = presets.upsert_preset({"name": "B", "service": "llama", "model": "m.gguf", "favorite": True})
        c = presets.upsert_preset({"name": "C", "service": "llama", "model": "other.gguf", "favorite": True})
        self.assertFalse(presets.get_preset(a["id"]).get("favorite"))
        self.assertTrue(presets.get_preset(b["id"]).get("favorite"))
        self.assertTrue(presets.get_preset(c["id"]).get("favorite"))

    def test_fields_are_declared_per_app(self):
        self.assertIn("ctx", presets.fields_for("llama"))
        self.assertNotIn("ctx", presets.fields_for("strata"))      # llama の項目は、ほかのアプリでは受け付けない
        self.assertIn("cmd", presets.fields_for("strata"))
        self.assertIn("model_set", presets.fields_for("comfy"))
        self.assertNotIn("model_set", presets.fields_for("strata"))
        p = presets.upsert_preset({"name": "S", "service": "strata", "cmd": "run-a.sh", "ctx": 4096})
        self.assertNotIn("ctx", p)

    def test_types_are_validated(self):
        bad = [{"ctx": "big"}, {"ctx": True}, {"ctx": 10}, {"temp": 99}, {"top_p": "x"}, {"reasoning": "$(rm -rf)"},
               {"ngl": "lots"}, {"flags": "--jinja"}, {"extra": 123}, {"model": ["a"]}, {"model": "a\nb"}, {"favorite": "yes"}]
        for extra in bad:
            with self.assertRaises(HubError, msg=str(extra)):
                presets.upsert_preset({"name": "X", "service": "llama", **extra})
        for ok in ({"ctx": 8192}, {"ngl": "auto"}, {"ngl": 20}, {"reasoning": "-1"}, {"reasoning": "100"}, {"temp": 1}):
            presets.upsert_preset({"name": "X", "service": "llama", **ok})
        with self.assertRaises(HubError):
            presets.upsert_preset({"id": "../evil", "name": "X", "service": "llama"})      # id にパスは使えない
        with self.assertRaises(HubError):
            presets.upsert_preset({"name": "X", "service": "comfy", "model_set": "a/b"})

    def test_hand_edited_presets_file_is_checked_before_use(self):
        import json
        (self.env.tmp / "presets.json").write_text(json.dumps([{"id": "p1", "name": "X", "service": "llama", "ctx": "oops"}]))
        with self.assertRaises(HubError):
            presets.get_preset("p1")

    def test_delete_and_missing(self):
        p = presets.upsert_preset({"name": "A", "service": "llama"})
        presets.delete_preset(p["id"])
        with self.assertRaises(HubError):
            presets.get_preset(p["id"])


if __name__ == "__main__":
    unittest.main()
