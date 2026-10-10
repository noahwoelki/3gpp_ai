"""Extract abbreviations, symbols and definitions into one glossary (F5).

Reads the "Abbreviations", "Symbols" and "Definitions" clauses of every spec, plus
TR 21.905, which is the general 3GPP vocabulary. The .docx is read directly, because
abbreviation lines separate term and meaning with a tab ("1x RTT<tab>CDMA2000 1x ..."),
and the clause parser turns tabs into spaces.

- Abbreviations and symbols: one paragraph per entry, "term<tab>meaning".
- Definitions: "term: definition", followed paragraphs (notes, bullets) belong to it.

Output: data/parsed/glossary.jsonl
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from docx import Document

from specdelta import config
from specdelta.ingest.parse_docx import HEADING_STYLE, clean, doc_info, docx_parts, split_heading

KIND_BY_TITLE = {
    "abbreviations": "abbreviation",
    "symbols": "symbol",
    "definitions": "definition",
    "terms and definitions": "definition",
}
MAX_TERM_WORDS = 10  # longer text before ":" is a sentence, not a defined term


@dataclass
class GlossaryEntry:
    spec: str
    release: str
    clause_id: str
    kind: str  # abbreviation, symbol or definition
    term: str
    text: str


def parse_glossary(folder: Path) -> list[GlossaryEntry]:
    spec, release, _ = doc_info(folder.name)
    entries: list[GlossaryEntry] = []
    clause_id, kind = "", None  # kind is None outside glossary clauses

    for part in docx_parts(folder):
        for paragraph in Document(str(part)).paragraphs:
            style = paragraph.style.name if paragraph.style is not None else ""
            raw = paragraph.text.strip()
            heading = HEADING_STYLE.match(style)
            if heading and raw:
                parsed = split_heading(int(heading.group(1)), raw)
                if parsed is not None:  # unnumbered headings are the "A", "B" letter groups
                    clause_id, title = parsed
                    kind = KIND_BY_TITLE.get(title.lower())
                continue
            if kind is None or not raw:
                continue

            if kind in ("abbreviation", "symbol"):
                if "\t" in raw:
                    term, meaning = raw.split("\t", 1)
                    entries.append(
                        GlossaryEntry(spec, release, clause_id, kind, clean(term), clean(meaning))
                    )
                continue

            term, separator, definition = raw.partition(":")
            is_new_term = separator and style == "Normal" and len(term.split()) <= MAX_TERM_WORDS
            if is_new_term:
                entries.append(
                    GlossaryEntry(spec, release, clause_id, kind, clean(term), clean(definition))
                )
            elif (
                entries and entries[-1].kind == "definition" and entries[-1].clause_id == clause_id
            ):
                entries[-1].text += "\n" + clean(raw)  # note or bullet of the definition above
    return entries


def main() -> None:
    entries = []
    for name in config.DOCUMENTS:
        found = parse_glossary(config.DOCX_DIR / name)
        counts = {
            k: sum(1 for e in found if e.kind == k)
            for k in ("abbreviation", "symbol", "definition")
        }
        print(f"{name}: {counts}")
        entries += found
    with (config.PARSED_DIR / "glossary.jsonl").open("w") as f:
        for entry in entries:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    print(f"{len(entries)} glossary entries")


if __name__ == "__main__":
    main()
