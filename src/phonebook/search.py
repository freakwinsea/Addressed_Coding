"""Directory assistance: find an address from a description of what you want.

The DNS problem is the first objection anyone raises about numeric addresses —
nobody can remember them. The answer is that you are not supposed to: you look
them up. This module and `dial show` are that lookup, and they exist before any
program can run for exactly that reason.

Pure standard library on purpose. A dependency-free TF-IDF over a 54-entry
corpus is both sufficient and auditable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .registry import Entry, Registry
from .types import Type, parse_type

_WORD = re.compile(r"[a-z0-9]+")

_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "be", "it", "its", "that", "this", "with", "from", "how", "i", "we", "you",
    "want", "need", "get", "make", "do", "does", "my", "me",
}


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


@dataclass
class Hit:
    entry: Entry
    score: float
    why: str


class Index:
    """A tiny TF-IDF index over the registry's search surface."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.docs: dict[str, Counter[str]] = {}
        for entry in registry:
            self.docs[entry.address] = Counter(self._surface(entry))

        n = max(len(self.docs), 1)
        appearances: Counter[str] = Counter()
        for doc in self.docs.values():
            appearances.update(doc.keys())
        self.idf = {term: math.log(1 + n / (1 + count)) for term, count in appearances.items()}

    @staticmethod
    def _surface(entry: Entry) -> list[str]:
        terms: list[str] = []
        # The name matters most, so it is weighted by repetition rather than by
        # a separate coefficient — keeps the scoring one formula.
        terms += tokenize(entry.name.replace("_", " ")) * 3
        terms += tokenize(entry.summary) * 2
        for keyword in entry.keywords:
            terms += tokenize(keyword) * 3
        terms += tokenize(entry.description)
        return terms

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        wanted = tokenize(query)
        if not wanted:
            return []
        hits: list[Hit] = []
        for address, doc in self.docs.items():
            total = sum(doc.values()) or 1
            score = 0.0
            matched: list[str] = []
            for term in set(wanted):
                if term in doc:
                    score += (doc[term] / total) * self.idf.get(term, 0.0)
                    matched.append(term)
            if score > 0:
                entry = self.registry.require(address)
                hits.append(Hit(entry, score, ", ".join(sorted(matched))))
        hits.sort(key=lambda h: (-h.score, h.entry.address))
        return hits[:limit]


def successors(registry: Registry, produces: str, limit: int = 10) -> list[Entry]:
    """Addresses that accept a value of this type as their first input.

    The "who can I call next" feature: given what you are holding, show what can
    be dialed with it.
    """
    from .types import Substitution, unify
    from .errors import CheckError

    have = parse_type(produces)
    out: list[Entry] = []
    for entry in registry:
        inputs = entry.contract.inputs
        if not inputs:
            continue
        subs: Substitution = {}
        try:
            unify(inputs[0].type, have, subs)
        except CheckError:
            continue
        out.append(entry)
    return out[:limit]


def describe_signature(entry: Entry) -> str:
    """Render a contract the way a phonebook listing would show it."""
    parts = []
    for param in entry.contract.inputs:
        suffix = "..." if param.variadic else ""
        parts.append(f"{param.name}: {param.type}{suffix}")
    output = entry.contract.output.type
    shown = "" if output.name == "unit" else f" -> {output}"
    return f"{entry.name}({', '.join(parts)}){shown}"


def resolve_type(text: str) -> Type:
    return parse_type(text)
