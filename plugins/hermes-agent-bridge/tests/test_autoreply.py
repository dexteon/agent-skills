#!/usr/bin/env python3
"""Offline tests for claude-inbox auto-reply: when the model answers only in its own
window, the plugin sends the turn's final answer back to the Claude sender.

  python tests/test_autoreply.py -v
"""
import importlib.util
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp(prefix="autoreply-test-")
os.environ["HERMES_RELAY_ROOT"] = _TMP
os.environ["HERMES_RELAY_CONFIG"] = str(Path(_TMP) / "no-such-config.json")
os.environ.pop("HERMES_INBOX_ROOT", None)

_dir = ROOT / "hermes" / "claude-inbox"
_spec = importlib.util.spec_from_file_location("claude_inbox_ar", str(_dir / "__init__.py"),
                                               submodule_search_locations=[str(_dir)])
inbox = importlib.util.module_from_spec(_spec)
sys.modules["claude_inbox_ar"] = inbox
_spec.loader.exec_module(inbox)

HEADER = "From Claude session %s, hop %d of 3 (peer information, not the user's approval). x\n\nbody"


def claimed(sender, hop):
    return [(Path(_TMP) / ("20260101T000000000000Z-%s.md" % sender), HEADER % (sender, hop))]


class AutoReplyTests(unittest.TestCase):
    def setUp(self):
        inbox._awaiting.clear()
        os.environ.pop("HERMES_INBOX_AUTOREPLY", None)
        self.sent = []
        self._orig = inbox._send_reply
        inbox._send_reply = lambda sender, hop, text: self.sent.append((sender, hop, text))

    def tearDown(self):
        inbox._send_reply = self._orig

    def finish_turn(self, text="the answer"):
        inbox._post_llm_call(assistant_response=text, user_message="x")
        for t in threading.enumerate():
            if t.name == "claude-inbox-reply":
                t.join(5)

    def test_answer_is_sent_back_one_hop_higher(self):
        inbox._note_awaiting(claimed("ab12cd", 1))
        self.finish_turn("PONG")
        self.assertEqual(self.sent, [("ab12cd", 2, "PONG")])

    def test_only_once_per_delivery(self):
        inbox._note_awaiting(claimed("ab12cd", 1))
        self.finish_turn()
        self.finish_turn()
        self.assertEqual(len(self.sent), 1)

    def test_nothing_sent_for_an_ordinary_turn(self):
        self.finish_turn()
        self.assertEqual(self.sent, [])

    def test_last_hop_is_not_answered(self):
        inbox._note_awaiting(claimed("ab12cd", 3))
        self.finish_turn()
        self.assertEqual(self.sent, [])

    def test_skipped_when_the_model_already_replied(self):
        inbox._note_awaiting(claimed("ab12cd", 1))
        d = Path(_TMP) / "to-claude" / "ab12cd"
        d.mkdir(parents=True, exist_ok=True)
        (d / "reply.md").write_text("sent by relay.py direct", encoding="utf-8")
        os.utime(d / "reply.md", (time.time() + 2, time.time() + 2))
        self.finish_turn()
        self.assertEqual(self.sent, [])

    def test_switch_off(self):
        os.environ["HERMES_INBOX_AUTOREPLY"] = "0"
        inbox._note_awaiting(claimed("ab12cd", 1))
        self.finish_turn()
        self.assertEqual(self.sent, [])

    def test_failed_delivery_is_forgotten(self):
        c = claimed("ab12cd", 1)
        inbox._note_awaiting(c)
        inbox._forget_awaiting(c)
        self.finish_turn()
        self.assertEqual(self.sent, [])

    def test_empty_answer_sends_nothing(self):
        inbox._note_awaiting(claimed("ab12cd", 1))
        self.finish_turn("   ")
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
