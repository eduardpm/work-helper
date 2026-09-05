import json
import threading
from datetime import date
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from work_helper.dashboard import Handler, add_task, payload, toggle_task, update_task
from work_helper.demo import seed_demo

TODAY = date(2026, 9, 5)


def test_payload_epics_tasks_and_sync(tmp_path):
    seed_demo(tmp_path, TODAY)
    data = payload(tmp_path, TODAY)
    assert len(data["weeks"]) == 12 and data["weeks"][-1] == "2026-08-31"
    by = {e["slug"]: e for e in data["epics"]}
    assert data["epics"][0]["slug"] == "stock-depletion"  # most recent activity first
    assert by["renovate-config"]["status"] == "new" and by["renovate-config"]["blockers"] == 1
    assert by["ci-flakes"]["status"] == "quiet" and by["payments-migration"]["status"] == "quiet"
    assert by["checkout-redesign"]["status"] == "active"
    assert sum(by["stock-depletion"]["counts"]) == 8 and by["stock-depletion"]["counts"][-1] == 2
    assert "todos" not in by["stock-depletion"]  # moved into tasks
    assert by["stock-depletion"]["log"].count("### ") == 8 and by["stock-depletion"]["state"].startswith("### Summary")
    events = by["stock-depletion"]["events"]
    assert len(events) == 8 and events[0]["date"] == "2026-09-05" and events[-1]["date"] == "2026-06-23"
    assert events[2] == {"date": "2026-08-27", "source": "slack", "title": "#inventory", "url": "https://slack.example/14",
                         "kind": "progress", "summary": "Anna: consumer handles reserve and deplete events; cancel path still open."}
    assert [e["kind"] for e in by["renovate-config"]["events"]] == ["progress", "blocker"]
    assert by["renovate-config"]["events"][0]["title"] == "!490 renovate.json"

    tasks = data["tasks"]
    mine = [t for t in tasks if t["epic"] == ""]
    assert [t["text"] for t in mine][:2] == ["Prepare 1:1 notes for Thursday", "Book time for Q4 planning"]
    assert mine[2]["done"] is True
    assert {"epic": "checkout-redesign", "epic_title": "Checkout redesign", "text": "align with design on address form", "done": True, "due": "", "description": ""} in tasks
    adr = next(t for t in tasks if t["text"] == "write ADR for depletion events")
    assert adr["due"] == "2026-09-05" and adr["description"].startswith("Cover the cancel path") and "\n" in adr["description"]
    assert data["today"] == "2026-09-05"
    assert data["sync"]["slack"]["items"] == 9 and data["sync"]["slack"]["synced"]
    assert data["sync"]["notes"] == {"synced": None, "items": 0, "last_item": None}
    assert data["sync"]["jira"]["last_item"] == "2026-09-02"


def test_toggle_and_add_tasks(tmp_path):
    seed_demo(tmp_path, TODAY)
    epic = tmp_path / "epics/renovate-config.md"
    assert toggle_task(tmp_path, "renovate-config", "decide renovate schedule")
    assert "- [x] decide renovate schedule" in epic.read_text()
    assert toggle_task(tmp_path, "renovate-config", "decide renovate schedule")
    assert "- [ ] decide renovate schedule" in epic.read_text()
    assert toggle_task(tmp_path, "", "Renew GitLab token")
    assert "- [ ] Renew GitLab token" in (tmp_path / "tasks.md").read_text()
    assert not toggle_task(tmp_path, "renovate-config", "no such task")
    assert not toggle_task(tmp_path, "../evil", "x")

    assert add_task(tmp_path, "", "  Call   the bank ", due="2026-09-06", description="Ask about the fee.")
    assert (tmp_path / "tasks.md").read_text().endswith("- [ ] Call the bank 📅 2026-09-06\n    Ask about the fee.\n")
    assert not add_task(tmp_path, "", "bad date", due="tomorrow")
    assert add_task(tmp_path, "renovate-config", "announce schedule in #platform")
    assert "- [ ] announce schedule in #platform" in epic.read_text()
    assert not add_task(tmp_path, "renovate-config", "   ")
    assert not add_task(tmp_path, "no-such-epic", "x")
    # a fresh personal list is created on first add
    assert add_task(tmp_path / "empty", "", "first") and (tmp_path / "empty/tasks.md").read_text().startswith("# My tasks")


def test_http_routes(tmp_path):
    seed_demo(tmp_path, TODAY)
    Handler.vault = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_address[1])

        def call(method, path, body=None):
            conn.request(method, path, json.dumps(body) if body else None, {"Content-Type": "application/json"})
            r = conn.getresponse()
            return r.status, r.read()

        assert b"Work helper" in call("GET", "/")[1]
        assert call("POST", "/tasks", {"epic": "", "text": "from the browser"})[0] == 200
        assert call("POST", "/task", {"epic": "", "text": "from the browser", "done": True})[0] == 200
        assert call("POST", "/task", {"epic": "", "text": "nope", "done": True})[0] == 400
        assert call("POST", "/nope", {})[0] == 404
        tasks = json.loads(call("GET", "/api")[1])["tasks"]
        assert {"epic": "", "epic_title": "My tasks", "text": "from the browser", "done": True, "due": "", "description": ""} in tasks
    finally:
        server.shutdown()
        server.server_close()


FAKE_CODEX = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
thread = args[args.index("resume") + 1] if "resume" in args else "11111111-2222-4333-8444-555555555555"
print(json.dumps({"type": "thread.started", "thread_id": thread}))
if prompt.splitlines()[-1] == "please fail":
    print(json.dumps({"type": "turn.failed", "error": {"message": "model exploded"}}))
    sys.exit(1)
open(args[args.index("-o") + 1], "w").write(
    "echo: " + prompt.splitlines()[-1] + " model=" + args[args.index("-m") + 1]
    + (" resumed" if "resume" in args else " fresh") + (" sandboxed" if "-s" in args else ""))
"""


def fake_codex(tmp_path):
    from work_helper.config import CodexConfig

    script = tmp_path / "fake-codex"
    script.write_text(FAKE_CODEX)
    script.chmod(0o755)
    return CodexConfig(command=str(script), model="test-model")


def test_chat_runs_codex_and_resumes(tmp_path):
    from work_helper.dashboard import chat

    seed_demo(tmp_path, TODAY)
    codex = fake_codex(tmp_path)
    first = chat(tmp_path, codex, "renovate-config", "what is left?")
    assert first == {"reply": "echo: what is left? model=test-model fresh sandboxed", "thread": "11111111-2222-4333-8444-555555555555"}
    second = chat(tmp_path, codex, "renovate-config", "and who owns it?", first["thread"])
    assert second["reply"] == "echo: and who owns it? model=test-model resumed"
    assert "error" in chat(tmp_path, codex, "renovate-config", "please fail")
    assert chat(tmp_path, codex, "renovate-config", "please fail")["error"] == "model exploded"
    assert chat(tmp_path, codex, "nope", "x") == {"error": "Unknown epic."}
    whole = chat(tmp_path, codex, "", "what is blocked right now?")
    assert whole["reply"] == "echo: what is blocked right now? model=test-model fresh sandboxed"
    assert chat(tmp_path, codex, "renovate-config", "  ") == {"error": "Empty message."}
    assert "not found" in chat(tmp_path, codex.model_copy(update={"command": "/no/such/codex"}), "renovate-config", "hi")["error"]


def test_chat_route(tmp_path):
    seed_demo(tmp_path, TODAY)
    Handler.vault = tmp_path
    Handler.codex = fake_codex(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_address[1])
        conn.request("POST", "/chat", json.dumps({"epic": "ci-flakes", "text": "status?", "thread": "junk"}), {"Content-Type": "application/json"})
        r = conn.getresponse()
        assert r.status == 200
        assert json.loads(r.read())["reply"].startswith("echo: status? model=test-model fresh")
    finally:
        server.shutdown()
        server.server_close()


def test_sync_collects_and_records_time(tmp_path, monkeypatch):
    from work_helper.collectors import collect_sources
    from work_helper.config import Config
    from work_helper.dashboard import sync
    from work_helper.state import State

    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    cfg = Config(vault=tmp_path, jira={"base_url": "https://example.atlassian.net"})
    (cfg.notes_inbox).mkdir(parents=True)
    (cfg.notes_inbox / "standup.md").write_text("talked about renovate")

    results = collect_sources(cfg, ("notes", "jira"))
    assert results["notes"] == 1
    assert results["jira"] == "Missing environment variable: JIRA_EMAIL"
    state = State(tmp_path)
    assert "notes" in state.synced and "jira" not in state.synced

    assert sync(None, "notes")["error"].startswith("Sync needs a config.yaml")
    assert sync(cfg, "nope") == {"error": "Unknown source."}
    assert sync(cfg, "notes") == {"results": {"notes": "0 new items"}}


def test_sync_route(tmp_path):
    from work_helper.config import Config

    seed_demo(tmp_path, TODAY)
    Handler.vault = tmp_path
    Handler.cfg = Config(vault=tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_address[1])
        conn.request("POST", "/sync", json.dumps({"source": "notes"}), {"Content-Type": "application/json"})
        r = conn.getresponse()
        assert r.status == 200 and json.loads(r.read()) == {"results": {"notes": "0 new items"}}
        conn.request("GET", "/api")
        assert json.loads(conn.getresponse().read())["sync"]["notes"]["synced"]
    finally:
        server.shutdown()
        server.server_close()
        Handler.cfg = None


def test_update_task_due_and_description(tmp_path):
    seed_demo(tmp_path, TODAY)
    note = tmp_path / "epics/stock-depletion.md"
    task = "review depletion event schema"
    assert update_task(tmp_path, "stock-depletion", task, {"due": "2026-09-05", "description": "Check with Anna.\n\nSecond line."})
    assert f"- [ ] {task} 📅 2026-09-05\n    Check with Anna.\n    Second line.\n" in note.read_text()
    assert update_task(tmp_path, "stock-depletion", task, {"done": True})  # keeps due + description
    assert f"- [x] {task} 📅 2026-09-05\n    Check with Anna.\n    Second line.\n- [ ] review !482" in note.read_text()
    assert update_task(tmp_path, "stock-depletion", task, {"due": "", "description": ""})
    assert f"- [x] {task}\n- [ ] review !482" in note.read_text()
    assert not update_task(tmp_path, "stock-depletion", task, {"due": "next week"})
    assert not update_task(tmp_path, "stock-depletion", "no such task", {"done": True})
    # a re-index keeps planned tasks exactly as they are
    from test_render import make_index, make_item

    from work_helper.indexer.render import parse_epic, update_epic

    update_task(tmp_path, "stock-depletion", "write ADR for depletion events", {"due": "2026-09-09"})
    update_epic(tmp_path, make_item("z-1"), make_index(["Write ADR for depletion events"], epics=("stock-depletion",)), "stock-depletion")
    todos = parse_epic(note.read_text())[3]
    assert sum("write ADR" in t for t in todos) == 1 and any("📅 2026-09-09\n    Cover the cancel path" in t for t in todos)


def test_favorite_lives_in_frontmatter(tmp_path):
    from work_helper.dashboard import set_favorite
    from work_helper.indexer.render import parse_epic

    seed_demo(tmp_path, TODAY)
    by = {e["slug"]: e for e in payload(tmp_path, TODAY)["epics"]}
    assert by["stock-depletion"]["favorite"] is True and by["ci-flakes"]["favorite"] is False
    assert set_favorite(tmp_path, "ci-flakes", True)
    assert parse_epic((tmp_path / "epics/ci-flakes.md").read_text())[0]["favorite"] is True
    assert set_favorite(tmp_path, "ci-flakes", False)
    assert "favorite" not in parse_epic((tmp_path / "epics/ci-flakes.md").read_text())[0]
    assert not set_favorite(tmp_path, "nope", True)
