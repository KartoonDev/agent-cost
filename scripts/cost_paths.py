#!/usr/bin/env python3
"""Where the ledger lives — one resolver shared by capture.py and report.py.

Order:  $AGENT_COST_DIR  →  ~/.config/agent-cost/config.json ("dir")  →  ~/.agent-cost

Keeping the answer in one place means the hook that writes and the report that
reads can never disagree about which file is the source of truth. The default is
deliberately machine-neutral so a teammate who just unzips the skill gets a
working ledger without editing anything.
"""
import json, os

CONFIG = os.path.expanduser("~/.config/agent-cost/config.json")
DEFAULT_DIR = "~/.agent-cost"


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ledger_dir(cfg=None):
    env = os.environ.get("AGENT_COST_DIR")
    if env:
        return os.path.expanduser(env)
    if cfg is None:
        cfg = load_config()
    return os.path.expanduser(cfg.get("dir") or DEFAULT_DIR)


def record_prompts(cfg=None):
    """False → the ledger keeps the numbers but not what was asked."""
    if os.environ.get("AGENT_COST_NO_PROMPT") == "1":
        return False
    if cfg is None:
        cfg = load_config()
    return bool(cfg.get("record_prompts", True))


class ledger_lock:
    """Short exclusive lock around every write to ledger.jsonl.

    Writers: the Stop hook (capture.py), ide_sync.py (also run by dashboard.py every
    few seconds), backfill.py, and capture.py --rebuild, which swaps the whole file.
    Without it, a row appended while rebuild is replacing the file is silently lost.

    Never blocks forever: after `timeout` seconds the caller proceeds unlocked,
    because a hook that hangs would stall the agent. No-op where fcntl is missing.
    """

    def __init__(self, ledger_dir_path, timeout=20.0, name=".ledger.lock"):
        # A writer of a different file (e.g. codex-ledger.jsonl) passes its own name so it
        # never makes the Stop hook wait.
        self.path = os.path.join(ledger_dir_path, name)
        self.timeout = timeout
        self.fh = None

    def __enter__(self):
        try:
            import fcntl, time
        except ImportError:
            return self
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.fh = open(self.path, "a")
            end = time.time() + self.timeout
            while True:
                try:
                    fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except BlockingIOError:
                    if time.time() >= end:
                        return self
                    time.sleep(0.1)
        except OSError:
            return self

    def __exit__(self, *exc):
        if self.fh:
            try:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_UN)
            except Exception:
                pass
            self.fh.close()
        return False
