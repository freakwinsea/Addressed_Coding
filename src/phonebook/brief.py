"""The agent-facing address table, generated from the registry.

Handing a model a hand-maintained list of addresses would reproduce exactly the
rot this project exists to prevent: the documentation and the contracts drifting
apart until the documentation lies. So the table is generated, committed, and a
test fails when it goes stale.

The contract notes are included on purpose. They are the behavior nobody can
guess from a signature — that DIV truncates toward zero, that ENTRIES sorts by
key — and they are precisely where a model writing from intuition goes wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

from .registry import Registry
from .search import describe_signature

BEGIN = "<!-- BEGIN GENERATED ADDRESS TABLE -->"
END = "<!-- END GENERATED ADDRESS TABLE -->"

AREA_TITLES = {
    "100": "Core",
    "200": "Text",
    "300": "Collections",
    "400": "Numbers",
    "500": "Input / output — the only addresses with effects",
    "600": "Logic and comparison",
}


def cheatsheet(registry: Registry, notes: bool = True) -> str:
    """The complete address table, grouped by area."""
    out: list[str] = []
    for area, entries in sorted(registry.areas().items()):
        out.append("")
        out.append(f"### {area} — {AREA_TITLES.get(area, '')}".rstrip())
        out.append("")
        out.append("```")
        for entry in entries:
            effects = f"  [{', '.join(entry.contract.effects)}]" if entry.contract.effects else ""
            out.append(f"{entry.address}  {describe_signature(entry)}{effects}")
            out.append(f"{'':<13}{entry.summary}")
            if notes:
                for note in entry.contract.notes:
                    for index, line in enumerate(_wrap(note, 62)):
                        out.append(f"{'':<13}{'! ' if index == 0 else '  '}{line}")
            if entry.contract.errors:
                out.append(f"{'':<13}errors: {', '.join(entry.contract.errors)}")
            out.append("")
        if out[-1] == "":
            out.pop()
        out.append("```")
    return "\n".join(out).strip() + "\n"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def guide_path(registry: Registry) -> Path:
    return registry.root.parent / "docs" / "WRITING-PHONE.md"


#: Section 5 is eight worked patterns — filter a list, fold a total, rank a
#: tally. Excellent documentation for a real user, and a near-complete solution
#: key for the study's task set, which was written in the same sitting. A run
#: with it in context measures recall of an example the experimenter supplied,
#: not use of the language. `--minimal` withholds it; everything else stays,
#: because syntax, rules, constraints, and the address table are the language
#: itself rather than the method.
WORKED_PATTERNS = re.compile(r"\n## 5\. Patterns you will need\n.*?(?=\n## 6\.)", re.DOTALL)

WITHHELD_NOTICE = """## 5. Patterns you will need

*Withheld. The worked patterns that normally sit here solve most of the study's
tasks outright, so they are removed when this guide is used as a measuring
instrument. Everything else is intact: the rules above, and below them the full
address table with the semantics each contract pins.*"""


def render_guide(registry: Registry, minimal: bool = False) -> str:
    """The writing guide with its generated table section refreshed.

    `minimal` produces the study instrument — see WORKED_PATTERNS.
    """
    path = guide_path(registry)
    source = path.read_text(encoding="utf-8")
    table = cheatsheet(registry)
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(source):
        raise ValueError(f"{path.name} has no generated-table markers")
    rendered = pattern.sub(f"{BEGIN}\n\n{table}\n{END}", source)
    if minimal:
        rendered, count = WORKED_PATTERNS.subn("\n" + WITHHELD_NOTICE + "\n", rendered)
        if count != 1:
            raise ValueError("could not locate the worked-patterns section to withhold")
    return rendered


def guide_is_current(registry: Registry) -> bool:
    return guide_path(registry).read_text(encoding="utf-8") == render_guide(registry)
