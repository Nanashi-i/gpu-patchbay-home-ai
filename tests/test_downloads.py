import unittest

from helpers import EnvTest

from patchbay.apps import app_for
from patchbay.apps._common import sets
from patchbay.apps._common.categories import guess_role
from patchbay.core.errors import HubError
from patchbay.downloads import engine
from patchbay.downloads.hf import parse_hf
from patchbay.downloads.safety import safe_dest


class GuessTest(unittest.TestCase):
    def test_folder_names_win(self):
        cases = {"split_files/diffusion_models/q.safetensors": "diffusion", "split_files/text_encoders/te.safetensors": "textenc",
                 "vae/ae.safetensors": "vae", "loras/x.safetensors": "lora", "checkpoints/m.safetensors": "checkpoint",
                 "model_patches/controlnet_union.safetensors": "controlnet"}
        for path, role in cases.items():
            self.assertEqual(guess_role(path), role, path)

    def test_file_names_when_no_folder(self):
        cases = {"my-lora-v1.safetensors": "lora", "sdxl.vae.safetensors": "vae", "taesd_decoder.safetensors": "vae",
                 "clip_l.safetensors": "clip", "t5xxl_fp8.safetensors": "textenc", "qwen3vl_8b.safetensors": "textenc",
                 "4x-UltraSharp.pth": "upscale", "model.gguf": "diffusion", "random.safetensors": "checkpoint"}
        for path, role in cases.items():
            self.assertEqual(guess_role(path), role, path)

    def test_parse_hf(self):
        self.assertEqual(parse_hf("https://huggingface.co/Comfy-Org/Qwen-Image-2.1"), ("Comfy-Org/Qwen-Image-2.1", "main", None))
        self.assertEqual(parse_hf("https://huggingface.co/a/b/resolve/v2/x/y.gguf"), ("a/b", "v2", "x/y.gguf"))
        self.assertEqual(parse_hf("https://huggingface.co/a/b/tree/dev"), ("a/b", "dev", None))
        self.assertIsNone(parse_hf("https://example.com/a/b"))
        self.assertIsNone(parse_hf("https://huggingface.co/onlyone"))


class SafeDestTest(EnvTest):
    def test_rejects_escape_extension_and_existing(self):
        d = self.env.models / "llama"
        d.mkdir(parents=True)
        self.assertEqual(safe_dest("llama", d, "ok.gguf"), (d / "ok.gguf").resolve())
        with self.assertRaises(HubError):
            safe_dest("llama", d, "../../outside.gguf")
        with self.assertRaises(HubError):
            safe_dest("llama", d, "bad.exe")
        (d / "there.gguf").write_text("x")
        with self.assertRaises(HubError):
            safe_dest("llama", d, "there.gguf")


class SchemeTest(EnvTest):
    def test_only_http_and_https_are_allowed(self):
        for url in ("file:///etc/passwd", "ftp://example.com/a.gguf", "javascript:alert(1)", "/etc/passwd"):
            with self.assertRaises(HubError, msg=url):
                engine.inspect(url, "llama")
            with self.assertRaises(HubError, msg=url):
                engine.enqueue({"service": "llama", "url": url, "files": [{"path": "a.gguf"}]})


class InspectTest(EnvTest):
    def test_direct_url(self):
        r = engine.inspect("https://example.com/files/model.safetensors", "comfy")
        self.assertTrue(r["direct"] and not r["need_name"])
        self.assertEqual(r["files"][0]["category"], "checkpoints")
        r = engine.inspect("https://example.com/api/download/models/123", "comfy")     # 拡張子がない → ファイル名の入力が必要
        self.assertTrue(r["need_name"])
        r = engine.inspect("https://example.com/m.gguf", "llama")
        self.assertEqual((r["categories"], r["files"][0]["category"]), ([], None))

    def test_unknown_service(self):
        with self.assertRaises(HubError):
            engine.inspect("https://example.com/m.gguf", "nothing")


class EnqueueAndDownloadTest(EnvTest):
    def setUp(self):
        super().setUp()
        engine.ALLOWED_SCHEMES = ("http", "https", "file")        # テストだけ、ローカルのファイルから取得する
        self.addCleanup(setattr, engine, "ALLOWED_SCHEMES", ("http", "https"))
        self.src = self.env.tmp / "src.safetensors"
        self.src.write_bytes(b"abc" * 1000)
        self.url = self.src.as_uri()

    def run_jobs(self):
        while not engine.DL_Q.empty():
            jid, url, dest = engine.DL_Q.get()
            engine._download(jid, url, dest)

    def test_category_download_with_link_and_set(self):
        sets.upsert_set({"id": "s1", "name": "S", "service": "comfy", "files": {}})
        engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "my.safetensors", "category": "vae"}],
                        "link": True, "set_id": "s1"})
        self.run_jobs()
        job = next(iter(engine.DL.values()))
        self.assertEqual((job["state"], job["category"], job["link"], job["set"]), ("done", "vae", True, "s1"))
        dest = self.env.models / "comfyui/vae/my.safetensors"
        self.assertEqual(dest.stat().st_size, 3000)
        self.assertFalse(dest.with_name("my.safetensors.part").exists())
        link = self.env.models / "forge/VAE/my.safetensors"                       # もう一方のサービスにも共有
        self.assertTrue(link.is_symlink() and link.resolve() == dest.resolve())
        self.assertEqual(sets.load_sets()["sets"][0]["files"], {"vae": ["my.safetensors"]})

    def test_new_set_is_created_at_enqueue(self):
        engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "a.safetensors", "category": "loras"}], "new_set": "Fresh"})
        self.run_jobs()
        self.assertEqual([s["name"] for s in sets.load_sets()["sets"]], ["Fresh"])

    def test_folder_download_for_llama(self):
        engine.enqueue({"service": "llama", "url": self.url.replace(".safetensors", ".safetensors"), "folder": "sub",
                        "files": [{"path": "x.gguf"}]})
        self.run_jobs()
        job = next(iter(engine.DL.values()))
        self.assertEqual(job["state"], "done")
        self.assertTrue((self.env.models / "llama/sub/x.gguf").exists())
        self.assertIsNone(job["category"])

    def test_existing_file_and_empty_selection_are_rejected(self):
        self.env.touch("comfyui/vae/dup.safetensors")
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "dup.safetensors", "category": "vae"}]})
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": []})
        with self.assertRaises(HubError):
            engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "a.safetensors", "category": "../../etc"}]})

    def test_resume_from_part_file(self):
        part = self.env.models / "comfyui/vae/r.safetensors.part"
        part.parent.mkdir(parents=True)
        part.write_bytes(b"abc" * 500)                                              # 途中まで
        engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "r.safetensors", "category": "vae"}]})
        self.run_jobs()
        job = next(iter(engine.DL.values()))
        self.assertEqual(job["state"], "done", job["error"])
        self.assertEqual((self.env.models / "comfyui/vae/r.safetensors").stat().st_size, 3000)

    def test_cancel(self):
        engine.enqueue({"service": "comfy", "url": self.url, "files": [{"path": "c.safetensors", "category": "vae"}]})
        jid = next(iter(engine.DL))
        engine.cancel(jid)
        self.run_jobs()
        self.assertEqual(engine.DL[jid]["state"], "cancelled")
        engine.clear_finished()
        self.assertEqual(engine.DL, {})


if __name__ == "__main__":
    unittest.main()
