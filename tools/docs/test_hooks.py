"""验证版本提示兼容历史标题结构，且不重复已有入口说明。"""

from types import SimpleNamespace
import unittest

from hooks import on_page_markdown


class VersionNoticeChecks(unittest.TestCase):
    def render(self, path, markdown):
        page = SimpleNamespace(file=SimpleNamespace(src_uri=path), meta={})
        config = SimpleNamespace(repo_url="https://github.com/Leroll/fast-vc-service")
        return on_page_markdown(markdown, page, config, None)

    def test_current_chinese_page(self):
        rendered = self.render("api/system.md", "# 系统接口\n\n接口正文\n")
        self.assertTrue(rendered.startswith("# 系统接口\n"))
        self.assertIn("文档版本：main", rendered)
        self.assertNotIn("本页包含历史记录", rendered)

    def test_history_without_h1_keeps_original_content(self):
        original = "## 原始笔记\n\n历史正文\n"
        rendered = self.render("design/archive/example.md", original)
        self.assertIn("本页包含历史记录", rendered)
        self.assertTrue(rendered.endswith(original))

    def test_entry_is_not_duplicated(self):
        original = "# Fast-VC\n\n**文档版本：main 开发分支。**\n"
        self.assertEqual(self.render("project.md", original), original)

    def test_english_release_history_uses_english_notice(self):
        rendered = self.render("changelog/releases_en.md", "## v0.1.0\n\nChanges\n")
        self.assertIn("Documentation version: main", rendered)
        self.assertIn("historical records", rendered)
        self.assertNotIn("文档版本", rendered)


if __name__ == "__main__":
    unittest.main()
