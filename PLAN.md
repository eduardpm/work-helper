# work-helper — Plan

A personal tool that collects my work data (Slack, Jira, GitLab, my own notes),
categorizes it with a local LLM (LM Studio), and stores it as Markdown in an
Obsidian vault. Later I ask questions like "what is left to do on the Renovate
ticket?" and the tool finds the answer with ripgrep plus the local model.

## Decisions made

- Meeting transcripts are out of scope. I write my own notes and drop them in a folder.
- Language: Python. Target Python 3.9 (the system Python on this machine).
- All processing stays local. LM Studio serves the model at `http://localhost:1234/v1`.
- Tokens live in environment variables, never in config files or the vault.
- The tool runs on a company laptop. Keep dependencies few and well known.

## Architecture

Three parts, three CLI commands. Each part works alone.

```
collect  ->  vault/raw/<date>/*.json     (fetch, deterministic, no LLM)
index    ->  vault/topics/*.md           (LM Studio categorizes raw items)
             vault/daily/<date>.md
ask      ->  answer in the terminal      (ripgrep + LM Studio over the vault)
```

Why separate: fetching is cheap and repeatable. LLM work is slow and can fail.
If the indexer fails, I re-run it on the saved raw files without fetching again.

## Vault layout

```
vault/
  raw/2026-08-31/slack-C0123-1725000000.json   # one raw item per file
  topics/renovate-config.md                    # one note per thread of work
  daily/2026-08-31.md                          # what happened that day
  .state.json                                  # per-source cursors, processed IDs
```

Topic notes carry YAML frontmatter (`tags`, `people`, `jira`, `updated`).
The frontmatter makes ripgrep and Obsidian search precise.

## Collectors

Each collector saves `RawItem` JSON files: source, stable ID, permalink, author,
timestamp, title, content. The stable ID prevents duplicates on re-runs.
Each collector stores a cursor (last fetch time) in `.state.json`.

- **Slack** (`slack_sdk`, user token): `conversations.history` for the channels
  in the config, since the cursor. Thread replies get merged into the parent item.
- **Jira** (REST, email + API token): JQL such as
  `updated >= <cursor> AND (assignee = currentUser() OR ...)`.
  One item per issue with description, status, and comments.
- **GitLab** (REST, personal token): MRs where I am author or reviewer, updated
  since the cursor. One item per MR with description and discussion notes.
- **Notes** (no API): reads Markdown or text files from a drop folder, then
  moves them into `raw/`.

## Indexer

For each unprocessed raw item:

1. Read the list of existing topic names from the vault frontmatter.
2. Send the item plus that topic list to LM Studio. Ask for JSON only:
   topic slug (existing or new), title, tags, people, summary, todos, links.
3. Python renders the Markdown, not the model. The script merges the result
   into the topic note (log entry + new TODO checkboxes) and the daily note.
4. Mark the item processed in `.state.json`.

Known risk: merging is harder than labeling. A small model will sometimes put a
Slack thread and its Jira ticket in different topics. Mitigations: pass the
existing topic list in the prompt, prefer Jira keys and MR numbers as anchors,
and use a 14B-class instruction model (Qwen3 14B or similar).

## Answerer

`ask "question"`:

1. LM Studio extracts search terms from the question.
2. ripgrep runs over `vault/` with those terms.
3. The matching topic notes go back to the model with the question.
4. The model answers with quotes and links from the notes.

`search "term"` skips the model and just prints ripgrep matches.

## CLI

```
work-helper collect [slack|jira|gitlab|notes|all]
work-helper index
work-helper ask "what is left on the renovate ticket?"
work-helper search renovate
```

Config: `config.yaml` (vault path, channels, JQL, base URLs, model name).
Secrets: `SLACK_TOKEN`, `JIRA_EMAIL`, `JIRA_TOKEN`, `GITLAB_TOKEN` in the env.

## Milestones

1. **M1 — skeleton + Slack end to end.** Config, state, Slack collector,
   indexer, renderer. Proves categorization quality, the only risky part.
2. **M2 — Jira and GitLab collectors.**
3. **M3 — answerer.** `ask` and `search`.
4. **M4 — polish.** A `collect all && index` daily run, maybe via launchd/cron.

## Out of scope for now

- Meeting transcript ingestion.
- Copying code into the vault. ripgrep searches the codebase in place.
- A UI. Obsidian is the UI for reading; the terminal is the UI for asking.
