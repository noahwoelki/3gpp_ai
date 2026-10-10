"""Load the parsed corpus into BigQuery.

Tables (all replaced on every run):

    clauses        one row per clause, with the blocks as a JSON string (drives the diff)
    chunks         search chunks with their embedding (empty for keyword-only chunks)
    spec_tables    one row per table, rows as a JSON string in table_rows
    table_cells    one row per table cell, for filtering inside any table
    bands          typed table 5.2-1 of 38.101-1
    power_classes  typed table 6.2.1-1 of 38.101-1
    glossary       abbreviations, symbols and definitions
"""

import json
import re

from google.cloud import bigquery

from specdelta import config
from specdelta.ingest.chunk import is_note_row, load_chunks, split_notes
from specdelta.ingest.embed import load_embeddings
from specdelta.ingest.parse_docx import doc_info, load_clauses

S = bigquery.SchemaField
REPEATED_STRING = {"field_type": "STRING", "mode": "REPEATED"}

SCHEMAS = {
    "clauses": [
        S("spec", "STRING"), S("release", "STRING"), S("version", "STRING"),
        S("clause_id", "STRING"), S("title", "STRING"), S("path", **REPEATED_STRING),
        S("text", "STRING"), S("blocks", "STRING"),
        S("referenced_clauses", **REPEATED_STRING), S("referenced_specs", **REPEATED_STRING),
    ],
    "chunks": [
        S("chunk_id", "STRING"), S("spec", "STRING"), S("release", "STRING"),
        S("version", "STRING"), S("clause_id", "STRING"), S("title", "STRING"),
        S("path", **REPEATED_STRING), S("kind", "STRING"), S("header", "STRING"),
        S("content", "STRING"), S("block_start", "INTEGER"), S("block_end", "INTEGER"),
        S("table_id", "STRING"), S("row_start", "INTEGER"), S("row_end", "INTEGER"),
        S("embed", "BOOLEAN"), S("referenced_clauses", **REPEATED_STRING),
        S("referenced_specs", **REPEATED_STRING),
        S("embedding", "FLOAT64", mode="REPEATED"),
    ],
    "spec_tables": [
        S("spec", "STRING"), S("release", "STRING"), S("clause_id", "STRING"),
        S("table_id", "STRING"), S("table_number", "STRING"), S("caption", "STRING"),
        S("header_rows", "INTEGER"), S("row_count", "INTEGER"), S("notes", "STRING"),
        S("table_rows", "STRING"),
    ],
    "table_cells": [
        S("spec", "STRING"), S("release", "STRING"), S("table_id", "STRING"),
        S("row_index", "INTEGER"), S("column_index", "INTEGER"),
        S("column_header", "STRING"), S("value", "STRING"),
    ],
    "bands": [
        S("release", "STRING"), S("band", "STRING"), S("band_number", "INTEGER"),
        S("ul_low_mhz", "FLOAT64"), S("ul_high_mhz", "FLOAT64"),
        S("dl_low_mhz", "FLOAT64"), S("dl_high_mhz", "FLOAT64"),
        S("duplex_mode", "STRING"), S("notes", "STRING"),
    ],
    "power_classes": [
        S("release", "STRING"), S("band", "STRING"), S("band_number", "INTEGER"),
        S("power_class", "STRING"), S("max_power_dbm", "FLOAT64"),
        S("tolerance_db", "STRING"), S("notes", "STRING"),
    ],
    "glossary": [
        S("spec", "STRING"), S("release", "STRING"), S("clause_id", "STRING"),
        S("kind", "STRING"), S("term", "STRING"), S("text", "STRING"),
    ],
}  # fmt: skip

# "Table 5.2-1: ...", also the misspelled "TableA.7.3-3:" and "Tables 7.7E.1A-2:"
TABLE_NUMBER = re.compile(r"^Tables?\s*([A-Z0-9][\w.\-]*?)[:\s]")


def column_headers(block: dict) -> list[str]:
    """One label per column, joining the header rows, e.g. "Channel bandwidth / 20 MHz"."""
    header = block["rows"][: block["header_rows"]]
    labels = []
    for column in range(len(header[0])):
        parts = []
        for row in header:
            cell = row[column] if column < len(row) else ""
            if cell and cell not in parts:
                parts.append(cell)
        labels.append(" / ".join(parts))
    return labels


def table_rows_for(spec: str, release: str) -> tuple[list[dict], list[dict]]:
    """Rows for spec_tables and table_cells."""
    tables, cells = [], []
    for clause in load_clauses(spec, release):
        for block in clause.blocks:
            if block["type"] != "table":
                continue
            rows = block["rows"]
            data = [(i, row) for i, row in enumerate(rows) if i >= block["header_rows"]]
            notes = split_notes([row for _, row in data if is_note_row(row)])
            match = TABLE_NUMBER.match(block["caption"])
            tables.append(
                {
                    "spec": spec,
                    "release": release,
                    "clause_id": clause.clause_id,
                    "table_id": block["table_id"],
                    "table_number": match.group(1) if match else None,
                    "caption": block["caption"],
                    "header_rows": block["header_rows"],
                    "row_count": len(data),
                    "notes": "\n".join(notes.values()),
                    "table_rows": json.dumps(rows, ensure_ascii=False),
                }
            )
            headers = column_headers(block)
            for row_index, row in data:
                if is_note_row(row):
                    continue
                for column_index, value in enumerate(row):
                    if not value:
                        continue
                    header = headers[column_index] if column_index < len(headers) else ""
                    cells.append(
                        {
                            "spec": spec,
                            "release": release,
                            "table_id": block["table_id"],
                            "row_index": row_index,
                            "column_index": column_index,
                            "column_header": header,
                            "value": value,
                        }
                    )
    return tables, cells


def read_jsonl(name: str) -> list[dict]:
    with (config.PARSED_DIR / name).open() as f:
        return [json.loads(line) for line in f]


def load_table(client: bigquery.Client, name: str, rows: list[dict]) -> None:
    table_ref = f"{config.PROJECT_ID}.{config.BQ_DATASET}.{name}"
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMAS[name], write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    client.load_table_from_json(rows, table_ref, job_config=job_config).result()
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    client = bigquery.Client(project=config.PROJECT_ID)
    dataset = bigquery.Dataset(f"{config.PROJECT_ID}.{config.BQ_DATASET}")
    dataset.location = config.REGION
    client.create_dataset(dataset, exists_ok=True)

    clauses, chunks, tables, cells = [], [], [], []
    missing_embeddings = 0
    for name in config.DOCUMENTS:
        spec, release, _ = doc_info(name)
        for clause in load_clauses(spec, release):
            row = {field.name: getattr(clause, field.name) for field in SCHEMAS["clauses"]}
            row["blocks"] = json.dumps(clause.blocks, ensure_ascii=False)
            clauses.append(row)

        embeddings = load_embeddings(spec, release)
        for chunk in load_chunks(spec, release):
            chunk["embedding"] = embeddings.get(chunk["chunk_id"], []) if chunk["embed"] else []
            if chunk["embed"] and not chunk["embedding"]:
                missing_embeddings += 1
            chunks.append(chunk)

        spec_tables, table_cells = table_rows_for(spec, release)
        tables += spec_tables
        cells += table_cells

    if missing_embeddings:
        print(f"warning: {missing_embeddings} chunks have no embedding yet, run `make embed`")

    load_table(client, "clauses", clauses)
    load_table(client, "chunks", chunks)
    load_table(client, "spec_tables", tables)
    load_table(client, "table_cells", cells)
    load_table(client, "bands", read_jsonl("bands.jsonl"))
    load_table(client, "power_classes", read_jsonl("power_classes.jsonl"))
    load_table(client, "glossary", read_jsonl("glossary.jsonl"))


if __name__ == "__main__":
    main()
