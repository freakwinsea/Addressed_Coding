"""Extract readable markdown transcripts from the saved ideation sessions.

The two HTML files in docs/origins/ are browser "save page" captures of the
conversations this project was designed in. They are kept for provenance, but
they are unreadable as HTML in a repo, so this script renders the prose to
markdown next to them.

Usage:
    python scripts/extract_origins.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ORIGINS = Path(__file__).resolve().parent.parent / "docs" / "origins"

SESSIONS = [
    ("session-01-chatgpt.html", "session-01-chatgpt.md", "Session 01 — ChatGPT"),
    ("session-02-gemini.html", "session-02-gemini.md", "Session 02 — Gemini"),
]

# Saved-page chrome that appears before the conversation itself starts.
CHROME = re.compile(
    r"^(skip to content|new chat|search|pinned|recents|chat history|library|"
    r"scheduled|plugins|more|projects|chats|show more|show less|expand menu|"
    r"copy prompt|copy response|good response|bad response|share & export|"
    r"google apps|google account|junk mail|ctrl|shift|o|plus|work|"
    r"gemini|pro|notebooks|new notebook|all notebooks|dictate.*|settings|"
    r"switch to spark.*|expand text|edit prompt|redo|-->)$",
    re.IGNORECASE,
)


def strip_tags(raw: str) -> list[str]:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", raw))
    return [line.strip() for line in text.split("\n") if line.strip()]


def render(lines: list[str], title: str) -> str:
    out = [f"# {title}", ""]
    out.append(
        "> Verbatim transcript recovered from the saved page. Formatting is "
        "approximate; the HTML capture is alongside this file."
    )
    out.append("")
    for line in lines:
        if CHROME.match(line):
            continue
        # Turn the platform's speaker labels into headings.
        if line in ("You said", "You said:"):
            out += ["", "## You", ""]
        elif line in ("ChatGPT said", "ChatGPT said:", "Gemini said", "Gemini said:"):
            speaker = "ChatGPT" if line.startswith("ChatGPT") else "Gemini"
            out += ["", f"## {speaker}", ""]
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    for src_name, dst_name, title in SESSIONS:
        src = ORIGINS / src_name
        if not src.exists():
            print(f"skip: {src} not found")
            continue
        lines = strip_tags(src.read_text(encoding="utf-8", errors="ignore"))
        (ORIGINS / dst_name).write_text(render(lines, title), encoding="utf-8")
        print(f"wrote docs/origins/{dst_name} ({len(lines)} source lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
