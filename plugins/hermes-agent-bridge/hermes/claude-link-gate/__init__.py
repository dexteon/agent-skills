"""claude-link-gate: a delete gate for work that arrives over the Claude link.

A Claude Code session may give Hermes work orders through hermes_ask.py, but it
should not be able to make Hermes delete or destroy data without the user being
asked first. On a headless run nobody is present to answer an approval prompt,
and a permanent command allowlist can pre-approve destructive commands before
any "nobody present, deny" rule is consulted. This plugin closes that gap.

hermes_ask.py sets HERMES_CLAUDE_LINK=1 on the Hermes process it starts. While
that is set, terminal commands and executed code that delete or destroy data are
blocked, and the agent is told to report what it wanted to delete. After the
user approves a specific deletion, the sender re-runs with --allow-delete, which
sets HERMES_CLAUDE_LINK_DELETE_OK=1 for that one run.

Normal Hermes chats, cron jobs and the gateway never set the variable, so they
behave exactly as before. Enable the plugin in every profile hermes_ask.py may
address: an unmarked profile is an ungated profile.

The pattern list is a guard against accidents and casual requests, not a
sandbox. A determined agent can delete data in ways no regex sees.
"""
import os
import re

_TOOLS = {"terminal", "execute_code", "process"}

_DESTRUCTIVE = re.compile(
    r"""
    (?<![\w-])rm(?:dir)?\s
  | (?<![\w-])(?:del|erase|rd|unlink|shred|truncate|mkfs|format)\s
  | \bRemove-Item\b | \bClear-Content\b | \bClear-RecycleBin\b | \bRemove-ItemProperty\b
  | \bri\s+-(?:r|fo|rec)
  | \bfind\b[^\n|;&]*\s-delete\b
  | \bgit\b[^\n|;&]*?\s(?:clean\b|reset\s+--hard|push\b[^\n|;&]*?(?:--force|\s-f\b|\s\+\S)|branch\b[^\n|;&]*?\s-D\b|stash\s+(?:drop|clear))
  | \bdocker\s+(?:\w+\s+)?(?:rm|rmi|prune)\b | \bdocker\s+compose\s+down\b[^\n]*(?:-v|--volumes)
  | \brobocopy\b[^\n]*/(?:MIR|PURGE) | \brsync\b[^\n]*--delete
  | \b(?:DROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)|TRUNCATE\s+TABLE|DELETE\s+FROM)\b
  | \brmtree\b | \bos\.(?:remove|unlink|rmdir|removedirs)\b | \.unlink\s*\( | \.rmdir\s*\(
  | \bfs\.(?:rm|unlink|rmdir)\w*\b | \bFile\.Delete\b | \bDirectory\.Delete\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MESSAGE = (
    "CLAUDE LINK GATE: this work came from a Claude Code session over the link, and "
    "the command would delete or destroy data ({what}). Deleting over the link needs "
    "the user's approval first. Do NOT retry it and do NOT delete the data another way. "
    "Carry on with the rest of the work, and in your reply list exactly what you "
    "wanted to delete and why, so the sender can ask the user."
)


def active():
    return (os.environ.get("HERMES_CLAUDE_LINK") == "1"
            and os.environ.get("HERMES_CLAUDE_LINK_DELETE_OK") != "1")


def check(tool_name, args):
    """Return a block directive for a destructive call on a Claude-link run, else None."""
    if not active() or tool_name not in _TOOLS or not isinstance(args, dict):
        return None
    text = "\n".join(str(args.get(k) or "") for k in ("command", "code", "script", "input"))
    hit = _DESTRUCTIVE.search(text)
    if not hit:
        return None
    return {"action": "block", "rule": "claude-link-delete",
            "message": _MESSAGE.format(what=hit.group(0).strip()[:60])}


def _pre_tool_call(tool_name, args, task_id=None, session_id=None, **kwargs):
    return check(tool_name, args)


def register(ctx):
    ctx.register_hook("pre_tool_call", _pre_tool_call)
