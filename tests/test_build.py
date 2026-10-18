import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_standalone import build


class BuildTests(unittest.TestCase):
    def test_public_build_never_reads_personal_database(self):
        with tempfile.TemporaryDirectory() as folder, patch("build_standalone.Store", side_effect=AssertionError("must not read personal data")):
            target = build(Path(folder) / "site" / "index.html", include_data=False)
            html = target.read_text(encoding="utf-8")
        seed = json.loads(re.search(r"window.LOCAL_SEED=(.*?);</script>", html).group(1))
        self.assertEqual(seed["projects"], [])
        self.assertIn({"name":"网站作品","color":"blue"}, seed["categories"])
        self.assertIn("window.FORCE_LOCAL_MODE=true", html)
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn('href="/style.css"', html)

    def test_personal_build_escapes_records_in_scripts(self):
        with tempfile.TemporaryDirectory() as folder, patch("build_standalone.Store") as store:
            store.return_value.list.return_value = [{"name":"</script><script>alert(1)</script>"}]
            store.return_value.categories.return_value = []
            html = build(Path(folder) / "local.html").read_text(encoding="utf-8")
        seed = json.loads(re.search(r"window.LOCAL_SEED=(.*?);</script>", html).group(1))
        self.assertEqual(seed["projects"][0]["name"], "</script><script>alert(1)</script>")
        self.assertNotIn('"name": "</script>', html)
