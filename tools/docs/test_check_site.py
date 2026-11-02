"""通过故意损坏的最小构建产物验证网页检查器的失败边界。"""

import json
from pathlib import Path
import tempfile
import unittest

from check_site import check_site


class SiteChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.write("index.html", '<h1>首页</h1><a href="guide/#中文锚点">指南</a>')
        self.write("guide/index.html", '<h1>指南</h1><h2 id="中文锚点">章节</h2>')
        self.write("search-records.json", json.dumps(["/fast-vc-service/guide/#中文锚点"]))
        self.write("docs-manifest.json", json.dumps({"pages": {"docs/guide.md": "guide/index.md"}}))

    def write(self, name, text):
        target = self.site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def check(self):
        return check_site(self.site, "https://example.com/fast-vc-service/")

    def test_directory_urls_and_unicode_anchors(self):
        self.assertEqual(self.check(), (2, 3, 1))

    def test_missing_asset_and_anchor_are_reported(self):
        self.write("index.html", '<h1>首页</h1><img src="missing.svg"><a href="guide/#不存在">指南</a>')
        with self.assertRaisesRegex(ValueError, "目标不存在: missing.svg[\\s\\S]*锚点不存在"):
            self.check()

    def test_search_record_must_resolve(self):
        self.write("search-records.json", '["/fast-vc-service/guide/#deleted"]')
        with self.assertRaisesRegex(ValueError, "锚点不存在"):
            self.check()

    def test_manifest_detects_unlinked_missing_page(self):
        self.write("docs-manifest.json", '{"pages":{"docs/extra.md":"extra/index.md"}}')
        with self.assertRaisesRegex(ValueError, "目标不存在"):
            self.check()

    def test_site_base_and_encoded_path_escape_are_rejected(self):
        for value in ("/guide/", "/fast-vc-service/%2e%2e/private.html"):
            with self.subTest(value=value):
                self.write("index.html", f'<h1>首页</h1><a href="{value}">错误路径</a>')
                with self.assertRaisesRegex(ValueError, "链接越出"):
                    self.check()


if __name__ == "__main__":
    unittest.main()
