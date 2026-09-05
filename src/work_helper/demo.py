"""Seed a throwaway vault with realistic data for `work-helper dashboard --demo`
and for tests."""

from __future__ import annotations

import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .collectors.base import RawItem, iso, save_raw
from .indexer.categorize import ItemIndex
from .indexer.render import parse_epic, render_epic, update_daily, update_epic
from .state import State

STATES = {
    "stock-depletion": """### Summary
Stock depletion is the new inventory concept: orders reserve stock at checkout and the warehouse service depletes it on pick. Anna's team owns the events; pricing consumes them, so this decides how our numbers react to reservations.

### Where it stands
- Consumer MR !482 (Anna) handles reserve and deplete events; in review, Anna wants eyes on it before Friday.
- Decision: checkout reserves stock at order placement, not at cart (Anna, Dora).
- INV-131 opened by Bela for the cancellation re-credit question.

### Blockers and questions
- Bela is waiting on Anna's team: do cancellations re-credit stock synchronously?
- Anna is waiting on a reviewer for !482.""",
    "renovate-config": """### Summary
Renovate keeps opening major-version MRs during release week, which floods the platform team. The epic is about picking a schedule and grouping strategy.

### Where it stands
- Dora drafted a renovate.json with grouped majors (!490).
- Csaba raised the blocker in #platform after 14 major MRs landed in release week again.

### Blockers and questions
- Csaba is waiting on the team to agree on a schedule outside release days; Dora prefers grouping majors instead.""",
    "checkout-redesign": """### Summary
New checkout flow behind a feature flag, starting with the address form and then the payment step.

### Where it stands
- Address form aligned with design; MR !455 approved (Dora).
- Checkout reserves stock at order placement, shared decision with the stock depletion epic.

### Blockers and questions
- none known""",
}

# epic tasks the user planned (the indexer never creates tasks)
TASKS = [
    ("payments-migration", "cut over sandbox to new PSP"),
    ("stock-depletion", "review depletion event schema"),
    ("ci-flakes", "retry flaky job manually when it fails"),
    ("checkout-redesign", "add feature flag for new checkout"),
    ("checkout-redesign", "align with design on address form"),
    ("stock-depletion", "review !482 depletion consumer"),
    ("stock-depletion", "write ADR for depletion events"),
    ("renovate-config", "decide renovate schedule"),
    ("renovate-config", "open MR for renovate.json"),
]

# (epic slugs, days ago, source, author, title, event, summary, todos)
ITEMS = [
    (["payments-migration"], 84, "jira", "erik", "PAY-311 migrate to new PSP", "progress", "Erik moved the PSP migration ticket to In Progress.", ["cut over sandbox to new PSP"]),
    (["payments-migration"], 80, "gitlab", "erik", "!401 psp client", "progress", "Erik opened the PSP client MR.", []),
    (["payments-migration"], 77, "slack", "erik", "#payments", "decision", "Team agreed to migrate in two steps: sandbox first, then production.", []),
    (["stock-depletion"], 74, "slack", "anna", "#inventory", "discovery", "Anna introduced the stock depletion concept and asked pricing to react to depletion events.", []),
    (["stock-depletion"], 67, "jira", "anna", "INV-120 depletion events", "progress", "Anna created the epic for depletion events and the first event schema.", ["review depletion event schema"]),
    (["ci-flakes"], 63, "gitlab", "bela", "!420 retry flaky e2e", "progress", "Bela added a retry for the flaky checkout e2e job.", ["retry flaky job manually when it fails"]),
    (["ci-flakes"], 58, "slack", "bela", "#ci", "question", "Bela asked whether the flaky job should be quarantined instead of retried.", []),
    (["stock-depletion"], 52, "slack", "bela", "#inventory", "question", "Bela asked whether cancellations re-credit stock synchronously.", []),
    (["ci-flakes"], 50, "jira", "bela", "CI-77 quarantine flaky job", "decision", "Decision: quarantine the job until the root cause is known.", []),
    (["checkout-redesign"], 41, "jira", "dora", "CHK-9 new checkout flow", "progress", "Dora created the checkout redesign epic.", ["add feature flag for new checkout"]),
    (["stock-depletion", "checkout-redesign"], 36, "slack", "anna", "#inventory", "decision", "Decision: checkout reserves stock at order placement, not at cart.", []),
    (["checkout-redesign"], 29, "gitlab", "dora", "!455 address form", "progress", "Dora opened the address form MR.", ["align with design on address form"]),
    (["stock-depletion"], 22, "gitlab", "anna", "!482 depletion consumer", "progress", "Anna opened the consumer MR in pricing.", ["review !482 depletion consumer"]),
    (["checkout-redesign"], 12, "slack", "dora", "#checkout", "progress", "Address form aligned with design, MR approved.", []),
    (["stock-depletion"], 9, "slack", "anna", "#inventory", "progress", "Anna: consumer handles reserve and deplete events; cancel path still open.", ["write ADR for depletion events"]),
    (["stock-depletion"], 3, "jira", "bela", "INV-131 cancellation re-credit", "question", "Bela opened a ticket for the cancellation re-credit question.", []),
    (["renovate-config"], 2, "slack", "csaba", "#platform", "blocker", "Csaba: Renovate opened 14 major MRs during release week again; blocked on a schedule decision.", ["decide renovate schedule"]),
    (["renovate-config"], 1, "gitlab", "dora", "!490 renovate.json", "progress", "Dora drafted a renovate.json with grouped majors.", ["open MR for renovate.json"]),
    (["stock-depletion"], 0, "slack", "anna", "#inventory", "progress", "Anna asked for review on !482 before Friday.", []),
]

DONE = {("checkout-redesign", "align with design on address form"), ("payments-migration", "cut over sandbox to new PSP")}
MY_TASKS = ["Prepare 1:1 notes for Thursday", "Book time for Q4 planning", "Renew GitLab token"]
# (epic, task, days from today for the due date or None, description)
PLANNED = [
    ("", "Prepare 1:1 notes for Thursday", 0, "Topics: depletion ADR ownership, on-call rotation, Q4 goals."),
    ("stock-depletion", "write ADR for depletion events", 0, "Cover the cancel path and the re-credit question Bela raised.\nAnna wants a draft before Friday."),
    ("renovate-config", "decide renovate schedule", -2, ""),
    ("stock-depletion", "review !482 depletion consumer", 3, ""),
]


def seed_demo(vault: Path | None = None, today: date | None = None) -> Path:
    vault = vault or Path(tempfile.mkdtemp(prefix="work-helper-demo-"))
    today = today or date.today()
    for n, (epics, days_ago, source, author, title, event, summary, todos) in enumerate(ITEMS):
        stamp = datetime.combine(today - timedelta(days=days_ago), time(10, 0), timezone.utc)
        item = RawItem(source=source, id=f"{source}-demo-{n}", url=f"https://{source}.example/{n}",
                       author=author, timestamp=iso(stamp), title=title, content=summary)
        save_raw(vault, item)
        idx = ItemIndex(epics=epics, event=event, summary=summary, people=[author])
        for slug in idx.epics:
            update_epic(vault, item, idx, slug)
        update_daily(vault, item, idx)

    from .dashboard import add_task, set_favorite, update_task

    for slug, task in TASKS:
        add_task(vault, slug, task)
    set_favorite(vault, "stock-depletion", True)
    for slug, text in STATES.items():
        path = vault / "epics" / f"{slug}.md"
        _meta, title, _, todos, log = parse_epic(path.read_text())
        path.write_text(render_epic(_meta, title, text, todos, log))
    for slug, task in DONE:
        path = vault / "epics" / f"{slug}.md"
        path.write_text(path.read_text().replace(f"- [ ] {task}", f"- [x] {task}"))

    lines = [f"- [{'x' if t == MY_TASKS[-1] else ' '}] {t}" for t in MY_TASKS]
    (vault / "tasks.md").write_text("# My tasks\n\n" + "\n".join(lines) + "\n")

    for slug, task, offset, description in PLANNED:
        due = (today + timedelta(days=offset)).isoformat() if offset is not None else ""
        update_task(vault, slug, task, {"due": due, "description": description})

    now = datetime.now(timezone.utc)
    state = State(vault)
    state.synced = {
        "slack": iso(now - timedelta(minutes=48)),
        "jira": iso(now - timedelta(hours=3)),
        "gitlab": iso(now - timedelta(hours=30)),
    }
    state.save()
    return vault
