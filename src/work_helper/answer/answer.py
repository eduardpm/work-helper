from __future__ import annotations

from ..config import Config
from ..indexer.llm import LLM
from .search import top_files

TERMS_PROMPT = """You build a search plan for a grep over the user's work
notes. The user rarely uses the same words as the notes, so do not just copy
words out of the question. Split your plan in two:

"terms" - the concrete things actually named in the question: tool names,
ticket keys, people, channels, repos, services. 2-5 of them.

"related" - the words the notes are likely to use for the same idea in a
full-stack software project: synonyms, the implementation-level name, the
layer above and below, and common abbreviations. 3-8 of them. For a question
about a "job" that would be worker, queue, cron, scheduler, task, celery.
For "login": auth, session, token, oauth, sso.

Rules:
- Search is a case-insensitive substring match, so prefer short stems
  ("deploy" also finds deployment, deployed) and use no regex characters.
- One or two words per entry.
- Skip generic filler: issue, thing, update, status, work, problem.

Respond with ONE JSON object and nothing else:
{"terms": ["term1"], "related": ["term2"]}
"""

ANSWER_PROMPT = """You answer questions about the user's own work, using only
the notes provided. The notes contain links (Slack, Jira, GitLab).
- Answer directly and briefly.
- Quote open TODO items exactly as written when the question asks what is left.
- Include the relevant links so the user can jump to the source.
- If the notes do not contain the answer, say so. Do not invent anything.
"""

MAX_CONTEXT_CHARS = 24000


def _clean(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def ask(cfg: Config, question: str) -> str:
    llm = LLM(cfg.lmstudio)

    data = llm.json_chat(TERMS_PROMPT, question)
    terms = _clean(data.get("terms"))
    related = [t for t in _clean(data.get("related")) if t.lower() not in
               {t.lower() for t in terms}]
    if not terms and not related:
        terms = [question]
    if terms:
        print("searching for: " + ", ".join(terms))
    if related:
        print("also trying: " + ", ".join(related))

    files = top_files(cfg.vault, terms, related)
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
