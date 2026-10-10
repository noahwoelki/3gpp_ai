"""Write a short description of each large table with Gemini Flash.

Large tables (see chunk.LARGE_TABLE_CHUNKS) are not embedded row by row. Instead they
get one description chunk that says what the table contains, which is embedded and
searched like normal text. The agent then fetches the actual rows when it needs them.
The description is only used to find the table, answers always cite the table itself.

Descriptions are kept in data/parsed/<spec>_<release>.table_descriptions.jsonl. Tables
that already have a description are skipped, so rerunning only fills in what is missing.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from google import genai
from google.genai import types

from specdelta import config
from specdelta.ingest.chunk import Chunk, chunk_clause, word_count
from specdelta.ingest.parse_docx import Clause, doc_info, load_clauses, table_as_text

SAMPLE_ROWS = 8
INTRO_WORDS = 120

PROMPT = """Below is an excerpt of a table from 3GPP {spec} {release}, clause {clause_id} \
"{title}" (clause path: {path}).

Write a description of this table in 3 to 5 sentences, for a search index. Say what one
row represents, what the columns contain, which kinds of values appear (for example band
numbers, CA configurations, power levels in dBm) and what questions the table answers.
Use the terms an engineer would search for. Do not list many individual values and do
not add anything that is not supported by the excerpt. Answer with the description only.

Text of the clause before the table:
{intro}

Caption: {caption}
Total data rows: {row_count}

Header and sample rows:
{sample}
"""


def clause_intro(clause: Clause, table_index: int) -> str:
    """The paragraphs of the clause before the table, cut to INTRO_WORDS."""
    paragraphs = [b["text"] for b in clause.blocks[:table_index] if b["type"] == "paragraph"]
    words = " ".join(paragraphs).split()
    return " ".join(words[:INTRO_WORDS]) or "(none)"


def table_sample(block: dict) -> str:
    """Header plus rows from the start, middle and end of the table."""
    rows = block["rows"]
    header, data = rows[: block["header_rows"]], rows[block["header_rows"] :]
    if len(data) > SAMPLE_ROWS:
        third = SAMPLE_ROWS // 3
        middle = len(data) // 2
        data = data[:third] + data[middle : middle + third] + data[-(SAMPLE_ROWS - 2 * third) :]
    return table_as_text(header + data)


def large_tables(clauses: list[Clause]) -> list[tuple[Clause, int, list[Chunk]]]:
    """(clause, block index of the table, its row chunks) for every large table."""
    result = []
    for clause in clauses:
        chunks = chunk_clause(clause)
        for index, block in enumerate(clause.blocks):
            if block["type"] != "table":
                continue
            rows = [c for c in chunks if c.table_id == block["table_id"]]
            if rows and not rows[0].embed:
                result.append((clause, index, rows))
    return result


def describe(client: genai.Client, clause: Clause, index: int, row_chunks: list[Chunk]) -> Chunk:
    block = clause.blocks[index]
    prompt = PROMPT.format(
        spec=clause.spec,
        release=clause.release,
        clause_id=clause.clause_id,
        title=clause.title,
        path=" > ".join(clause.path) or "-",
        intro=clause_intro(clause, index),
        caption=block["caption"] or "(no caption)",
        row_count=len(block["rows"]) - block["header_rows"],
        sample=table_sample(block),
    )
    response = client.models.generate_content(
        model=config.FLASH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    caption = block["caption"] or f"Table in clause {clause.clause_id}"
    first = row_chunks[0]
    return Chunk(
        chunk_id=f"{clause.spec}_{clause.release}_{block['table_id']}_description",
        spec=clause.spec,
        release=clause.release,
        version=clause.version,
        clause_id=clause.clause_id,
        title=clause.title,
        path=clause.path,
        kind="table_description",
        header=first.header,
        content=f"{caption}\n{response.text.strip()}",
        block_start=index,
        block_end=index,
        table_id=block["table_id"],
        row_start=row_chunks[0].row_start,
        row_end=row_chunks[-1].row_end,
    )


def main() -> None:
    client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.VERTEX_LOCATION)
    for name in config.DOCUMENTS:
        spec, release, _ = doc_info(name)
        path = config.PARSED_DIR / f"{spec}_{release}.table_descriptions.jsonl"
        existing = {}
        if path.exists():
            with path.open() as f:
                existing = {c["table_id"]: c for c in map(json.loads, f)}

        todo = [
            t for t in large_tables(load_clauses(spec, release)) if t[2][0].table_id not in existing
        ]
        if not todo and not existing:
            continue
        print(f"{spec}_{release}: {len(existing)} described, {len(todo)} to do")

        def run(item):
            clause, index, row_chunks = item
            try:
                return describe(client, clause, index, row_chunks)
            except Exception as error:  # one failed call should not stop the batch
                print(f"  failed {clause.clause_id} {row_chunks[0].table_id}: {error}")
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            for chunk in pool.map(run, todo):
                if chunk is not None:
                    existing[chunk.table_id] = asdict(chunk)

        with path.open("w") as f:
            for chunk in existing.values():
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        longest = max((word_count(c["content"]) for c in existing.values()), default=0)
        print(f"  wrote {len(existing)} descriptions, longest {longest} words")


if __name__ == "__main__":
    main()
