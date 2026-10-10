"""Split parsed clauses into chunks for search.

Text and tables are chunked separately:

- Text chunks hold the paragraphs of a clause, about MAX_WORDS each, cut at paragraph
  boundaries with a one-paragraph overlap. A table inside the text is replaced by a
  one-line placeholder with its caption.
- Table chunks can each be read on their own: caption, header rows, a group of data
  rows and only the NOTE rows these data rows refer to. Large tables become several
  chunks, each repeating the header.

Tables that need LARGE_TABLE_CHUNKS or more chunks are marked embed=False. Their row
chunks look nearly identical to an embedding model and would crowd the vector search,
so they are only used for keyword search. describe_tables.py writes one embedded
description chunk per large table instead.

Every chunk stores where it came from (block range in the clause, or table id and row
range), so the UI can show the full clause or table with the matched part highlighted.

Output: data/parsed/<spec>_<release>.chunks.jsonl
"""

import json
import re
from dataclasses import asdict, dataclass, field

from specdelta import config
from specdelta.ingest.parse_docx import (
    Clause,
    doc_info,
    find_references,
    load_clauses,
    table_as_text,
)

MAX_WORDS = 450  # roughly 600 tokens
OVERLAP_WORDS = 80  # the last paragraph is repeated in the next chunk if it is this short
TABLE_MAX_WORDS = 400  # header + rows + notes of one table chunk
LARGE_TABLE_CHUNKS = 3

NOTE_START = re.compile(r"(?=\bNOTE\s*\d*\s*:)")
NOTE_NUMBER = re.compile(r"^NOTE\s*(\d*)\s*:")
NOTE_MENTION = re.compile(r"\bnote\s*(\d+(?:\s*,\s*\d+)*)", re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: str
    spec: str
    release: str
    version: str
    clause_id: str
    title: str
    path: list[str]
    kind: str  # "text", "table" or "table_description"
    header: str  # "[38.300 Rel-18 §16.4.2 Title]", put in front of the content for embedding
    content: str
    # Where the chunk comes from: blocks [block_start, block_end] of the clause, and for
    # table chunks also the table id and the data rows [row_start, row_end] of that table
    block_start: int
    block_end: int
    table_id: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    embed: bool = True  # False for row chunks of large tables, see module docstring
    referenced_clauses: list[str] = field(default_factory=list)
    referenced_specs: list[str] = field(default_factory=list)


def word_count(text: str) -> int:
    return len(text.split())


def table_placeholder(block: dict) -> str:
    return f"[{block['caption'] or 'Table'} - see table]"


def split_long_text(text: str) -> list[str]:
    """A single paragraph longer than MAX_WORDS is cut into word windows."""
    words = text.split()
    return [" ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]


def text_chunks(clause: Clause) -> list[tuple[int, int, str]]:
    """Group the clause paragraphs into (block_start, block_end, content) chunks."""
    units = []  # (block index, text)
    for index, block in enumerate(clause.blocks):
        if block["type"] == "table":
            previous = clause.blocks[index - 1] if index > 0 else {}
            if block["caption"] and previous.get("text") == block["caption"]:
                continue  # the caption paragraph above already stands in for the table
            text = table_placeholder(block)
        else:
            text = block["text"]
        for piece in split_long_text(text) if word_count(text) > MAX_WORDS else [text]:
            units.append((index, piece))

    chunks = []
    current: list[tuple[int, str]] = []
    for unit in units:
        current_words = sum(word_count(text) for _, text in current)
        if current and current_words + word_count(unit[1]) > MAX_WORDS:
            chunks.append(current)
            last = current[-1]
            current = [last] if word_count(last[1]) <= OVERLAP_WORDS else []
        current.append(unit)
    if current:
        chunks.append(current)

    # A chunk that is only table placeholders carries no text worth searching
    return [
        (group[0][0], group[-1][0], "\n".join(text for _, text in group))
        for group in chunks
        if any(clause.blocks[i]["type"] != "table" for i, _ in group)
    ]


def split_notes(note_rows: list[list[str]]) -> dict[str, str]:
    """Map note number -> note text. Unnumbered notes ("NOTE: ...") get the key ""."""
    notes = {}
    for row in note_rows:
        for part in NOTE_START.split(row[0]):
            match = NOTE_NUMBER.match(part.strip())
            if match:
                notes[match.group(1)] = part.strip()
    return notes


def mentioned_notes(text: str) -> set[str]:
    numbers = set()
    for match in NOTE_MENTION.findall(text):
        numbers.update(n.strip() for n in match.split(","))
    return numbers


def is_note_row(row: list[str]) -> bool:
    return len(set(row)) == 1 and NOTE_NUMBER.match(row[0]) is not None


def table_chunks(block: dict) -> list[tuple[int, int, str]]:
    """Split one table into (row_start, row_end, content) chunks."""
    rows = block["rows"]
    header = rows[: block["header_rows"]]
    body = list(enumerate(rows))[block["header_rows"] :]
    notes = split_notes([row for _, row in body if is_note_row(row)])
    data = [(i, row) for i, row in body if not is_note_row(row)]
    if not data:
        return []

    header_text = table_as_text(header)
    row_budget = max(100, TABLE_MAX_WORDS - word_count(header_text))

    groups: list[list[tuple[int, list[str]]]] = [[]]
    words = 0
    for index, row in data:
        row_words = word_count(table_as_text([row]))  # count the "|" too, they cost tokens
        # An empty first cell usually continues the row above (e.g. more SCS values of the
        # same band), so prefer to cut before a row that starts a new entry. Some tables
        # leave the first column empty almost everywhere, hence the hard limit.
        over_budget = words + row_words > row_budget
        starts_entry = row[0] != ""
        if groups[-1] and over_budget and (starts_entry or words > 1.5 * row_budget):
            groups.append([])
            words = 0
        groups[-1].append((index, row))
        words += row_words

    caption = block["caption"] or "Table"
    chunks = []
    for group in groups:
        rows_text = table_as_text([row for _, row in group])
        wanted = mentioned_notes(rows_text) | {""}
        note_lines = [text for number, text in notes.items() if number in wanted]
        position = ""
        if len(groups) > 1:
            first = data.index(group[0]) + 1
            position = f" (rows {first}-{first + len(group) - 1} of {len(data)})"
        content = "\n".join([caption + position, header_text, rows_text, *note_lines])
        chunks.append((group[0][0], group[-1][0], content))
    return chunks


def chunk_clause(clause: Clause) -> list[Chunk]:
    header = f"[{clause.spec} {clause.release} §{clause.clause_id} {clause.title}]"
    base = dict(
        spec=clause.spec,
        release=clause.release,
        version=clause.version,
        clause_id=clause.clause_id,
        title=clause.title,
        path=clause.path,
        header=header,
    )
    chunks = []

    def add(kind: str, content: str, block_start: int, block_end: int, **table_fields) -> None:
        referenced_clauses, referenced_specs = find_references(content)
        chunk_id = f"{clause.spec}_{clause.release}_{clause.clause_id}_{len(chunks)}"
        chunks.append(
            Chunk(chunk_id=chunk_id, kind=kind, content=content, block_start=block_start,
                  block_end=block_end, referenced_clauses=referenced_clauses,
                  referenced_specs=referenced_specs, **base, **table_fields)
        )  # fmt: skip

    for block_start, block_end, content in text_chunks(clause):
        add("text", content, block_start, block_end)

    for index, block in enumerate(clause.blocks):
        if block["type"] != "table":
            continue
        pieces = table_chunks(block)
        embed = len(pieces) < LARGE_TABLE_CHUNKS
        for row_start, row_end, content in pieces:
            add("table", content, index, index, table_id=block["table_id"],
                row_start=row_start, row_end=row_end, embed=embed)  # fmt: skip
    return chunks


def load_chunks(spec: str, release: str) -> list[dict]:
    """All chunks of one spec release: text and table chunks plus the table descriptions
    written by describe_tables.py (if it has been run)."""
    chunks = []
    for suffix in ("chunks", "table_descriptions"):
        path = config.PARSED_DIR / f"{spec}_{release}.{suffix}.jsonl"
        if path.exists():
            with path.open() as f:
                chunks += [json.loads(line) for line in f]
    return chunks


def main() -> None:
    for name in config.DOCUMENTS:
        spec, release, _ = doc_info(name)
        chunks = [chunk for clause in load_clauses(spec, release) for chunk in chunk_clause(clause)]
        path = config.PARSED_DIR / f"{spec}_{release}.chunks.jsonl"
        with path.open("w") as f:
            for chunk in chunks:
                f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
        tables = sum(1 for c in chunks if c.kind == "table")
        not_embedded = sum(1 for c in chunks if not c.embed)
        longest = max(word_count(c.content) for c in chunks)
        print(
            f"{spec}_{release}: {len(chunks)} chunks ({tables} table, "
            f"{not_embedded} keyword only), longest {longest} words"
        )


if __name__ == "__main__":
    main()
