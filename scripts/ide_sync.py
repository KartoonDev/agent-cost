#!/usr/bin/env python3
"""Pull CodeBuddy IDE turns into the ledger.

    python3 ide_sync.py            # append every finished IDE request not yet in the ledger
    python3 ide_sync.py --dry-run  # count only
    python3 ide_sync.py --watch    # keep syncing every 3 s (dashboard.py already does this itself)

The IDE never fires the Stop hook, but it does keep per-request usage on disk:

    <app data>/CodeBuddyExtension/Data/<uid>/CodeBuddyIDE/<uid>/
        history/<md5(workspace path)>/<conversation>/index.json   ← requests[].usage
        history/.../messages/<id>.json                              ← prompt, model, tool calls

<app data> is ~/Library/Application Support (macOS), %APPDATA% (Windows) or
~/.config (Linux); override with $CODEBUDDY_APPDATA.

One request = one turn (a prompt and everything the agent did for it), the same
unit capture.py writes. Rows land as agent "codebuddy" with source "ide" so the
report and dashboard count them next to the CLI; the credit is the IDE's own
number, not an estimate.

Idempotent: turn_key is derived from the request id, and index.json files whose
mtime hasn't changed since the last run are skipped. Requests still running are
left for the next run.
"""
import datetime, glob, hashlib, json, os, re, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cost_paths import ledger_dir, record_prompts

USAGE_V = 2  # same token definition as capture.py
PATH_RE = re.compile(r"((?:/Users|/home)/[^\s\"'\\<>`]+|[A-Za-z]:\\\\[^\s\"'<>`]+)")


def app_roots():
    if os.environ.get("CODEBUDDY_APPDATA"):
        return [os.path.expanduser(os.environ["CODEBUDDY_APPDATA"])]
    home = os.path.expanduser("~")
    return [os.path.join(home, "Library", "Application Support"),
            os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
            os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")]


def globs(*parts):
    out = []
    for root in app_roots():
        out += glob.glob(os.path.join(root, *parts))
    return out


def turn_key(request_id):
    return hashlib.sha1(f"codebuddy:ide:{request_id}".encode()).hexdigest()[:16]


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def known_workspaces():
    """md5(path) → path from the IDE's workspaceStorage; md5 → folder name from log file names."""
    paths, names = {}, {}
    for f in globs("CodeBuddy", "User", "workspaceStorage", "*", "workspace.json"):
        try:
            uri = json.load(open(f, encoding="utf-8")).get("folder") or ""
        except Exception:
            continue
        if uri.startswith("file://"):
            p = urllib.parse.unquote(uri[7:]).rstrip("/")
            paths[md5(p)] = p
    for f in globs("CodeBuddyExtension", "Logs", "CodeBuddyIDE", "*", "*__*.log"):
        name, h = os.path.basename(f)[:-4].rsplit("__", 1)
        names.setdefault(h, name)
    return paths, names


def load_msg(conv, mid):
    try:
        m = json.load(open(os.path.join(conv, "messages", mid + ".json"), encoding="utf-8"))
        inner = json.loads(m.get("message") or "{}")
        extra = json.loads(m.get("extra") or "{}")
    except Exception:
        return None
    return {"role": m.get("role"), "at": m.get("createdAt"), "content": inner.get("content"), "extra": extra}


def blocks(msg):
    return [b for b in msg["content"] if isinstance(b, dict)] if isinstance(msg["content"], list) else []


def text_of(msg):
    src = msg["extra"].get("sourceContentBlocks") or []
    t = " ".join(b.get("text", "") for b in src if b.get("type") == "text").strip()
    if t:
        return t
    for b in blocks(msg):
        m = re.search(r"<user_query>\s*(.*?)\s*</user_query>", b.get("text", ""), re.S)
        if m:
            return m.group(1)
    return ""


def resolve_path(ws, msgs, paths):
    """The workspace dir is md5-hashed into the history path — confirm a candidate by hashing it."""
    if ws in paths:
        return paths[ws]
    for msg in msgs:
        for b in blocks(msg):
            for p in PATH_RE.findall(json.dumps(b, ensure_ascii=False)):
                p = p.rstrip("/.,:;)")
                while p.count("/") >= 3:
                    if md5(p) == ws:
                        paths[ws] = p
                        return p
                    p = p.rsplit("/", 1)[0]
    return ""


def parse_at(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def records(index_path, seen, paths, names, prompts, since=None):
    conv = os.path.dirname(index_path)
    ws = os.path.basename(os.path.dirname(conv))
    try:
        data = json.load(open(index_path, encoding="utf-8"))
    except Exception:
        return
    for req in data.get("requests") or []:
        u, start = req.get("usage"), req.get("startedAt")
        if req.get("state") != "complete" or not u or not start or turn_key(req["id"]) in seen:
            continue
        started = datetime.datetime.fromtimestamp(start / 1000).astimezone()
        if since and started.date() < since:
            continue
        msgs = [m for m in (load_msg(conv, mid) for mid in req.get("messages") or []) if m]
        users = [m for m in msgs if m["role"] == "user" and not m["extra"].get("isHelperMessage")]
        tools, files = [], []
        for m in msgs:
            if m["role"] != "assistant":
                continue
            for b in blocks(m):
                if b.get("type") != "tool-call":
                    continue
                tools.append(b.get("toolName") or "?")
                args = b.get("args")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if isinstance(args, dict) and b.get("toolName") in ("write_to_file", "replace_in_file", "read_file"):
                    p = args.get("filePath") or args.get("path") or args.get("target_file")
                    if isinstance(p, str):
                        files.append(p)
        model = next((m["extra"].get("modelId") for m in msgs if m["extra"].get("modelId")), None)
        stamps = [t for t in (parse_at(m["at"]) for m in msgs if m.get("at")) if t]
        elapsed = round(max(stamps) - start / 1000, 1) if stamps else None
        cwd = resolve_path(ws, msgs, paths)

        # IDE inputTokens include cache hits and writes, like the CLI's prompt_tokens.
        cache_read, cache_write = u.get("cacheTokens") or 0, u.get("cachedWriteTokens") or 0
        inp = max(0, (u.get("inputTokens") or 0) - cache_read - cache_write)
        out = u.get("outputTokens") or 0
        yield {
            "turn_key": turn_key(req["id"]),
            "agent": "codebuddy",
            "source": "ide",
            "session_id": os.path.basename(conv),
            "ts": started.isoformat(timespec="seconds"),
            "cwd": cwd,
            "repo": os.path.basename(cwd) if cwd else names.get(ws, "?"),
            "prompt": (" ".join(text_of(users[0]).split())[:400] if users else "") if prompts else "",
            "credit": u.get("credit"),
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "total_tokens": inp + cache_read + cache_write + out,
            "usage_v": USAGE_V,
            "elapsed_sec": elapsed if elapsed is None or elapsed >= 0 else None,
            "model": model,
            "n_tool_calls": len(tools),
            "tools": sorted(set(tools)),
            "files_touched": sorted(set(files))[:40],
            "ide_history": index_path,
        }


def ledger_keys(ledger):
    seen = set()
    try:
        with open(ledger, encoding="utf-8") as fh:
            for line in fh:
                m = re.search(r'"turn_key":\s*"([^"]+)"', line)
                if m:
                    seen.add(m.group(1))
    except OSError:
        pass
    return seen


def sync(dry_run=False, since=None):
    """Append new IDE turns; return them. With `since`, rescan everything and leave the mtime cache alone."""
    d = ledger_dir()
    ledger, state_path = os.path.join(d, "ledger.jsonl"), os.path.join(d, ".ide_sync.json")
    try:
        state = {} if since else json.load(open(state_path, encoding="utf-8"))
    except Exception:
        state = {}
    changed = {}
    for f in globs("CodeBuddyExtension", "Data", "*", "CodeBuddyIDE", "*", "history", "*", "*", "index.json"):
        try:
            mt = os.stat(f).st_mtime_ns
        except OSError:
            continue
        if state.get(f) != mt:
            changed[f] = mt
    if not changed:
        return []

    seen = ledger_keys(ledger)
    paths, names = known_workspaces()
    prompts = record_prompts()
    new = []
    for f in sorted(changed):
        for rec in records(f, seen, paths, names, prompts, since):
            seen.add(rec["turn_key"])
            new.append(rec)
    if dry_run:
        return new

    new.sort(key=lambda r: r["ts"])
    if new:
        os.makedirs(d, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as fh:
            for rec in new:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if not since:
        state.update(changed)
        os.makedirs(d, exist_ok=True)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, state_path)
    return new


def main():
    argv = sys.argv[1:]
    if "--watch" in argv:
        print("watching CodeBuddy IDE history (Ctrl+C to stop)", flush=True)
        try:
            while True:
                try:
                    n = len(sync())
                    if n:
                        print(datetime.datetime.now().strftime("%H:%M:%S"), f"added {n}", flush=True)
                except Exception as e:
                    print("sync failed:", e, file=sys.stderr, flush=True)
                time.sleep(3)
        except KeyboardInterrupt:
            pass
        return
    dry = "--dry-run" in argv
    new = sync(dry_run=dry)
    print(f"{'would add' if dry else 'added'} {len(new)} CodeBuddy IDE turn(s)")


if __name__ == "__main__":
    main()
