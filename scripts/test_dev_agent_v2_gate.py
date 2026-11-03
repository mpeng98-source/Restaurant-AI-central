#!/usr/bin/env python3
"""Regression tests for v2's post-Codex path gate."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

GATE = Path(__file__).with_name("dev_agent_v2_gate.py")
spec = importlib.util.spec_from_file_location("dev_agent_v2_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.oldcwd = os.getcwd()
        os.chdir(self.temp.name)
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "config", "user.name", "Test"], check=True)
        Path("README.md").write_text("seed")
        subprocess.run(["git", "add", "README.md"], check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], check=True)

    def tearDown(self):
        os.chdir(self.oldcwd)
        self.temp.cleanup()

    def test_allows_regular_inventory_test(self):
        path = Path("backend/tests/test_agent.py")
        path.parent.mkdir(parents=True)
        path.write_text("assert True\n")
        self.assertEqual(gate.main(), 0)
        self.assertIn("backend/tests/test_agent.py", gate.command("git", "diff", "--cached", "--name-only"))

    def test_rejects_untracked_nested_secret(self):
        root = Path("backend/tests")
        root.mkdir(parents=True)
        (root / "test_agent.py").write_text("assert True\n")
        (root / ".env").write_text("SECRET=placeholder\n")
        # Git may ignore .env; explicitly add a non-ignored restricted path.
        (root / "private.key").write_text("not-a-key\n")
        self.assertEqual(gate.main(), 2)
        self.assertEqual(gate.command("git", "diff", "--cached", "--name-only"), "")

    def test_rejects_symlink(self):
        root = Path("backend/tests")
        root.mkdir(parents=True)
        (root / "test_agent.py").symlink_to(Path(self.oldcwd) / "README.md")
        self.assertEqual(gate.main(), 2)

    def test_rejects_deletion(self):
        path = Path("backend/tests/test_old.py")
        path.parent.mkdir(parents=True)
        path.write_text("assert True\n")
        subprocess.run(["git", "add", str(path)], check=True)
        subprocess.run(["git", "commit", "-qm", "add test"], check=True)
        path.unlink()
        self.assertEqual(gate.main(), 2)


if __name__ == "__main__":
    unittest.main()
