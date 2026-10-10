"""Parse 3GPP .docx specs into clauses.

Walks each document in order. Headings start a new clause, everything until the next
heading becomes the content of that clause. The content is kept as an ordered list of
blocks, so later steps can render it the way they need it (plain text for search and
diff, formatted for prompts and the UI):

    {"type": "paragraph", "style": "B1", "text": "-  the UE ..."}
    {"type": "table", "table_id": "5.2/1", "caption": "Table 5.2-1: ...",
     "header_rows": 1, "rows": [["NR operating band", ...], ["n1", ...]]}

Output per document:

    data/parsed/<spec>_<release>.clauses.jsonl
    data/parsed/<spec>_<release>_report.md
"""

import json
import re
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path

from docx import Document
from docx.table import Table, _Cell
from docx.text.hyperlink import Hyperlink

from specdelta import config

# Word's "Heading 1".."Heading 9", plus the 3GPP style "H6" used for level 6 in some specs
HEADING_STYLE = re.compile(r"^(?:Heading |H)(\d)$")
# A clause number is the first token of a heading and contains at least one digit:
# "4", "16.4.2", "5.2A.1", "A.1". Letter-only tokens ("A", "Foreword") are not clause numbers.
CLAUSE_ID = re.compile(r"^(?=\S*\d)[0-9A-Z]+(\.[0-9A-Za-z]+)*$")
# Annex headings look like "Annex A (normative):\nMeasurement channels"
ANNEX_HEADING = re.compile(r"^Annex ([A-Z]+)\b[^:]*:\s*(.*)$", re.DOTALL)
FILE_NAME = re.compile(r"^(\d{5}(?:-\d+)?)-([a-z])([0-9a-z])([0-9a-z])$")

REFERENCED_SPEC = re.compile(r"\bT[SR]\s+(\d{2}\.\d{3}(?:-\d+)?)")
# "clause 5.2", but not "clause 6.5 of TS 38.331" which points into another spec
REFERENCED_CLAUSE = re.compile(
    r"\b(?:[Ss]ub)?[Cc]lauses?\s+((?>(?:\d+[A-Z]?|[A-Z])(?:\.\d+[A-Z]?)*))(?!\s+of\s+T[SR]\b)"
)
FOOTNOTE_MARK = re.compile(r"^[\d,\s]*\d[\d,\s]*$")


@dataclass
class Clause:
    spec: str
    release: str
    version: str
    clause_id: str
    title: str
    path: list[str]  # ancestors as "id title", outermost first
    blocks: list[dict] = field(default_factory=list)
    text: str = ""  # plain text rendering of blocks, used for search and diff
    referenced_clauses: list[str] = field(default_factory=list)
    referenced_specs: list[str] = field(default_factory=list)


@dataclass
class ParsedDoc:
    spec: str
    release: str
    version: str
    clauses: list[Clause]
    unnumbered_headings: list[str]
    duplicate_clause_ids: list[str]


def doc_info(name: str) -> tuple[str, str, str]:
    """Spec, release and version from an archive name, e.g. 38300-ib0 -> 38.300, Rel-18, 18.11.0"""
    match = FILE_NAME.match(name)
    if match is None:
        raise ValueError(f"unexpected file name: {name}")
    number, letter, minor, patch = match.groups()
    major = ord(letter) - ord("a") + 10  # h -> 17, i -> 18, j -> 19
    spec = f"{number[:2]}.{number[2:]}"
    version = f"{major}.{int(minor, 36)}.{int(patch, 36)}"
    return spec, f"Rel-{major}", version


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_heading(style_level: int, text: str) -> tuple[str, str] | None:
    """Return (clause_id, title) for a heading, or None if it has no clause number."""
    annex = ANNEX_HEADING.match(text.strip())
    if style_level >= 8 and annex:
        return annex.group(1), clean(annex.group(2))
    parts = clean(text).split(" ", 1)
    if CLAUSE_ID.match(parts[0]):
        return parts[0], parts[1] if len(parts) > 1 else ""
    return None


def cell_text(cell: _Cell) -> str:
    """Cell text with superscript footnote markers written as "(note 16)". Otherwise
    band n24 with footnote 16 would read as n2416."""
    paragraphs = []
    for paragraph in cell.paragraphs:
        text, note = "", ""
        for item in paragraph.iter_inner_content():
            for run in item.runs if isinstance(item, Hyperlink) else [item]:
                if run.font.superscript and FOOTNOTE_MARK.match(run.text):
                    note += run.text
                    continue
                if note:
                    text += f" (note {note.strip(', ')})"
                    note = ""
                text += run.text
        if note:
            text += f" (note {note.strip(', ')})"
        paragraphs.append(text)
    return clean(" ".join(paragraphs))


def table_rows(table: Table) -> list[list[str]]:
    return [[cell_text(cell) for cell in row.cells] for row in table.rows]


def count_header_rows(rows: list[list[str]]) -> int:
    """Guess how many leading rows form the table header (1 to 3).

    A following row still belongs to the header if its first cell is merged down from
    the row above (python-docx repeats the text), if the row above is a title spanning
    the whole table, or if it is empty below a row that has a group title merged across
    columns, e.g.

        Pre-coding | Channel bandwidth | Channel bandwidth
        Pre-coding | 20 MHz            | 40 MHz
        DFT-s-OFDM | ...
    """
    count = 1
    while count < min(3, len(rows) - 1):
        above, row = rows[count - 1], rows[count]
        merged_down = row[0] != "" and row[0] == above[0]
        merged_across = any(a == b and a for a, b in pairwise(above))
        title_row = len(above) > 1 and len(set(above)) == 1  # one cell spanning the table
        if not (merged_down or title_row or (row[0] == "" and merged_across)):
            break
        count += 1
    return count


def table_as_text(rows: list[list[str]]) -> str:
    """One line per row, cells joined with " | ". Cells are kept as they are so columns
    line up with the header, even where python-docx repeats a merged cell. Only a row
    that is one cell spanning the whole table (a title or NOTE row) is written once."""
    lines = []
    for row in rows:
        if len(set(row)) == 1:
            lines.append(row[0])
        else:
            lines.append(" | ".join(row))
    return "\n".join(lines)


def blocks_to_text(blocks: list[dict]) -> str:
    parts = []
    for block in blocks:
        if block["type"] == "table":
            parts.append(table_as_text(block["rows"]))
        else:
            parts.append(block["text"])
    return "\n".join(parts)


def table_blocks(clauses: list[Clause]) -> list[dict]:
    return [b for c in clauses for b in c.blocks if b["type"] == "table"]


def find_references(text: str) -> tuple[list[str], list[str]]:
    clauses = {m for m in REFERENCED_CLAUSE.findall(text) if any(c.isdigit() for c in m)}
    specs = set(REFERENCED_SPEC.findall(text))
    return sorted(clauses), sorted(specs)


def docx_parts(folder: Path) -> list[Path]:
    """The .docx files of one spec in reading order. Large specs are split into several
    files, named so that sorting gives the right order. The cover page is skipped."""
    return sorted(p for p in folder.glob("*.docx") if "cover" not in p.name.lower())


def parse_spec(folder: Path) -> ParsedDoc:
    spec, release, version = doc_info(folder.name)
    clauses: dict[str, Clause] = {}
    unnumbered: list[str] = []
    duplicates: list[str] = []

    current: str | None = None  # clause id we are currently adding text to
    skipping = False  # inside the change history annex
    last_paragraph = ""  # used as table caption

    for part in docx_parts(folder):
        for block in Document(str(part)).iter_inner_content():
            if isinstance(block, Table):
                if current is None or skipping:
                    continue
                rows = table_rows(block)
                blocks = clauses[current].blocks
                table_number = sum(1 for b in blocks if b["type"] == "table") + 1
                blocks.append(
                    {
                        "type": "table",
                        "table_id": f"{current}/{table_number}",
                        "caption": last_paragraph if last_paragraph.startswith("Table") else "",
                        "header_rows": count_header_rows(rows),
                        "rows": rows,
                    }
                )
                continue

            style = block.style.name if block.style is not None else ""
            text = block.text
            heading = HEADING_STYLE.match(style)

            if heading and text.strip():
                parsed = split_heading(int(heading.group(1)), text)
                if parsed is None:
                    # Unnumbered heading inside a clause (e.g. a table title styled as a
                    # heading): keep it as normal text of the current clause.
                    unnumbered.append(clean(text))
                    if current is not None and not skipping:
                        clauses[current].blocks.append(
                            {"type": "paragraph", "style": style, "text": clean(text)}
                        )
                    continue

                clause_id, title = parsed
                if ANNEX_HEADING.match(text.strip()):
                    skipping = "change history" in title.lower()
                if skipping:
                    continue

                current = clause_id
                if clause_id in clauses:
                    # Same heading repeated, e.g. at the start of the next file part.
                    # Keep adding to the existing clause.
                    duplicates.append(clause_id)
                    continue
                clauses[clause_id] = Clause(
                    spec, release, version, clause_id, title, path=ancestors(clause_id, clauses)
                )
                continue

            if style.lower().startswith("toc") or current is None or skipping:
                continue
            text = clean(text)
            if text:
                clauses[current].blocks.append({"type": "paragraph", "style": style, "text": text})
                last_paragraph = text

    for clause in clauses.values():
        clause.text = blocks_to_text(clause.blocks)
        clause.referenced_clauses, clause.referenced_specs = find_references(clause.text)

    return ParsedDoc(spec, release, version, list(clauses.values()), unnumbered, duplicates)


def ancestors(clause_id: str, clauses: dict[str, Clause]) -> list[str]:
    """Path of parent clauses, e.g. 16.4.2 -> ["16 ...", "16.4 ..."]."""
    path = []
    parent = clause_id
    while "." in parent:
        parent = parent.rsplit(".", 1)[0]
        if parent in clauses:
            path.insert(0, f"{parent} {clauses[parent].title}")
    return path


def write_report(doc: ParsedDoc, path: Path) -> None:
    clause_ids = {c.clause_id for c in doc.clauses}
    has_children = {c.clause_id.rsplit(".", 1)[0] for c in doc.clauses if "." in c.clause_id}
    # Clauses titled "Void" or "Reserved" are empty in the spec itself
    empty_leaves = [
        c.clause_id
        for c in doc.clauses
        if not c.text
        and c.clause_id not in has_children
        and c.title.strip("()").lower() not in ("void", "reserved")
    ]
    missing_parents = sorted(
        {cid.rsplit(".", 1)[0] for cid in clause_ids if "." in cid} - clause_ids
    )
    tables = table_blocks(doc.clauses)
    uncaptioned = sum(1 for t in tables if not t["caption"])
    multi_row_headers = [t["table_id"] for t in tables if t["header_rows"] > 1]
    largest = sorted(doc.clauses, key=lambda c: len(c.text), reverse=True)[:5]

    lines = [
        f"# Parse report: {doc.spec} {doc.release} (v{doc.version})",
        "",
        f"- clauses: {len(doc.clauses)}",
        f"- clauses with text: {sum(1 for c in doc.clauses if c.text)}",
        f"- tables: {len(tables)} ({uncaptioned} without caption)",
        f"- total text: {sum(len(c.text) for c in doc.clauses):,} characters",
        "",
        f"## Empty leaf clauses ({len(empty_leaves)})",
        ", ".join(empty_leaves) or "none",
        "",
        f"## Parent clause missing ({len(missing_parents)})",
        ", ".join(missing_parents) or "none",
        "",
        f"## Repeated clause headings ({len(doc.duplicate_clause_ids)})",
        ", ".join(doc.duplicate_clause_ids) or "none",
        "",
        f"## Headings without clause number ({len(doc.unnumbered_headings)})",
        *[f"- {h}" for h in doc.unnumbered_headings[:20]],
        *(["- ..."] if len(doc.unnumbered_headings) > 20 else []),
        "",
        f"## Tables with a multi-row header ({len(multi_row_headers)})",
        ", ".join(multi_row_headers[:40]) + (" ..." if len(multi_row_headers) > 40 else ""),
        "",
        "## Largest clauses",
        *[f"- {c.clause_id} {c.title}: {len(c.text):,} characters" for c in largest],
    ]
    path.write_text("\n".join(lines) + "\n")


def write_jsonl(records: list, path: Path) -> None:
    with path.open("w") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def load_clauses(spec: str, release: str) -> list[Clause]:
    """Read the parsed clauses of one spec release from data/parsed/."""
    path = config.PARSED_DIR / f"{spec}_{release}.clauses.jsonl"
    with path.open() as f:
        return [Clause(**json.loads(line)) for line in f]


def main() -> None:
    config.PARSED_DIR.mkdir(parents=True, exist_ok=True)
    for name in config.DOCUMENTS:
        folder = config.DOCX_DIR / name
        if not folder.exists():
            print(f"skipping {name}: {folder} not found, run `make download` first")
            continue
        doc = parse_spec(folder)
        stem = f"{doc.spec}_{doc.release}"
        write_jsonl(doc.clauses, config.PARSED_DIR / f"{stem}.clauses.jsonl")
        write_report(doc, config.PARSED_DIR / f"{stem}_report.md")
        print(f"{stem}: {len(doc.clauses)} clauses, {len(table_blocks(doc.clauses))} tables")


if __name__ == "__main__":
    main()
