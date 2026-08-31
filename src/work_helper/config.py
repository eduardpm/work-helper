from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class LMStudioConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen/qwen3-14b"


@dataclass
class SlackConfig:
    channels: List[str] = field(default_factory=list)


@dataclass
class JiraConfig:
    base_url: str = ""
    jql: str = (
        'updated >= "{cursor}" AND '
        "(assignee = currentUser() OR reporter = currentUser())"
    )


@dataclass
class GitlabConfig:
    base_url: str = ""


@dataclass
class Config:
    vault: Path
    notes_inbox: Path
    lmstudio: LMStudioConfig
    slack: SlackConfig
    jira: JiraConfig
    gitlab: GitlabConfig


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def find_config_path() -> Path:
    env = os.environ.get("WORK_HELPER_CONFIG")
    if env:
        return _expand(env)
    for candidate in (Path("config.yaml"), Path.home() / ".config/work-helper/config.yaml"):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "No config.yaml found. Copy config.example.yaml to config.yaml, "
        "or set WORK_HELPER_CONFIG."
    )


def load_config(path: Path = None) -> Config:
    if path is None:
        path = find_config_path()
    data = yaml.safe_load(path.read_text()) or {}

    vault = _expand(data.get("vault", "~/work-vault"))
    notes_inbox = _expand(data.get("notes_inbox", str(vault / "notes-inbox")))

    lm = data.get("lmstudio", {}) or {}
    slack = data.get("slack", {}) or {}
    jira = data.get("jira", {}) or {}
    gitlab = data.get("gitlab", {}) or {}

    return Config(
        vault=vault,
        notes_inbox=notes_inbox,
        lmstudio=LMStudioConfig(
            base_url=lm.get("base_url", LMStudioConfig.base_url),
            model=lm.get("model", LMStudioConfig.model),
        ),
        slack=SlackConfig(channels=list(slack.get("channels", []) or [])),
        jira=JiraConfig(
            base_url=(jira.get("base_url", "") or "").rstrip("/"),
            jql=jira.get("jql", JiraConfig.jql),
        ),
        gitlab=GitlabConfig(base_url=(gitlab.get("base_url", "") or "").rstrip("/")),
    )


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value
