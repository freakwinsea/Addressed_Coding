//! Area 500 — the only block that touches the filesystem.
//!
//! The CSV state machine below is a line-for-line counterpart of the one in
//! `phonebook_rt/io_.py`. Delegating to a crate would have been shorter and
//! would have made the two backends agree only by luck; writing the same
//! explicit machine twice is what makes them agree by construction.

use std::collections::BTreeMap;

const QUOTE_NEEDED: [char; 4] = [',', '"', '\r', '\n'];

/// 500-0000001 READ_TEXT_FILE — UTF-8 strict, no newline translation.
pub fn read_text_file(path: &str) -> String {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(err) => match err.kind() {
            std::io::ErrorKind::NotFound => crate::fault("file_not_found", path),
            std::io::ErrorKind::PermissionDenied => crate::fault("permission_denied", path),
            _ => crate::fault("file_not_found", path),
        },
    };
    match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(_) => crate::fault("decode_error", &format!("{path} is not valid UTF-8")),
    }
}

/// 500-0000002 WRITE_TEXT_FILE — truncating, byte-exact, no newline translation.
pub fn write_text_file(path: &str, content: &str) {
    match std::fs::write(path, content.as_bytes()) {
        Ok(()) => {}
        Err(err) => match err.kind() {
            std::io::ErrorKind::PermissionDenied => crate::fault("permission_denied", path),
            _ => crate::fault("path_not_writable", path),
        },
    }
}

/// 500-0000003 READ_CSV — header row, everything stays text.
pub fn read_csv(path: &str) -> Vec<BTreeMap<String, String>> {
    let text = read_text_file(path);
    let records = parse_csv(&text, path);
    let mut rows: Vec<BTreeMap<String, String>> = Vec::new();
    let header = match records.first() {
        Some(header) => header.clone(),
        None => return rows,
    };
    for (offset, cells) in records.iter().skip(1).enumerate() {
        if cells.len() > header.len() {
            crate::fault(
                "malformed_csv",
                &format!(
                    "{}:{} has {} cells but the header has {}",
                    path,
                    offset + 2,
                    cells.len(),
                    header.len()
                ),
            );
        }
        let mut row: BTreeMap<String, String> = BTreeMap::new();
        for (index, name) in header.iter().enumerate() {
            let value = cells.get(index).cloned().unwrap_or_default();
            row.insert(name.clone(), value);
        }
        rows.push(row);
    }
    rows
}

/// 500-0000004 WRITE_CSV — minimal quoting, LF line endings.
pub fn write_csv(path: &str, rows: &[BTreeMap<String, String>], columns: &[String]) {
    let mut out = String::new();
    out.push_str(&csv_line(columns));
    out.push('\n');
    for row in rows {
        let cells: Vec<String> = columns
            .iter()
            .map(|column| row.get(column).cloned().unwrap_or_default())
            .collect();
        out.push_str(&csv_line(&cells));
        out.push('\n');
    }
    write_text_file(path, &out);
}

// -------------------------------------------------------------------------
// the shared CSV state machine
// -------------------------------------------------------------------------

fn parse_csv(text: &str, path: &str) -> Vec<Vec<String>> {
    let chars: Vec<char> = text.chars().collect();
    let mut records: Vec<Vec<String>> = Vec::new();
    let mut row: Vec<String> = Vec::new();
    let mut field = String::new();
    let mut in_quotes = false;
    let mut i = 0usize;

    while i < chars.len() {
        let ch = chars[i];
        if in_quotes {
            if ch == '"' {
                if i + 1 < chars.len() && chars[i + 1] == '"' {
                    field.push('"');
                    i += 2;
                    continue;
                }
                in_quotes = false;
                i += 1;
                continue;
            }
            field.push(ch);
            i += 1;
            continue;
        }

        if ch == '"' && field.is_empty() {
            in_quotes = true;
            i += 1;
            continue;
        }
        if ch == ',' {
            row.push(std::mem::take(&mut field));
            i += 1;
            continue;
        }
        if ch == '\n' || ch == '\r' {
            row.push(std::mem::take(&mut field));
            if !is_blank_record(&row) {
                records.push(std::mem::take(&mut row));
            } else {
                row.clear();
            }
            i += if ch == '\r' && i + 1 < chars.len() && chars[i + 1] == '\n' {
                2
            } else {
                1
            };
            continue;
        }
        field.push(ch);
        i += 1;
    }

    if in_quotes {
        crate::fault(
            "malformed_csv",
            &format!("{path} ends inside a quoted field"),
        );
    }
    if !field.is_empty() || !row.is_empty() {
        row.push(field);
        if !is_blank_record(&row) {
            records.push(row);
        }
    }
    records
}

fn is_blank_record(row: &[String]) -> bool {
    row.len() == 1 && row[0].is_empty()
}

fn csv_line(cells: &[String]) -> String {
    let rendered: Vec<String> = cells.iter().map(|cell| csv_cell(cell)).collect();
    rendered.join(",")
}

fn csv_cell(cell: &str) -> String {
    if cell.chars().any(|c| QUOTE_NEEDED.contains(&c)) {
        format!("\"{}\"", cell.replace('"', "\"\""))
    } else {
        cell.to_string()
    }
}
