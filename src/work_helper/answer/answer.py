from __future__ import annotations

from ..config import Config
from ..indexer.llm import LLM
from .search import top_files

TERMS_PROMPT = """list 5-10 grep terms for searching the user's work notes.

Include the concrete things the question names (tool names, ticket keys,
people, channels) AND the words the notes probably use for the same idea in a
full-stack project: synonyms, the implementation-level name, common
abbreviations. A question about a "job" should also search worker, queue,
cron, scheduler, task. A question about "login": auth, session, token, sso.

Search is case-insensitive substring, so use short stems ("deploy" finds
deployment) and no regex characters. One or two words each. Skip filler like
issue, thing, update, status.

Respond with ONE JSON object and nothing else:
{"terms": ["term1", "term2"]}
"""

ANSWER_PROMPT = """You answer questions about the user's own work, using only
the notes provided. The notes contain links (Slack, Jira, GitLab).
- Answer directly and briefly.
- Quote open TODO items exactly as written when the question asks what is left.
- Include the relevant links so the user can jump to the source.
- If the notes do not contain the answer, say so. Do not invent anything.
"""

MAX_CONTEXT_CHARS = 24000


def ask(cfg: Config, question: str) -> str:
    llm = LLM(cfg.lmstudio)

    data = llm.json_chat(TERMS_PROMPT, question)
    terms = [str(t) for t in data.get("terms", []) if str(t).strip()]
    if not terms:
        terms = [question]
    print("searching for: " + ", ".join(terms))

    files = top_files(cfg.vault, terms)
    if not files:
        return "No notes matched. Try `work-helper search <term>` to check the vault."

    chunks = []
    used = 0
    for path in files:
        text = path.read_text()
        if used + len(text) > MAX_CONTEXT_CHARS:
            text = text[: MAX_CONTEXT_CHARS - used]
        chunks.append(f"=== {path.name} ===\n{text}")
        used += len(text)
        if used >= MAX_CONTEXT_CHARS:
            break
    print("reading: " + ", ".join(p.name for p in files))

    user = "NOTES:\n\n{}\n\nQUESTION: {}".format("\n\n".join(chunks), question)
    return llm.chat(ANSWER_PROMPT, user)
