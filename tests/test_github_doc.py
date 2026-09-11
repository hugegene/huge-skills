import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/github-doc/scripts"))
import api
import push_doc


def file_state(content=None, sha=None):
    return {"exists": sha is not None, "content": content, "sha": sha}


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.note = Path(self.tmp.name) / "note.md"
        self.note.write_text("# My note\n\nHello.\n")
        self.repo_mock = patch.object(api, "get_repo", return_value={"default_branch": "trunk"}).start()
        self.get_mock = patch.object(api, "get_file", side_effect=[file_state(), file_state("# Index\n", "r1")]).start()
        self.put_mock = patch.object(api, "put_file", return_value={"commit": {"html_url": "https://example.com/commit"}}).start()
        self.addCleanup(patch.stopall)

    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            push_doc.main([str(self.note), "--repo", "owner/repo", *args])
        return output.getvalue()

    def test_preview_makes_no_writes_and_resolves_default_branch(self):
        output = self.run_cli()
        self.put_mock.assert_not_called()
        self.assertIn("2 commit(s) planned", output)
        self.assertIn("+Hello.", output)
        self.get_mock.assert_any_call("owner", "repo", "note.md", "trunk")

    def test_push_writes_doc_then_readme_with_original_sha(self):
        self.run_cli("--push", "--branch", "docs")
        calls = self.put_mock.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[2], "note.md")
        self.assertEqual(calls[1].args[2], "README.md")
        self.assertEqual(calls[1].args[-2:], ("docs", "r1"))

    def test_nested_readme_uses_encoded_relative_link(self):
        self.run_cli("--push", "--path", "notes/my note(1).md", "--readme-path", "docs/README.md")
        self.assertIn("(../notes/my%20note%281%29.md)", self.put_mock.call_args_list[1].args[3])

    def test_rerun_skips_unchanged_doc_and_existing_link(self):
        self.get_mock.side_effect = [file_state(self.note.read_text(), "d1"), file_state("- [My note](note.md)\n", "r1")]
        self.assertIn("No changes", self.run_cli("--push"))
        self.put_mock.assert_not_called()

    def test_partial_success_and_recovery(self):
        self.put_mock.side_effect = [{"commit": {}}, ValueError("conflict")]
        with self.assertRaisesRegex(ValueError, "Partial success: committed note.md; failed at README.md"):
            self.run_cli("--push")
        self.get_mock.side_effect = [file_state(self.note.read_text(), "d1"), file_state("# Index\n", "r1")]
        self.put_mock.reset_mock(side_effect=True)
        self.run_cli("--push")
        self.put_mock.assert_called_once()
        self.assertEqual(self.put_mock.call_args.args[2], "README.md")

    def test_no_readme_and_invalid_same_target(self):
        self.run_cli("--push", "--no-readme")
        self.get_mock.assert_called_once()
        self.put_mock.assert_called_once()
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.run_cli("--path", "README.md")

    def test_script_runs_through_symlink_from_another_directory(self):
        skill_link = Path(self.tmp.name) / "linked skill"
        skill_link.symlink_to(ROOT / "skills/github-doc")
        result = subprocess.run([sys.executable, str(skill_link / "scripts/push_doc.py"), "--help"],
                                cwd=self.tmp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--repo", result.stdout)


class MarkdownTests(unittest.TestCase):
    def test_existing_link_is_unchanged(self):
        text = "- [Original label](notes/a.md)\n"
        self.assertEqual(push_doc.insert_readme_link(text, "notes/a.md", "Other", None), (text, False))

    def test_section_preserves_prose_and_next_heading(self):
        text = "# Index\n\n## Notes\n\nContext.\n\n- [Old](old.md)\n\n## Other\n\nKeep.\n"
        new, changed = push_doc.insert_readme_link(text, "new.md", "New", "## Notes")
        self.assertTrue(changed)
        self.assertIn("Context.\n\n- [Old](old.md)\n- [New](new.md)\n\n## Other", new)
        self.assertTrue(new.endswith("Keep.\n"))

    def test_missing_section_and_label_escaping(self):
        new, _ = push_doc.insert_readme_link("# Index\n", "note.md", "[Title]", "## Notes")
        self.assertIn("## Notes\n\n- [\\[Title\\]](note.md)", new)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MCP_GIT_PAT": "test-token"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    @patch.object(requests, "request")
    def test_create_and_update_send_correct_sha_and_encoded_path(self, request):
        request.return_value = Mock(status_code=201)
        api.put_file("owner", "repo", "notes/a #?.md", "hello", "docs: add", "main", None)
        self.assertNotIn("sha", request.call_args.kwargs["json"])
        self.assertIn("a%20%23%3F.md", request.call_args.args[1])
        api.put_file("owner", "repo", "a.md", "hello", "docs: update", "main", "old-sha")
        self.assertEqual(request.call_args.kwargs["json"]["sha"], "old-sha")
        self.assertEqual(base64.b64decode(request.call_args.kwargs["json"]["content"]), b"hello")

    @patch.object(requests, "request")
    def test_read_missing_file_and_reject_non_text(self, request):
        request.return_value = Mock(status_code=404)
        self.assertFalse(api.get_file("o", "r", "a.md", "main")["exists"])
        for payload in ([], {"type": "file", "encoding": "none"},
                        {"type": "file", "encoding": "base64", "content": "/w=="}):
            request.return_value = Mock(status_code=200, json=Mock(return_value=payload))
            with self.assertRaises(ValueError):
                api.get_file("o", "r", "a.md", "main")

    @patch.object(requests, "request")
    def test_conflict_and_timeout_are_not_retried(self, request):
        request.return_value = Mock(status_code=409)
        with self.assertRaisesRegex(ValueError, "HTTP 409"):
            api.put_file("o", "r", "a.md", "hi", "msg", "main", "old")
        request.assert_called_once()
        request.reset_mock()
        request.side_effect = requests.Timeout("sensitive request data")
        with self.assertRaisesRegex(ValueError, "inspect the branch") as caught:
            api.put_file("o", "r", "a.md", "hi", "msg", "main", "old")
        self.assertNotIn("sensitive", str(caught.exception))
        request.assert_called_once()

    def test_path_validation_and_missing_token(self):
        for path in ("../x", "/absolute", "a//b", "a/./b", "a\\b", "", None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                api.validate_path(path)
        del os.environ["MCP_GIT_PAT"]
        with self.assertRaisesRegex(ValueError, "Set MCP_GIT_PAT"):
            api._headers()


if __name__ == "__main__":
    unittest.main()
