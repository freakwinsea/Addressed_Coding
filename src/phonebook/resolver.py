"""Turning an address plus a version policy into a concrete implementation.

This is the switchboard. It is the only place that knows a backend exists, and
it is what the `@impl:` / `@contract:` / `@latest` selectors actually control.
Swapping which code runs behind an address happens here and nowhere else — the
program does not change a digit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import CheckError
from .nodes import Selector
from .registry import Registry


@dataclass(frozen=True)
class Implementation:
    address: str
    impl: int
    status: str
    since: str
    #: None when a target keeps the contract entirely with an inline template
    #: and has no callable function behind it (Rust's LIST, for example).
    runtime: str | None
    inline: str | None
    notes: str = ""


class Backend:
    """A loaded mapping table: how one target language keeps the promises."""

    def __init__(self, data: dict, path: Path):
        self.target: str = data["target"]
        self.runtime_package: str = data.get("runtime_package", "")
        self.type_map: dict[str, str] = data.get("type_map", {})
        self.path = path
        self.mappings: dict[str, dict] = data["mappings"]

    @classmethod
    def load(cls, target: str, root: Path | str | None = None) -> "Backend":
        root = Path(root) if root else default_backends_root()
        path = root / target / "mappings.json"
        if not path.exists():
            raise CheckError(f"no backend mapping table at {path}")
        return cls(json.loads(path.read_text(encoding="utf-8")), path)

    def implementations(self, address: str) -> list[Implementation]:
        entry = self.mappings.get(address)
        if entry is None:
            return []
        return [
            Implementation(
                address=address,
                impl=int(i["impl"]),
                status=i.get("status", "active"),
                since=i.get("since", ""),
                runtime=i.get("runtime"),
                inline=i.get("inline"),
                notes=i.get("notes", ""),
            )
            for i in entry["implementations"]
        ]

    def resolve(self, address: str, selector: Selector) -> Implementation:
        """Pick the implementation this call site is entitled to."""
        candidates = self.implementations(address)
        if not candidates:
            raise CheckError(
                f"{self.target} has no implementation of {address}",
                hint=f"add it to {self.path.as_posix()}",
            )
        if selector.kind == "impl":
            for candidate in candidates:
                if candidate.impl == selector.value:
                    return candidate
            available = ", ".join(str(c.impl) for c in candidates)
            raise CheckError(
                f"{address}@impl:{selector.value} is not available in {self.target}",
                hint=f"implementations present: {available}",
            )
        active = [c for c in candidates if c.status == "active"]
        if not active:
            raise CheckError(f"every {self.target} implementation of {address} is retired")
        return max(active, key=lambda c: c.impl)

    def audit_against(self, registry: Registry) -> list[str]:
        """Report addresses the registry issues but this backend cannot keep."""
        problems: list[str] = []
        for entry in registry:
            if entry.status == "withdrawn":
                continue
            mapping = self.mappings.get(entry.address)
            if mapping is None:
                problems.append(f"{entry.label}: no {self.target} implementation")
                continue
            if mapping.get("contract") != entry.contract.version:
                problems.append(
                    f"{entry.label}: {self.target} mapping targets contract "
                    f"v{mapping.get('contract')}, registry is at v{entry.contract.version}"
                )
        for address in self.mappings:
            if address not in registry:
                problems.append(f"{address}: {self.target} maps an address that does not exist")
        return problems


def default_backends_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backends").is_dir():
            return parent / "backends"
    raise CheckError("could not locate the backends/ directory")


def selector_for(address: str, call_selector: Selector, pins: dict[str, Selector]) -> Selector:
    """A call's own selector wins; otherwise the file's `pin` directive applies."""
    if call_selector.kind != "latest":
        return call_selector
    return pins.get(address, call_selector)
