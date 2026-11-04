"""用临时副本中的文档错误验证检查器，不启动服务或修改实际文档。"""

from pathlib import Path
import shutil
import tempfile
import unittest

from check_content import ROOT, check_content, normalized_example, read_policy, review_warnings


class ContentChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = {"README.md", "tools/docs/content.toml", "configs/prod.yaml",
                 "src/fast_vc_service/config.py", "examples/websocket/simple_protocol_ws_client.py"}
        policy = read_policy(ROOT)
        paths.update(policy["translations"])
        paths.update(policy["translations"].values())
        paths.update(path for targets in policy["review"].values() for path in targets)
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)

    def replace(self, path, old, new):
        target = self.root / path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text)
        target.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assert_error(self, fragment):
        self.assertTrue(any(fragment in error for error in check_content(self.root)[0]))

    def test_current_documents(self):
        self.assertEqual(check_content(self.root)[0], [])

    def test_changed_production_value_requires_docs_update(self):
        self.replace("configs/prod.yaml", "receive_timeout: 120", "receive_timeout: 121")
        self.assert_error("与 prod.yaml")

    def test_removed_config_field_is_detected_without_importing_service(self):
        self.replace("src/fast_vc_service/config.py", "prefill_time: int", "prefill_ms: int")
        self.assert_error("配置类不存在字段 buffer.prefill_time")

    def test_invalid_json(self):
        self.replace("docs/zh/api/voice-conversion.md", '"type": "config",', '"type": "config"')
        self.assert_error("json 示例语法错误")

    def test_bilingual_example_drift(self):
        self.replace("docs/en/api/voice-conversion.md", '"session_id": "example-001"', '"session_id": "different-example"')
        self.assert_error("双语机器示例不一致")

    def test_removed_client_option_is_detected(self):
        self.replace("examples/websocket/simple_protocol_ws_client.py", '"--source-wav-path"', '"--input-wav"')
        self.assert_error("unrecognized arguments: --source-wav-path")

    def test_python_heredoc_syntax(self):
        with self.assertRaises(SyntaxError):
            normalized_example("bash", "uv run python - <<'PY'\nif True\n    pass\nPY\n")

    def test_shell_syntax(self):
        with self.assertRaises(ValueError):
            normalized_example("bash", "if true; then\n")

    def test_examples_are_never_executed(self):
        marker = self.root / "should-not-exist"
        normalized_example("bash", f"touch '{marker}'\n")
        normalized_example("python", f"open({str(marker)!r}, 'w').close()\n")
        self.assertFalse(marker.exists())

    def test_maintainer_comments_do_not_require_matching_translation(self):
        self.assertEqual(normalized_example("bash", "# 中文\necho hello"),
                         normalized_example("bash", "# English\necho hello"))
        self.assertEqual(normalized_example("python", "# 中文\nx=1"),
                         normalized_example("python", "# English\nx = 1"))

    def test_one_sided_translation_is_warning(self):
        warnings = review_warnings({"docs/zh/api/system.md"}, read_policy(self.root))
        self.assertTrue(any("docs/en/api/system.md" in warning for warning in warnings))
        self.assertEqual(check_content(self.root)[0], [])

    def test_code_change_reminds_even_when_document_also_changes(self):
        warnings = review_warnings({"src/fast_vc_service/routers/ws.py", "docs/zh/api/voice-conversion.md"}, read_policy(self.root))
        self.assertTrue(any("源码/配置变更" in warning and "docs/en/api/voice-conversion.md" in warning for warning in warnings))

    def test_history_does_not_trigger_translation_warning(self):
        self.assertEqual(review_warnings({"docs/zh/changelog/2026-11-02.md"}, read_policy(self.root)), [])


if __name__ == "__main__":
    unittest.main()
