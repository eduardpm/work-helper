"""Local dashboard: a tiny HTTP server on localhost serving one page.

Tasks are checkbox lines: personal ones in vault/tasks.md, epic ones in the
TODO section of vault/epics/<slug>.md. Ticking or adding a task edits the note,
so Obsidian and the indexer see the same thing."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .answer.answer import ANSWER_PROMPT
from .collectors import SOURCES, collect_sources
from .config import CodexConfig, Config
from .indexer.categorize import normalize_slug
from .indexer.render import DUE_MARK, epic_path, parse_epic, render_epic
from .state import State

WEEKS = 12
QUIET_DAYS = 14
MY_TASKS = "tasks.md"
PLACEHOLDER = "(nothing tracked yet)"
LOG_ENTRY = re.compile(r"^### (\d{4}-\d{2}-\d{2}) ", re.MULTILINE)
EVENT = re.compile(r"^\*\*(\w+)\*\*", re.MULTILINE)
LOG_SPLIT = re.compile(r"^### ", re.MULTILINE)
LOG_ITEM = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\w+) — (.*?)(?: — \[[^\]]*\]\((\S+)\))?\s*\n(?:\*\*(\w+)\*\* — )?(.*)", re.DOTALL
)
PAGE = Path(__file__).with_name("dashboard.html")
THREAD_ID = re.compile(r"[0-9a-fA-F-]{36}")

VAULT_LAYOUT = """You are the assistant inside a personal work knowledge base: an Obsidian vault
of Markdown notes, which is the current working directory.
- epics/<slug>.md: one note per epic (a big thread of work). Fixed structure: YAML
  frontmatter (tags, people, refs, updated), "# Title", "## State" (catch-up
  summary), "## TODO" ("- [ ] item 📅 YYYY-MM-DD" lines with indented description
  lines; the ticks and dates belong to the user), "## Log" (newest first, one
  "### <date> <source> — <title> — [link]" entry per item).
- tasks.md: the user's personal task list, same checkbox format.
- raw/<date>/*.json: the original Slack, Jira, GitLab and notes items. grep them
  when the notes are not enough.
- daily/<date>.md: what happened that day.
"""

EDIT_RULES = """When the user asks to REFINE a note (rewrite the State, add, remove or reword
TODOs, fix tags, people, refs or the title), edit it in place and keep the
structure above. The State has exactly three "###" sections: "Summary" (2-4
sentences), "Where it stands" (bullets, newest first, with names and ticket or MR
keys) and "Blockers and questions" (bullets with who waits on whom, or "- none
known"). Prefer newer log entries when they conflict. Never tick or untick TODO
boxes or change their dates; only add or reword TODOs when the user asks. Do not
edit files the user did not ask about. Then reply with a short summary of what
you changed.

Reply in plain Markdown, briefly. This is a chat: later messages continue it.
"""

CHAT_INSTRUCTIONS = VAULT_LAYOUT + """
The user is asking about the epic "{title}" (epics/{slug}.md, shown below).

When the user asks a QUESTION:
{answer_rules}
""" + EDIT_RULES + """
=== epics/{slug}.md ===
{note}
"""

VAULT_INSTRUCTIONS = VAULT_LAYOUT + """
The user is asking about their work as a whole, not one epic. Start from the
State sections of the epic notes below, then grep the notes and raw items.

EPICS (slug — title — last activity):
{epics}

When the user asks a QUESTION:
{answer_rules}
""" + EDIT_RULES

ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_task(stripped: str) -> bool:
    return stripped[:3] == "- [" and stripped[4:6] == "] " and PLACEHOLDER not in stripped


def _todo_lines(lines) -> list[dict]:
    """Checkbox lines -> tasks. '- [x] text 📅 2026-09-05' carries the due date;
    indented lines under a task are its description."""
    out = []
    for line in lines:
        s = line.strip()
        if _is_task(s):
            rest = s[6:].strip()
            m = DUE_MARK.search(rest)
            out.append({"text": DUE_MARK.sub("", rest).strip(), "done": s[3] != " ",
                        "due": m.group(1) if m else "", "description": ""})
        elif out and s and line[:1] in (" ", "\t"):
            out[-1]["description"] = (out[-1]["description"] + "\n" + s).strip()
    return out


def _task_entry(text: str, done: bool = False, due: str = "", description: str = "", indent: str = "") -> str:
    head = f"{indent}- [{'x' if done else ' '}] {text}" + (f" 📅 {due}" if due else "")
    body = [f"{indent}    {ln.strip()}" for ln in description.splitlines() if ln.strip()]
    return "\n".join([head, *body])


def _todo_file(vault: Path, slug: str) -> Path | None:
    """'' is the personal list; anything else must be a clean epic slug."""
    if not slug:
        return vault / MY_TASKS
    return epic_path(vault, slug) if slug == normalize_slug(slug) else None


def _events(log: str) -> list[dict]:
    """Log entries as written by update_epic -> structured events, newest first."""
    out = []
    for chunk in LOG_SPLIT.split(log):
        m = LOG_ITEM.match(chunk.strip())
        if m:
            out.append({"date": m[1], "source": m[2], "title": m[3].strip(), "url": m[4] or "",
                        "kind": m[5] or "", "summary": m[6].strip()})
    return out


def _epic(path: Path, today: date) -> dict:
    meta, title, state, todos, log = parse_epic(path.read_text())
    dates = sorted(date.fromisoformat(d) for d in LOG_ENTRY.findall(log))
    counts = [0] * WEEKS
    for d in dates:
        wk = (today - d).days // 7
        if 0 <= wk < WEEKS:
            counts[WEEKS - 1 - wk] += 1
    if not dates:
        status = "empty"
    elif (today - dates[0]).days < QUIET_DAYS:
        status = "new"
    elif (today - dates[-1]).days >= QUIET_DAYS:
        status = "quiet"
    else:
        status = "active"
    return {
        "slug": path.stem,
        "title": title,
        "favorite": bool(meta.get("favorite")),
        "state": state,
        "log": log,
        "events": _events(log),
        "todos": _todo_lines("\n".join(todos).splitlines()),
        "entries": len(dates),
        "blockers": EVENT.findall(log).count("blocker"),
        "since": dates[0].isoformat() if dates else "",
        "last": dates[-1].isoformat() if dates else "",
        "counts": counts,
        "status": status,
    }


def _sync(vault: Path) -> dict:
    state = State(vault)
    raw = list((vault / "raw").glob("*/*.json")) if (vault / "raw").exists() else []
    out = {}
    for source in SOURCES:
        mine = [p for p in raw if p.name.startswith(source + "-")]
        out[source] = {
            "synced": state.synced.get(source),
            "items": len(mine),
            "last_item": max((p.parent.name for p in mine), default=None),
        }
    return out


def payload(vault: Path, today: date | None = None) -> dict:
    today = today or date.today()
    epics = [_epic(p, today) for p in (vault / "epics").glob("*.md")]
    epics.sort(key=lambda e: (e["last"], e["slug"]), reverse=True)

    tasks = []
    my = vault / MY_TASKS
    if my.exists():
        tasks += [{"epic": "", "epic_title": "My tasks", **t} for t in _todo_lines(my.read_text().splitlines())]
    for e in epics:
        tasks += [{"epic": e["slug"], "epic_title": e["title"], **t} for t in e.pop("todos")]

    monday = today - timedelta(days=today.weekday())
    weeks = [(monday - timedelta(weeks=WEEKS - 1 - i)).isoformat() for i in range(WEEKS)]
    return {
        "today": today.isoformat(),
        "vault": str(vault),
        "weeks": weeks,
        "sync": _sync(vault),
        "epics": epics,
        "tasks": tasks,
    }


def update_task(vault: Path, slug: str, text: str, patch: dict) -> bool:
    """Edit one task line in place. patch may set done (bool), due ('' or
    YYYY-MM-DD) and description (str). Returns False if not found or invalid."""
    path = _todo_file(vault, slug)
    if path is None or not path.exists() or not text:
        return False
    due = patch.get("due")
    if due is not None and due != "" and not ISO_DAY.fullmatch(str(due)):
        return False
    lines = path.read_text().split("\n")
    # ponytail: first task with this exact title wins; duplicate titles in one note would collide
    for i, line in enumerate(lines):
        if _is_task(line.strip()) and _todo_lines([line])[0]["text"] == text:
            break
    else:
        return False
    j = i + 1  # description lines: indented, non-empty, not a new task
    while j < len(lines) and lines[j].strip() and lines[j][:1] in (" ", "\t") and not _is_task(lines[j].strip()):
        j += 1
    current = _todo_lines(lines[i:j])[0]
    indent = line[: len(line) - len(line.lstrip())]
    lines[i:j] = _task_entry(
        text,
        done=bool(patch.get("done", current["done"])),
        due=str(due if due is not None else current["due"]),
        description=str(patch.get("description", current["description"]) or ""),
        indent=indent,
    ).split("\n")
    path.write_text("\n".join(lines))
    return True


def set_favorite(vault: Path, slug: str, favorite: bool) -> bool:
    """Store the star in the epic's frontmatter, so Obsidian sees it too."""
    path = _todo_file(vault, slug) if slug else None
    if path is None or not path.exists():
        return False
    meta, title, state, todos, log = parse_epic(path.read_text())
    if favorite:
        meta["favorite"] = True
    else:
        meta.pop("favorite", None)
    path.write_text(render_epic(meta, title, state, todos, log))
    return True


def toggle_task(vault: Path, slug: str, text: str) -> bool:
    path = _todo_file(vault, slug)
    if path is None or not path.exists():
        return False
    found = [t for t in _todo_lines(path.read_text().splitlines()) if t["text"] == text]
    return bool(found) and update_task(vault, slug, text, {"done": not found[0]["done"]})


def add_task(vault: Path, slug: str, text: str, due: str = "", description: str = "") -> bool:
    text = " ".join(text.split())
    path = _todo_file(vault, slug)
    if not text or path is None or (due and not ISO_DAY.fullmatch(due)):
        return False
    entry = _task_entry(text, due=due, description=description)
    if not slug:
        old = path.read_text() if path.exists() else "# My tasks\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(old.rstrip("\n") + "\n" + entry + "\n")
        return True
    if not path.exists():
        return False
    meta, title, state, todos, log = parse_epic(path.read_text())
    todos = [t for t in todos if PLACEHOLDER not in t] + [entry]
    path.write_text(render_epic(meta, title, state, todos, log))
    return True


def chat(vault: Path, codex: CodexConfig, slug: str, text: str, thread: str = "") -> dict:
    """One chat turn about an epic via `codex exec`. Returns {reply, thread} or {error}."""
    path = _todo_file(vault, slug) if slug else None
    if slug and (path is None or not path.exists()):
        return {"error": "Unknown epic."}
    text = text.strip()
    if not text:
        return {"error": "Empty message."}
    thread = thread if THREAD_ID.fullmatch(thread or "") else ""
    if not thread and slug:
        note = path.read_text()
        _meta, title, *_ = parse_epic(note)
        text = CHAT_INSTRUCTIONS.format(title=title, slug=slug, answer_rules=ANSWER_PROMPT, note=note) + "\nUSER:\n" + text
    elif not thread:
        epics = sorted((_epic(p, date.today()) for p in (vault / "epics").glob("*.md")), key=lambda e: e["last"], reverse=True)
        listing = "\n".join(f"- {e['slug']} — {e['title']} — {e['last'] or 'no activity'}" for e in epics) or "(no epics yet)"
        text = VAULT_INSTRUCTIONS.format(epics=listing, answer_rules=ANSWER_PROMPT) + "\nUSER:\n" + text

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "reply.md"
        cmd = [codex.command, "exec"]
        if thread:
            cmd += ["resume", thread]
        else:
            cmd += ["-C", str(vault), "-s", "workspace-write"]  # resume keeps these from the first turn
        cmd += ["--json", "--skip-git-repo-check", "-m", codex.model,
                "-c", f'model_reasoning_effort="{codex.reasoning}"', "-o", str(out), "-"]
        try:
            proc = subprocess.run(cmd, cwd=vault, input=text, capture_output=True, text=True, timeout=codex.timeout, check=False)
        except FileNotFoundError:
            return {"error": f"`{codex.command}` not found. Install the Codex CLI (npm i -g @openai/codex) or set codex.command in config.yaml."}
        except subprocess.TimeoutExpired:
            return {"error": f"Codex did not answer within {codex.timeout} s."}
        errors = []
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "thread.started":
                thread = ev.get("thread_id") or thread
            elif ev.get("type") == "error":
                errors.append(str(ev.get("message")))
            elif ev.get("type") == "turn.failed":
                errors.append(str((ev.get("error") or {}).get("message")))
        reply = out.read_text().strip() if out.exists() else ""
    if not reply:
        detail = errors[-1] if errors else proc.stderr.strip()[-1500:] or f"Codex exited with code {proc.returncode} and no reply."
        return {"error": detail, "thread": thread}
    return {"reply": reply, "thread": thread}


_sync_lock = threading.Lock()


def sync(cfg: Config | None, source: str) -> dict:
    """Collect one source, or all sources followed by an index run."""
    if cfg is None:
        return {"error": "Sync needs a config.yaml; the demo vault has no integrations."}
    if source != "all" and source not in SOURCES:
        return {"error": "Unknown source."}
    if not _sync_lock.acquire(blocking=False):
        return {"error": "A sync is already running."}
    try:
        raw = collect_sources(cfg, SOURCES if source == "all" else (source,))
        out = {"results": {k: (f"{v} new item{'s' if v != 1 else ''}" if isinstance(v, int) else v) for k, v in raw.items()}}
        if source == "all":
            from .indexer import run_index

            try:
                out["indexed"] = run_index(cfg)
            except Exception as exc:  # noqa: BLE001 - LM Studio down must not hide the collect results
                out["index_error"] = f"index failed: {exc}"
        return out
    finally:
        _sync_lock.release()


class Handler(BaseHTTPRequestHandler):
    vault: Path
    cfg: Config | None = None
    codex: CodexConfig = CodexConfig()

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api":
            self._json(200, payload(self.vault))
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path not in ("/task", "/tasks", "/chat", "/sync", "/epic"):
            return self._send(404, b"not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
            epic, text = str(body.get("epic", "")), str(body.get("text", ""))
        except (ValueError, TypeError, AttributeError):
            return self._json(400, {"ok": False})
        if self.path == "/chat":
            res = chat(self.vault, self.codex, epic, text, str(body.get("thread") or ""))
            return self._json(200 if "reply" in res else 400, res)
        if self.path == "/sync":
            res = sync(self.cfg, str(body.get("source", "all")))
            return self._json(200 if "results" in res else 400, res)
        if self.path == "/epic":
            ok = set_favorite(self.vault, epic, bool(body.get("favorite")))
            return self._json(200 if ok else 400, {"ok": ok})
        if self.path == "/tasks":  # create
            ok = add_task(self.vault, epic, text, str(body.get("due") or ""), str(body.get("description") or ""))
        else:  # edit: done / due / description
            patch = {k: body[k] for k in ("done", "due", "description") if k in body}
            ok = update_task(self.vault, epic, text, patch)
        self._json(200 if ok else 400, {"ok": ok})


def serve(vault: Path, port: int = 8787, open_browser: bool = True, cfg: Config | None = None) -> None:
    Handler.vault = vault
    Handler.cfg = cfg
    Handler.codex = cfg.codex if cfg else CodexConfig()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"dashboard at {url}  (Ctrl-C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
