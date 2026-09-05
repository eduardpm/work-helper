from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator


class LMStudioConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen/qwen3-14b"


class CodexConfig(BaseModel):
    """`codex exec` settings for the dashboard chat."""

    command: str = "codex"
    model: str = "gpt-5.6-luna"
    reasoning: str = "high"
    timeout: int = 600  # seconds per reply


class JiraConfig(BaseModel):
    base_url: str = ""
    jql: str = (
        'updated >= "{cursor}" AND '
        "(assignee = currentUser() OR reporter = currentUser())"
    )

    @field_validator("base_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")


def _expand(p) -> Path:
    return Path(os.path.expanduser(str(p))).resolve()


class Config(BaseModel):
    vault: Path = Path("~/work-vault")
    notes_inbox: Path | None = None
    lmstudio: LMStudioConfig = LMStudioConfig()
    jira: JiraConfig = JiraConfig()
    codex: CodexConfig = CodexConfig()
    slack_channels: list[str] = []
    gitlab_url: str = ""

    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data: dict) -> dict:
        """config.yaml nests these; the code only ever wants the one value."""
        data = dict(data or {})
        data.setdefault(
            "slack_channels", (data.get("slack") or {}).get("channels") or []
        )
        data.setdefault("gitlab_url", (data.get("gitlab") or {}).get("base_url") or "")
        return data

    @field_validator("gitlab_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @model_validator(mode="after")
    def _resolve_paths(self):
        self.vault = _expand(self.vault)
        self.notes_inbox = (
            _expand(self.notes_inbox)
            if self.notes_inbox
            else self.vault / "notes-inbox"
        )
        return self


def find_config_path() -> Path:
    env = os.environ.get("WORK_HELPER_CONFIG")
    if env:
        return _expand(env)
    for candidate in (
        Path("config.yaml"),
        Path.home() / ".config/work-helper/config.yaml",
    ):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "No config.yaml found. Copy config.example.yaml to config.yaml, "
        "or set WORK_HELPER_CONFIG."
    )


def load_config(path: Path = None) -> Config:
    if path is None:
        path = find_config_path()
    return Config(**(yaml.safe_load(path.read_text()) or {}))


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value
