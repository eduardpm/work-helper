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
```

Open the vault folder in Obsidian to browse topics and daily notes.

## Tests

```bash
uv run pytest
```
# work-helper
