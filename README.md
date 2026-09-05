# work-helper

Collects my work data (Slack, Jira, GitLab, my own notes), categorizes it with
a local LLM in LM Studio, and stores everything as Markdown in an Obsidian
vault. See [PLAN.md](PLAN.md) for the design.

## Setup

Needs [uv](https://docs.astral.sh/uv/) (`brew install uv`). uv installs the
right Python and all dependencies on its own.

```bash
uv sync
cp config.example.yaml config.yaml   # then edit it
```

Secrets go in the environment (e.g. in `~/.zshrc` or a local `.env` you source):

```bash
export SLACK_TOKEN=xoxp-...      # Slack user token
export JIRA_EMAIL=me@company.com
export JIRA_TOKEN=...            # Atlassian API token
export GITLAB_TOKEN=glpat-...    # GitLab personal access token
```

Start LM Studio, load a model (14B-class instruction model recommended), and
enable the local server. Put the model name in `config.yaml`.

## Use

```bash
uv run work-helper collect          # fetch new items -> vault/raw/<date>/
uv run work-helper index            # LM Studio categorizes -> vault/topics/, vault/daily/
uv run work-helper ask "what is left to do on the renovate ticket?"
uv run work-helper search renovate  # plain ripgrep, no LLM
uv run work-helper dashboard        # local dashboard app: tasks, epics, sync status
uv run work-helper dashboard --demo # same, on a throwaway vault with seed data
```

Open the vault folder in Obsidian to browse topics and daily notes.

The dashboard serves `http://127.0.0.1:8787` and opens it in the browser. It has
three views: **Today** (tasks due today or overdue; the calendar button on a
task plans it for today, and tasks added here get today's date), **Tasks** (your
own list in `vault/tasks.md` plus the TODOs of every epic; add and tick tasks
there, click a task to give it a description, the notes are edited in place) and **Epics**
(cards with status, blockers and weekly activity on the left; the selected
epic's State summary and log timeline on the right). Each open epic has a
chat panel: your message goes to `codex exec` running inside the vault with the
epic note as context, so you can ask questions or tell it to refine the State and
TODOs (it edits the note in place). Model and effort are set under `codex:` in
`config.yaml`. The sidebar shows when each integration last synced; the button
next to each one re-collects that source, and **Sync all** collects everything
and runs the indexer, like `work-helper sync`. To run it as a Dock app: open the URL in
Safari and choose File > Add to Dock.

Star an epic to mark it as a favorite (stored in the note's frontmatter); the
Favorites button in the top bar hides everything else in every view. The indexer
never creates tasks; you add them in the dashboard or in Obsidian. After changing
the State format, `uv run work-helper index --restate` rewrites every epic's State.

Three more views: **Changes** lists every log entry by day and marks the days
since you last opened the app as new. **Blockers** collects the entries the
indexer tagged as blocker or question, grouped by epic. **Ask** is the Codex chat
for the whole vault, not one epic.

Task lines use the Obsidian Tasks format, so the vault stays readable in Obsidian:

```markdown
- [ ] write ADR for depletion events 📅 2026-09-05
    Cover the cancel path and the re-credit question.
```

## Tests

```bash
uv run pytest
```
# work-helper
