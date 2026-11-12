#!/usr/bin/env python3
"""Offline tests for the claude-link-gate Hermes plugin and hermes_ask.py argument handling.

  python tests/test_link_gate.py -v
"""
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASK = ROOT / "skills" / "hermes-relay-volunteer" / "scripts" / "hermes_ask.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = load("claude_link_gate", ROOT / "hermes" / "claude-link-gate" / "__init__.py")

BLOCK = [
    "rm -rf /data/x", "rm file.txt", "cd x && rm -f a", "rmdir /s /q C:/x", "del /q a.txt",
    "Remove-Item -Recurse -Force D:/x", "powershell -c \"Remove-Item x\"",
    "find . -name '*.log' -delete", "git clean -fdx", "git reset --hard HEAD~1",
    "git push --force origin main", "git push -f", "git -C /repo push origin +main:main",
    "git branch -D feature", "docker rm -f c1", "docker system prune -af",
    "robocopy a b /MIR", "rsync -a --delete a/ b/", "sqlite3 db 'DROP TABLE users'",
    "psql -c 'DELETE FROM t'", "python -c \"import shutil; shutil.rmtree('x')\"",
    "python -c \"import os; os.remove('a')\"", "node -e \"fs.rmSync('x')\"", "unlink a",
    "truncate -s 0 a.log",
]
ALLOW = [
    "ls -la", "git status", "git push origin main", "git commit -m 'remove dead code'",
    "python build.py", "cat firmware.txt", "docker ps", "pytest -q", "echo performance",
    "npm run format:check", "git diff --stat", "curl http://127.0.0.1:8642/health",
    "python -m pip list", "Get-ChildItem D:/work",
]


class GateTests(unittest.TestCase):
    def setUp(self):
        os.environ["HERMES_CLAUDE_LINK"] = "1"
        os.environ.pop("HERMES_CLAUDE_LINK_DELETE_OK", None)

    def tearDown(self):
        os.environ.pop("HERMES_CLAUDE_LINK", None)
        os.environ.pop("HERMES_CLAUDE_LINK_DELETE_OK", None)

    def test_destructive_commands_are_blocked(self):
        for cmd in BLOCK:
            with self.subTest(cmd=cmd):
                d = gate.check("terminal", {"command": cmd})
                self.assertIsNotNone(d)
                self.assertEqual(d["action"], "block")

    def test_ordinary_commands_pass(self):
        for cmd in ALLOW:
            with self.subTest(cmd=cmd):
                self.assertIsNone(gate.check("terminal", {"command": cmd}))

    def test_off_without_the_marker(self):
        os.environ.pop("HERMES_CLAUDE_LINK")
        self.assertIsNone(gate.check("terminal", {"command": "rm -rf x"}))

    def test_off_after_approval(self):
        os.environ["HERMES_CLAUDE_LINK_DELETE_OK"] = "1"
        self.assertIsNone(gate.check("terminal", {"command": "rm -rf x"}))

    def test_only_acting_tools_are_checked(self):
        self.assertIsNone(gate.check("read_file", {"path": "rm -rf"}))
        self.assertIsNotNone(gate.check("execute_code", {"code": "import shutil\nshutil.rmtree('x')"}))

    def test_hook_signature_and_registration(self):
        seen = {}

        class Ctx:
            def register_hook(self, name, fn):
                seen[name] = fn

        gate.register(Ctx())
        d = seen["pre_tool_call"]("terminal", {"command": "rm -rf x"}, "task", "sess", tool_call_id="c1")
        self.assertEqual(d["rule"], "claude-link-delete")


class AskCliTests(unittest.TestCase):
    def run_ask(self, *argv):
        env = dict(os.environ, HERMES_HOME=str(ROOT / "no-such-hermes-home"))
        return subprocess.run([sys.executable, str(ASK), *argv], capture_output=True,
                              text=True, env=env, timeout=60)

    def test_needs_exactly_one_body(self):
        r = self.run_ask()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("exactly one of --text or --file", r.stderr)

    def test_unknown_profile_is_refused_before_anything_runs(self):
        r = self.run_ask("--profile", "../evil", "--text", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown profile", r.stderr)

    def test_oversize_message_is_refused(self):
        r = self.run_ask("--text", "x" * 9000)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("8 KB", r.stderr)

    def test_open_chat_route_needs_a_sender(self):
        r = self.run_ask("--to", "ab12cd", "--text", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--from", r.stderr)


if __name__ == "__main__":
    unittest.main()
