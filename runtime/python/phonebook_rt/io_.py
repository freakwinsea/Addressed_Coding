"""Area 500 — the only block that touches the filesystem.

The CSV reader and writer are hand-written rather than delegated to the `csv`
module. That is deliberate: the Rust runtime implements the same explicit state
machine, so the two backends agree by construction instead of by hoping two
third-party libraries interpret the same edge cases the same way.
"""

from __future__ import annotations

from .faults import PhonebookFault

QUOTE_NEEDED = {",", '"', "\r", "\n"}


def read_text_file(path: str) -> str:
    """500-0000001 READ_TEXT_FILE — UTF-8 strict, no newline translation."""
    try:
        with open(path, "r", encoding="utf-8", errors="strict", newline="") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise PhonebookFault("file_not_found", path) from exc
    except IsADirectoryError as exc:
        raise PhonebookFault("file_not_found", f"{path} is a directory") from exc
    except PermissionError as exc:
        raise PhonebookFault("permission_denied", path) from exc
    except UnicodeDecodeError as exc:
        raise PhonebookFault("decode_error", f"{path} is not valid UTF-8") from exc


def write_text_file(path: str, content: str) -> None:
    """500-0000002 WRITE_TEXT_FILE — truncating, byte-exact, no newline translation."""
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except PermissionError as exc:
        raise PhonebookFault("permission_denied", path) from exc
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError) as exc:
        raise PhonebookFault("path_not_writable", path) from exc


def read_csv(path: str) -> list:
    """500-0000003 READ_CSV — header row, everything stays text."""
    text = read_text_file(path)
    records = _parse_csv(text)
    if not records:
        return []
    header = records[0]
    rows: list = []
    for line_no, cells in enumerate(records[1:], start=2):
        if len(cells) > len(header):
            raise PhonebookFault(
                "malformed_csv",
                f"{path}:{line_no} has {len(cells)} cells but the header has {len(header)}",
            )
        padded = list(cells) + [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, padded)))
    return rows


def write_csv(path: str, rows: list, columns: list) -> None:
    """500-0000004 WRITE_CSV — minimal quoting, LF line endings."""
    lines = [_csv_line(columns)]
    for row in rows:
        lines.append(_csv_line([row.get(column, "") for column in columns]))
    write_text_file(path, "".join(line + "\n" for line in lines))


# --------------------------------------------------------------------------
# the shared CSV state machine
# --------------------------------------------------------------------------


def _parse_csv(text: str) -> list:
    records: list = []
    row: list = []
    field: list = []
    in_quotes = False
    i = 0
    size = len(text)

    while i < size:
        char = text[i]
        if in_quotes:
            if char == '"':
                if i + 1 < size and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field.append(char)
            i += 1
            continue

        if char == '"' and not field:
            in_quotes = True
            i += 1
            continue
        if char == ",":
            row.append("".join(field))
            field = []
            i += 1
            continue
        if char in ("\n", "\r"):
            row.append("".join(field))
            field = []
            if row != [""]:  # a blank line is not a record
                records.append(row)
            row = []
            i += 2 if char == "\r" and i + 1 < size and text[i + 1] == "\n" else 1
            continue
        field.append(char)
        i += 1

    if in_quotes:
        raise PhonebookFault("malformed_csv", "file ends inside a quoted field")
    if field or row:
        row.append("".join(field))
        if row != [""]:
            records.append(row)
    return records


def _csv_line(cells: list) -> str:
    return ",".join(_csv_cell(cell) for cell in cells)


def _csv_cell(cell: str) -> str:
    if any(char in QUOTE_NEEDED for char in cell):
        return '"' + cell.replace('"', '""') + '"'
    return cell
