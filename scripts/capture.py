#!/usr/bin/env python3
"""Append one turn's cost record to the agent-cost ledger.

Runs as a `Stop` hook in BOTH CodeBuddy CLI and Claude Code — the two share a
hook schema, so one script covers both and the numbers stay comparable.

Reads the hook payload on stdin: {session_id, transcript_path, cwd, ...}
Writes one JSON object per turn to  <LEDGER_DIR>/ledger.jsonl

A "turn" = everything from the last human prompt to the end of the transcript.
Tool results, local-command echoes (/model, /clear, /usage) and injected skill
bodies are NOT human prompts, so a 40-tool-call turn stays one record.

Token fields use ONE definition for both agents (usage_v 2):
  input_tokens       uncached input only
  cache_read_tokens  input served from cache
  cache_write_tokens input written to cache
  total_tokens       input + cache_read + cache_write + output  (everything processed)
CodeBuddy's raw prompt_tokens already include the cache hits; Claude's don't —
we subtract on the CodeBuddy side so the two columns mean the same thing.

    capture.py              hook mode (stdin payload)
    capture.py --rebuild    re-derive every ledger row from its transcript (backs up first)

Never fails loudly in hook mode: a hook that errors would interrupt the agent,
so every failure path exits 0. Set AGENT_COST_DEBUG=1 to see why nothing was written.
"""
import json, os, re, sys, time, datetime, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cost_paths import load_config, ledger_dir, record_prompts

CFG = load_config()
LEDGER_DIR = ledger_dir(CFG)
LEDGER = os.path.join(LEDGER_DIR, "ledger.jsonl")
RECORD_PROMPTS = record_prompts(CFG)
DEBUG = os.environ.get("AGENT_COST_DEBUG") == "1"
USAGE_V = 2
WORK_EVENTS = {"user", "assistant", "message", "reasoning", "function_call", "function_call_result"}


def log(*a):
    if DEBUG:
        print("[agent-cost]", *a, file=sys.stderr)


def ts_to_epoch(v):
    """Accept ISO-8601 strings or epoch millis; return float seconds or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0 if v > 1e11 else float(v)
    try:
        s = str(v).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def wait_for_settle(path, quiet=0.5, limit=3.0):
    """CodeBuddy fires Stop before it writes the turn's final assistant message
    (and that message carries its own credit). Wait until the file stops growing."""
    end = time.time() + limit
    last = -1
    while time.time() < end:
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size == last:
            return
        last = size
        time.sleep(quiet)


def load_events(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        log("cannot read transcript:", e)
    return out


def user_content(ev):
    """Content of a user-role message, or None if the event isn't one."""
    t = ev.get("type")
    # CodeBuddy: {"type":"message","role":"user"}   Claude: {"type":"user","message":{"role":"user"}}
    if t == "message" and ev.get("role") == "user":
        return ev.get("content")
    if t == "user":
        msg = ev.get("message") or {}
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def prompt_text(ev):
    content = user_content(ev)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for blk in content:
            # CodeBuddy emits "input_text"; Claude emits "text".
            if isinstance(blk, dict) and blk.get("type") in ("text", "input_text"):
                parts.append(blk.get("text", ""))
            elif isinstance(blk, str):
                parts.append(blk)
        return " ".join(parts).strip()
    return ""


def is_user_message(ev):
    """A user-role message that isn't a tool result."""
    content = user_content(ev)
    if content is None:
        return False
    if isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") in ("tool_result", "function_call_result"):
                return False
    return True


# Messages the harness writes in the user's name that don't start a turn.
_ECHO = re.compile(
    r"^\s*(<local-command-(stdout|stderr|caveat)>|<bash-(input|stdout|stderr)>"
    r"|<system-reminder[^>]*command-caveat"
    r"|\[Request interrupted by user)"
)
_TAG_ONLY_COMMAND = re.compile(
    r"^\s*(<(command-name|command-message|command-args)>[^<]*</\2>\s*)+$"
)


def human_prompt_indices(events):
    """Indices of events that really start a turn.

    Skipped: tool results; Claude `isMeta` injections (skill bodies, caveats,
    "Continue from where you left off"); local-command echoes; and a bare
    `<command-name>/model</command-name>` whose output is a local-command echo —
    that's a built-in like /model or /clear, not work. A slash command that runs
    a skill (/pr-review) has no such echo, so it still counts.
    Typing /model mid-turn used to end the turn early and drop its credits.
    """
    users = [i for i, ev in enumerate(events) if is_user_message(ev)]
    out = []
    for n, i in enumerate(users):
        ev = events[i]
        if ev.get("isMeta"):
            continue
        text = prompt_text(ev)
        if not text or _ECHO.match(text):
            continue
        if _TAG_ONLY_COMMAND.match(text):
            following = [prompt_text(events[j]) for j in users[n + 1:n + 3]]
            if any(t.lstrip().startswith("<local-command-std") for t in following):
                continue
        out.append(i)
    return out


def label_of(raw):
    """Turn a raw prompt into something readable in a report.

    A slash command reaches the transcript as the skill's whole SKILL.md body,
    which is useless as a label — collapse those back to the command name.
    """
    if not raw:
        return ""
    m = re.search(r"<command-name>\s*(/?[\w:-]+)\s*</command-name>", raw)
    if m:
        cmd = m.group(1)
        a = re.search(r"<command-args>([^<]*)</command-args>", raw) or re.search(r"ARGUMENTS:\s*(.+)", raw)
        return f"{cmd} {a.group(1).strip()}".strip()[:400] if a else cmd
    m = re.search(r"^Base directory for this skill:\s*(\S+)", raw)
    if m:
        name = os.path.basename(m.group(1).rstrip("/"))
        a = re.search(r"ARGUMENTS:\s*(.+)", raw)
        return f"skill:{name} {a.group(1).strip()}".strip()[:400] if a else f"skill:{name}"
    return " ".join(raw.split())[:400]


def turn_bounds(events, prompts, start):
    """(start, end) of the turn that begins at `start`: up to the next real prompt."""
    nxt = next((i for i in prompts if i > start), len(events))
    return start, nxt


def collect(turn):
    """Pull cost/usage/tool facts out of one turn, handling both transcript dialects."""
    credit = 0.0
    have_credit = False
    tok = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    model = None
    tools, files = [], []
    stamps = []
    # Claude Code writes ONE event per content block (thinking / text / tool_use)
    # and repeats the same `message.usage` on each — summing blindly overcounts
    # by ~2-3x. Count each assistant message, and each tool_use block, once.
    seen_msgs, seen_credit, seen_tools = set(), set(), set()

    for k, ev in enumerate(turn):
        # Only work events set elapsed — queue-operation / attachment / system rows and
        # skipped echoes (a /model typed the next morning) can land hours after the turn.
        working = ev.get("type") in WORK_EVENTS and (k == 0 or not is_user_message(ev))
        e = ts_to_epoch(ev.get("timestamp")) if working else None
        if e:
            stamps.append(e)

        pd = ev.get("providerData") or {}
        raw = pd.get("rawUsage") or {}
        if "credit" in raw and ev.get("id") not in seen_credit:
            seen_credit.add(ev.get("id"))
            try:
                credit += float(raw["credit"])
                have_credit = True
            except Exception:
                pass

        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        u = msg.get("usage") or {}
        msg_key = msg.get("id") or ev.get("id")
        if u and msg_key not in seen_msgs:
            seen_msgs.add(msg_key)
            inp = u.get("input_tokens") or u.get("prompt_tokens") or 0
            cr = u.get("cache_read_input_tokens") or 0
            cw = u.get("cache_creation_input_tokens") or 0
            if raw:
                # CodeBuddy (OpenAI-style): prompt_tokens already include cache hits.
                cr = cr or raw.get("prompt_cache_hit_tokens") or 0
                cw = cw or raw.get("prompt_cache_write_tokens") or 0
                inp = max(0, inp - cr - cw)
            tok["input"] += inp
            tok["output"] += u.get("output_tokens") or u.get("completion_tokens") or 0
            tok["cache_read"] += cr
            tok["cache_write"] += cw
        model = msg.get("model") or pd.get("model") or model

        # tool calls: CodeBuddy = function_call events; Claude = tool_use content blocks
        if ev.get("type") == "function_call":
            name = ev.get("name")
            if name:
                tools.append(name)
            args = ev.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if isinstance(args, dict):
                p = args.get("file_path") or args.get("path")
                if p:
                    files.append(p)
        content = msg.get("content")
        if isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    tkey = blk.get("id")
                    if tkey and tkey in seen_tools:
                        continue
                    if tkey:
                        seen_tools.add(tkey)
                    if blk.get("name"):
                        tools.append(blk["name"])
                    inp = blk.get("input") or {}
                    p = inp.get("file_path") or inp.get("path")
                    if p:
                        files.append(p)

    elapsed = round(max(stamps) - min(stamps), 1) if len(stamps) >= 2 else None
    return {
        "credit": round(credit, 4) if have_credit else None,
        "tokens": tok,
        "model": model,
        "tools": tools,
        "files": sorted(set(files)),
        "elapsed_sec": elapsed,
    }


def agent_of(tpath):
    return "codebuddy" if "/.codebuddy/" in tpath else "claude"


def make_key(agent, session_id, idx):
    return hashlib.sha1(f"{agent}:{session_id}:{idx}".encode()).hexdigest()[:16]


def build_record(events, prompts, start, tpath, session_id, cwd, ts):
    s, e = turn_bounds(events, prompts, start)
    turn = events[s:e]
    facts = collect(turn)
    if facts["credit"] is None and facts["tokens"]["output"] == 0:
        return None
    agent = agent_of(tpath)
    t = facts["tokens"]
    return {
        "turn_key": make_key(agent, session_id, s),
        "agent": agent,
        "session_id": session_id,
        "ts": ts,
        "cwd": cwd,
        "repo": os.path.basename(cwd.rstrip("/")),
        "prompt": (label_of(prompt_text(turn[0])) if turn and s in prompts else "") if RECORD_PROMPTS else "",
        "credit": facts["credit"],
        "input_tokens": t["input"],
        "output_tokens": t["output"],
        "cache_read_tokens": t["cache_read"],
        "cache_write_tokens": t["cache_write"],
        "total_tokens": t["input"] + t["cache_read"] + t["cache_write"] + t["output"],
        "usage_v": USAGE_V,
        "elapsed_sec": facts["elapsed_sec"],
        "model": facts["model"],
        "n_tool_calls": len(facts["tools"]),
        "tools": sorted(set(facts["tools"])),
        "files_touched": facts["files"][:40],
        "transcript": tpath,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        log("no/invalid stdin payload:", e)
        return

    tpath = payload.get("transcript_path") or ""
    if not tpath or not os.path.isfile(tpath):
        log("no transcript_path:", tpath)
        return

    if agent_of(tpath) == "codebuddy":
        wait_for_settle(tpath)

    events = load_events(tpath)
    if not events:
        log("empty transcript")
        return

    prompts = human_prompt_indices(events)
    start = prompts[-1] if prompts else 0
    session_id = payload.get("session_id") or os.path.basename(tpath).replace(".jsonl", "")
    rec = build_record(
        events, prompts, start, tpath, session_id,
        payload.get("cwd") or "",
        datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    # Nothing was actually spent (e.g. Stop fired on a no-op) → don't pollute the ledger.
    if rec is None:
        log("turn had no usage — skipped")
        return

    os.makedirs(LEDGER_DIR, exist_ok=True)
    # Cheap dedupe: turn keys only repeat within the same session, so the tail is enough.
    if os.path.exists(LEDGER):
        try:
            with open(LEDGER, "rb") as f:
                f.seek(max(0, os.path.getsize(LEDGER) - 200_000))
                if rec["turn_key"].encode() in f.read():
                    log("duplicate turn_key — skipped")
                    return
        except Exception:
            pass

    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log("wrote", rec["turn_key"], rec["agent"], rec["credit"], rec["total_tokens"])


def normalize_without_transcript(r):
    """Old row whose transcript is gone: fix the token definition arithmetically."""
    if r.get("usage_v") == USAGE_V:
        return r
    if r.get("agent") == "codebuddy":
        r["input_tokens"] = max(0, (r.get("input_tokens") or 0) - (r.get("cache_read_tokens") or 0)
                                - (r.get("cache_write_tokens") or 0))
    r["total_tokens"] = sum((r.get(k) or 0) for k in
                            ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"))
    r["usage_v"] = USAGE_V
    return r


def rebuild():
    """Re-derive every row from its transcript with the current turn rules.

    Old keys hashed the raw index of whatever message started the turn; we find
    that index again, walk back to the real prompt, and recompute. Rows that turn
    out to be pieces of one turn (split by a mid-turn /model) merge into one.
    Manual rows (no transcript) are kept, with token fields normalized.
    """
    if not os.path.exists(LEDGER):
        print("no ledger at", LEDGER)
        return 1
    rows = [json.loads(l) for l in open(LEDGER, encoding="utf-8") if l.strip()]
    cache, out, seen = {}, [], set()
    stats = {"rebuilt": 0, "merged": 0, "kept": 0, "relabeled": 0}

    for r in rows:
        tpath = r.get("transcript") or ""
        if not tpath or not os.path.isfile(tpath):
            out.append(normalize_without_transcript(r))
            stats["kept"] += 1
            continue
        if tpath not in cache:
            ev = load_events(tpath)
            cache[tpath] = (ev, human_prompt_indices(ev))
        events, prompts = cache[tpath]
        agent, sid = r.get("agent"), r.get("session_id")
        old = next((i for i in range(len(events)) if make_key(agent, sid, i) == r.get("turn_key")), None)
        if old is None:
            out.append(normalize_without_transcript(r))
            stats["kept"] += 1
            continue
        start = max([p for p in prompts if p <= old], default=0)
        new = build_record(events, prompts, start, tpath, sid, r.get("cwd") or "", r.get("ts"))
        if new is None:
            out.append(normalize_without_transcript(r))
            stats["kept"] += 1
            continue
        if new["turn_key"] in seen:
            stats["merged"] += 1
            continue
        seen.add(new["turn_key"])
        if RECORD_PROMPTS and new["prompt"] != r.get("prompt"):
            stats["relabeled"] += 1
        for k in ("owner",):
            if k in r:
                new[k] = r[k]
        out.append(new)
        stats["rebuilt"] += 1

    backup = LEDGER + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.replace(LEDGER, backup)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, LEDGER)
    print(f"{len(rows)} rows → {len(out)} · rebuilt {stats['rebuilt']} · merged {stats['merged']} "
          f"· kept as-is {stats['kept']} · prompt changed {stats['relabeled']}")
    print("backup:", backup)
    return 0


if __name__ == "__main__":
    if "--rebuild" in sys.argv[1:]:
        sys.exit(rebuild())
    try:
        main()
    except Exception as e:      # a hook must never break the agent's turn
        log("unhandled:", e)
    sys.exit(0)
