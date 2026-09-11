import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="skills test ")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "checkout with spaces"
        shutil.copytree(ROOT / "skills", self.repo / "skills", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "install.sh", self.repo / "install.sh")
        self.home = self.base / "home"
        self.home.mkdir()
        self.target = self.home / ".agents/skills"
        self.claude_target = self.home / ".claude/skills"
        self.env = {**os.environ, "HOME": str(self.home)}

    def run_installer(self, *args, code=0):
        result = subprocess.run(["/bin/bash", str(self.repo / "install.sh"), *args],
                                cwd=self.base, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_install_rerun_and_owned_uninstall(self):
        self.run_installer()
        link = self.target / "github-doc"
        self.assertTrue((link / "SKILL.md").is_file())
        self.assertEqual(link.resolve(), (self.repo / "skills/github-doc").resolve())
        self.assertIn("Already linked", self.run_installer().stdout)
        unrelated = self.target / "unrelated"
        unrelated.write_text("keep")
        self.run_installer("--uninstall", "--dry-run")
        self.assertTrue(link.is_symlink())
        self.run_installer("--uninstall")
        self.assertFalse(link.is_symlink())
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertTrue((self.repo / "skills/github-doc/SKILL.md").exists())

    def test_dry_run_and_empty_uninstall_create_nothing(self):
        self.run_installer("--dry-run")
        self.assertFalse(self.target.exists())
        self.run_installer("--uninstall")
        self.assertFalse(self.target.exists())

    def test_custom_relative_target_and_selection(self):
        self.run_installer("--target", "project skills", "--skill", "github-doc")
        self.assertTrue((self.base / "project skills/github-doc/SKILL.md").is_file())
        self.assertFalse(self.target.exists())

    def test_each_agent_installs_only_its_destination(self):
        for agent, target, other in [("codex", self.target, self.claude_target),
                                      ("claude", self.claude_target, self.target)]:
            with self.subTest(agent=agent):
                self.run_installer("--agent", agent)
                self.assertTrue((target / "github-doc/SKILL.md").is_file())
                self.assertFalse((other / "github-doc").is_symlink())
                self.run_installer("--agent", agent, "--uninstall")

    def test_both_rerun_and_selective_uninstall(self):
        self.run_installer("--agent", "both", "--skill", "github-doc")
        links = [target / "github-doc" for target in (self.target, self.claude_target)]
        self.assertEqual(links[0].resolve(), links[1].resolve())
        self.assertEqual(self.run_installer("--agent", "both").stdout.count("Already linked:"), 2)
        self.run_installer("--agent", "claude", "--uninstall", "--skill", "github-doc")
        self.assertTrue(links[0].is_symlink())
        self.assertFalse(links[1].is_symlink())
        self.run_installer("--agent", "both", "--uninstall")
        self.assertFalse(links[0].is_symlink())

    def test_both_dry_run_and_stale_uninstall(self):
        self.run_installer("--agent", "both", "--dry-run")
        self.assertFalse(self.target.exists())
        self.assertFalse(self.claude_target.exists())
        self.run_installer("--agent", "both")
        shutil.rmtree(self.repo / "skills/github-doc")
        self.run_installer("--agent", "both", "--uninstall", "--dry-run")
        for target in (self.target, self.claude_target):
            self.assertTrue((target / "github-doc").is_symlink())
        output = self.run_installer("--agent", "both", "--uninstall").stdout
        self.assertEqual(output.count("Unlink:"), 2)
        self.assertNotIn("Keep:", output)
        for target in (self.target, self.claude_target):
            self.assertFalse((target / "github-doc").is_symlink())

    def test_skill_selection_preserves_other_skills_for_both_agents(self):
        extra = self.repo / "skills/extra"
        extra.mkdir()
        (extra / "SKILL.md").write_text("---\nname: extra\ndescription: example\n---\n")
        self.run_installer("--agent", "both", "--skill", "github-doc")
        for target in (self.target, self.claude_target):
            self.assertFalse((target / "extra").exists())
        self.run_installer("--agent", "both", "--skill", "extra", "--skill", "github-doc")
        self.run_installer("--agent", "both", "--skill", "github-doc", "--uninstall")
        for target in (self.target, self.claude_target):
            self.assertFalse((target / "github-doc").is_symlink())
            self.assertTrue((target / "extra/SKILL.md").is_file())

    def test_project_install_for_both_and_default_codex(self):
        project = self.base / "my project"
        project.mkdir()
        self.run_installer("--project", "my project")
        self.assertTrue((project / ".agents/skills/github-doc/SKILL.md").is_file())
        self.assertFalse((project / ".claude").exists())
        self.run_installer("--agent", "both", "--project", str(project))
        self.assertTrue((project / ".claude/skills/github-doc/SKILL.md").is_file())
        self.assertFalse(self.target.exists())
        self.assertFalse(self.claude_target.exists())
        self.run_installer("--agent", "both", "--project", str(project), "--uninstall")
        for directory in (".agents", ".claude"):
            self.assertFalse((project / directory / "skills/github-doc").is_symlink())

    def test_conflict_in_second_agent_prevents_first_install(self):
        self.claude_target.mkdir(parents=True)
        conflict = self.claude_target / "github-doc"
        conflict.write_text("keep")
        self.run_installer("--agent", "both", code=1)
        self.assertFalse(self.target.exists())
        self.assertEqual(conflict.read_text(), "keep")

    def test_obstructed_second_agent_parent_prevents_first_install(self):
        (self.home / ".claude").write_text("keep")
        self.run_installer("--agent", "both", code=1)
        self.assertFalse(self.target.exists())
        self.assertEqual((self.home / ".claude").read_text(), "keep")

    def test_agent_argument_errors_create_nothing(self):
        for args in [("--agent", "unknown"), ("--agent",), ("--project",),
                     ("--project", "missing"), ("--agent", "codex", "--target", "custom"),
                     ("--target", "custom", "--agent", "both"),
                     ("--project", str(self.base), "--target", "custom")]:
            with self.subTest(args=args):
                self.run_installer(*args, code=1)
                self.assertFalse(self.target.exists())
                self.assertFalse(self.claude_target.exists())
                self.assertFalse((self.base / "custom").exists())

    def test_conflicts_are_preserved_and_preflight_is_atomic(self):
        extra = self.repo / "skills/aaa"
        extra.mkdir()
        (extra / "SKILL.md").write_text("---\nname: aaa\ndescription: example\n---\n")
        self.target.mkdir(parents=True)
        conflict = self.target / "github-doc"
        for kind in ("file", "directory", "dangling-link"):
            with self.subTest(kind=kind):
                if kind == "file":
                    conflict.write_text("keep")
                elif kind == "directory":
                    conflict.mkdir()
                else:
                    conflict.symlink_to(self.base / "missing")
                self.run_installer(code=1)
                self.assertFalse((self.target / "aaa").exists())
                self.run_installer("--uninstall", "--skill", "github-doc")
                self.assertTrue(conflict.exists() or conflict.is_symlink())
                if kind == "directory":
                    conflict.rmdir()
                else:
                    conflict.unlink()

    def test_uninstall_stale_owned_link(self):
        self.run_installer()
        shutil.rmtree(self.repo / "skills/github-doc")
        self.run_installer("--uninstall")
        self.assertFalse((self.target / "github-doc").is_symlink())

    def test_unknown_skill_and_invalid_arguments(self):
        for args in [("--skill", "missing"), ("--skill", "../escape"), ("--target",), ("--wat",)]:
            with self.subTest(args=args):
                self.run_installer(*args, code=1)
                self.assertFalse(self.target.exists())

    def test_skill_discovery_metadata(self):
        for folder in (self.repo / "skills").iterdir():
            content = (folder / "SKILL.md").read_text()
            self.assertTrue(content.startswith("---\n"))
            frontmatter = content.split("---", 2)[1]
            self.assertIn(f"\nname: {folder.name}\n", frontmatter)
            self.assertRegex(frontmatter, r"\ndescription: \S")


if __name__ == "__main__":
    unittest.main()
