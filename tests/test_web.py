import re
import subprocess
import sys
import unittest
from pathlib import Path

from patchbay.api.static import MIME, serve

ROOT = Path(__file__).resolve().parents[1]


class WebModulesTest(unittest.TestCase):
    def test_js_modules_are_consistent(self):
        """import 漏れ・未使用の import・import の循環・構文を、検査する(tools/check_js.py)。"""
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_js.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_index_loads_a_single_module_entry(self):
        html = (ROOT / "web" / "index.html").read_text()
        self.assertEqual(re.findall(r'<script[^>]*src="([^"]+)"', html), ["/js/main.js"])
        self.assertIn('type="module"', html)
        self.assertNotRegex(html, r"\bon(click|change|input)=")        # HTML に、処理を埋め込まない

    def test_modules_are_served_as_javascript(self):
        code, ctype, body = serve("/js/state.js")
        self.assertEqual(code, 200)
        self.assertEqual(ctype, MIME[".js"])                          # モジュールは、JavaScript の種類でないと読み込まれない
        self.assertIn(b"export const state", body)

    def test_no_mutable_exports(self):
        """他のファイルから書き換えられる変数は、export しない。共有する状態は、state.js の state に置く。"""
        for p in (ROOT / "web" / "js").glob("*.js"):
            self.assertIsNone(re.search(r"(?m)^export\s+(let|var)\s", p.read_text()), p.name)


if __name__ == "__main__":
    unittest.main()
