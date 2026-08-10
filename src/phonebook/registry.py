"""Loading, validating, and freezing the phonebook.

The registry is data, not code: `phonebook/areas/*.json`. This module turns it
into typed objects, checks it for the invariants that make the whole system
trustworthy, and maintains the immutability ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .errors import RegistryError
from .types import Type, parse_type

ADDRESS_RE = re.compile(r"^([0-9]{3})-([0-9]{7})$")

LOCAL_AREA = "000"
QUARANTINE_AREA = "999"
RESERVED_AREAS = {"700", "800", "900", QUARANTINE_AREA}

CAPABILITY_OF_EFFECT = {
    "stdout": "console",
    "filesystem-read": "filesystem-read",
    "filesystem-write": "filesystem-write",
    "process": "process",
    "network": "network",
}


def area_of(address: str) -> str:
    match = ADDRESS_RE.match(address)
    if not match:
        raise RegistryError(f"malformed address {address!r}, expected AAA-NNNNNNN")
    return match.group(1)


def is_local(address: str) -> bool:
    return area_of(address) == LOCAL_AREA


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    name: str
    type: Type
    description: str = ""
    variadic: bool = False


@dataclass(frozen=True)
class Contract:
    version: int
    inputs: tuple[Param, ...]
    output: Param
    constraints: dict[str, str]
    effects: tuple[str, ...]
    errors: tuple[str, ...]
    purity: str
    determinism: str
    notes: tuple[str, ...] = ()

    @property
    def variadic(self) -> bool:
        return bool(self.inputs) and self.inputs[-1].variadic

    @property
    def min_arity(self) -> int:
        return len(self.inputs) - 1 if self.variadic else len(self.inputs)

    @property
    def returns_value(self) -> bool:
        return self.output.type.name != "unit"


@dataclass(frozen=True)
class Entry:
    address: str
    name: str
    summary: str
    description: str
    keywords: tuple[str, ...]
    contract: Contract
    examples: tuple[str, ...]
    conformance: tuple[dict[str, Any], ...]
    status: str
    since: str
    area: str
    superseded_by: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def label(self) -> str:
        return f"{self.address} {self.name}"


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _param(raw: dict[str, Any], where: str) -> Param:
    try:
        return Param(
            name=raw["name"],
            type=parse_type(raw["type"]),
            description=raw.get("description", ""),
            variadic=bool(raw.get("variadic", False)),
        )
    except KeyError as exc:
        raise RegistryError(f"{where}: parameter is missing {exc}") from exc
    except Exception as exc:
        raise RegistryError(f"{where}: {exc}") from exc


def _entry(raw: dict[str, Any], area: str, source: Path) -> Entry:
    where = f"{source.name}:{raw.get('address', '<no address>')}"
    for required in ("address", "name", "summary", "keywords", "contract", "status", "since"):
        if required not in raw:
            raise RegistryError(f"{where}: missing required field {required!r}")

    address = raw["address"]
    if not ADDRESS_RE.match(address):
        raise RegistryError(f"{where}: malformed address, expected AAA-NNNNNNN")
    if area_of(address) != area:
        raise RegistryError(f"{where}: address does not belong to area {area}")
    if not re.match(r"^[A-Z][A-Z0-9_]*$", raw["name"]):
        raise RegistryError(f"{where}: name must be SCREAMING_SNAKE_CASE")

    c = raw["contract"]
    for required in ("version", "inputs", "output", "effects", "errors", "purity", "determinism"):
        if required not in c:
            raise RegistryError(f"{where}: contract is missing {required!r}")

    inputs = tuple(_param(i, where) for i in c["inputs"])
    for param in inputs[:-1]:
        if param.variadic:
            raise RegistryError(f"{where}: only the final input may be variadic")

    contract = Contract(
        version=int(c["version"]),
        inputs=inputs,
        output=_param(c["output"], where),
        constraints=dict(c.get("constraints", {})),
        effects=tuple(c["effects"]),
        errors=tuple(c["errors"]),
        purity=c["purity"],
        determinism=c["determinism"],
        notes=tuple(c.get("notes", ())),
    )

    declares_effects = bool(contract.effects)
    if declares_effects != (contract.purity == "effectful"):
        raise RegistryError(
            f"{where}: purity {contract.purity!r} disagrees with effects {list(contract.effects)}"
        )

    return Entry(
        address=address,
        name=raw["name"],
        summary=raw["summary"],
        description=raw.get("description", ""),
        keywords=tuple(raw["keywords"]),
        contract=contract,
        examples=tuple(raw.get("examples", ())),
        conformance=tuple(raw.get("conformance", ())),
        status=raw["status"],
        since=raw["since"],
        area=area,
        superseded_by=raw.get("superseded_by"),
        raw=raw,
    )


class Registry:
    """The loaded phonebook, indexed by address and by name."""

    def __init__(self, entries: dict[str, Entry], root: Path):
        self.entries = entries
        self.root = root
        self.by_name = {e.name: e for e in entries.values()}

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, root: Path | str | None = None) -> "Registry":
        root = Path(root) if root else default_root()
        areas_dir = root / "areas"
        if not areas_dir.is_dir():
            raise RegistryError(f"no phonebook at {areas_dir}")

        entries: dict[str, Entry] = {}
        names: dict[str, str] = {}
        for path in sorted(areas_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            area = data["area"]
            if area in RESERVED_AREAS or area == LOCAL_AREA:
                raise RegistryError(f"{path.name}: area {area} is reserved and cannot hold entries")
            for raw in data["entries"]:
                entry = _entry(raw, area, path)
                if entry.address in entries:
                    raise RegistryError(f"duplicate address {entry.address}")
                if entry.name in names:
                    raise RegistryError(
                        f"duplicate name {entry.name}: {names[entry.name]} and {entry.address}"
                    )
                entries[entry.address] = entry
                names[entry.name] = entry.address
        return cls(entries, root)

    # -- lookup ----------------------------------------------------------

    def __contains__(self, address: str) -> bool:
        return address in self.entries

    def __iter__(self) -> Iterator[Entry]:
        return iter(sorted(self.entries.values(), key=lambda e: e.address))

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, address: str) -> Entry | None:
        return self.entries.get(address)

    def require(self, address: str) -> Entry:
        entry = self.entries.get(address)
        if entry is None:
            raise RegistryError(f"no such address: {address}")
        return entry

    def areas(self) -> dict[str, list[Entry]]:
        grouped: dict[str, list[Entry]] = {}
        for entry in self:
            grouped.setdefault(entry.area, []).append(entry)
        return grouped

    # -- immutability ledger ---------------------------------------------

    @property
    def frozen_path(self) -> Path:
        return self.root / "frozen.json"

    def load_frozen(self) -> dict[str, str]:
        if not self.frozen_path.exists():
            return {}
        return json.loads(self.frozen_path.read_text(encoding="utf-8"))["contracts"]

    def verify_frozen(self) -> list[str]:
        """Return a list of immutability violations. Empty means the ledger holds.

        This is the mechanical form of the rule the whole design rests on: an
        issued address may never silently acquire a different meaning.
        """
        ledger = self.load_frozen()
        problems: list[str] = []
        for entry in self:
            key = f"{entry.address}@contract:{entry.contract.version}"
            digest = contract_hash(entry)
            recorded = ledger.get(key)
            if recorded is None:
                problems.append(
                    f"{key} ({entry.name}) is not in the ledger — run `dial registry freeze`"
                )
            elif recorded != digest:
                problems.append(
                    f"{key} ({entry.name}) CHANGED without a version bump\n"
                    f"    frozen:  {recorded}\n"
                    f"    current: {digest}"
                )
        for key in ledger:
            address = key.split("@", 1)[0]
            if address not in self.entries:
                problems.append(f"{key} was issued but has vanished from the registry")
        return problems

    def freeze(self) -> tuple[int, int]:
        """Record hashes for any newly issued contracts. Never rewrites an old one.

        Returns (added, unchanged). Changed contracts are refused: bumping the
        version is the only sanctioned way to alter a promise.
        """
        ledger = self.load_frozen()
        added = 0
        unchanged = 0
        conflicts: list[str] = []
        for entry in self:
            key = f"{entry.address}@contract:{entry.contract.version}"
            digest = contract_hash(entry)
            if key not in ledger:
                ledger[key] = digest
                added += 1
            elif ledger[key] != digest:
                conflicts.append(f"{key} ({entry.name})")
            else:
                unchanged += 1
        if conflicts:
            raise RegistryError(
                "refusing to freeze: these contracts changed in place.\n  "
                + "\n  ".join(conflicts)
                + "\n\nIncrement contract.version (or issue a new address) instead."
            )
        payload = {
            "_comment": (
                "SHA-256 over each issued contract. An issued address may never "
                "silently acquire a different meaning; this file is how that rule "
                "is enforced rather than merely promised. Do not hand-edit."
            ),
            "contracts": dict(sorted(ledger.items())),
        }
        self.frozen_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return added, unchanged


def contract_hash(entry: Entry) -> str:
    """Stable digest of everything an address promises.

    Covers the address, the human-facing name (audit reports quote it, so it is
    load-bearing), and the full contract. Deliberately excludes examples,
    keywords, and prose description: those may improve freely.
    """
    canonical = {
        "address": entry.address,
        "name": entry.name,
        "contract": entry.raw["contract"],
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def default_root() -> Path:
    """Locate the bundled `phonebook/` directory by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "phonebook" / "areas"
        if candidate.is_dir():
            return parent / "phonebook"
    raise RegistryError("could not locate the phonebook/ directory")


def lint(registry: Registry) -> list[str]:
    """Domain checks beyond schema validity. Returns a list of complaints."""
    problems: list[str] = []
    for entry in registry:
        where = entry.label

        if len(entry.keywords) < 3:
            problems.append(f"{where}: needs at least 3 keywords to be findable via dial search")
        if entry.summary.endswith("."):
            problems.append(f"{where}: summary should not end with a period")
        if entry.status == "withdrawn" and not entry.superseded_by:
            problems.append(f"{where}: withdrawn entries must name a superseded_by address")

        seen: set[str] = set()
        for param in entry.contract.inputs:
            if param.name in seen:
                problems.append(f"{where}: duplicate input name {param.name!r}")
            seen.add(param.name)

        # Every generic in the output must be reachable from the inputs,
        # otherwise the checker can never resolve it.
        input_vars = set()
        for param in entry.contract.inputs:
            input_vars |= _vars(param.type)
        for var in _vars(entry.contract.output.type) - input_vars:
            problems.append(f"{where}: output variable {var} never appears in an input")

        for var in entry.contract.constraints:
            if var not in input_vars | _vars(entry.contract.output.type):
                problems.append(f"{where}: constraint on unknown variable {var}")

        # stdout belongs to core; everything else that touches the outside
        # world is confined to 500 so the audit capability report stays honest.
        outside = set(entry.contract.effects) - {"stdout"}
        if outside and entry.area != "500":
            problems.append(f"{where}: effects {sorted(outside)} are only allowed in area 500")

        for case in entry.conformance:
            if not case.get("id", "").startswith(entry.name.lower().split("_")[0]):
                continue  # naming is a convention, not a rule

    return problems


def _vars(t: Type) -> set[str]:
    if t.is_var:
        return {t.name}
    out: set[str] = set()
    for arg in t.args:
        out |= _vars(arg)
    return out
