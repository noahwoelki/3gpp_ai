"""Turn the key 38.101-1 tables into typed rows for SQL lookups (F3).

- Table 5.2-1 (NR operating bands in FR1) -> one row per band with UL/DL ranges in MHz
- Table 6.2.1-1 (UE power class) -> one row per band and power class

Footnote markers like "n24 (note 16)" are moved into a separate notes column, with the
note text from the bottom of the table.

Output: data/parsed/bands.jsonl and data/parsed/power_classes.jsonl, all releases.
"""

import json
import re
from dataclasses import asdict, dataclass

from specdelta import config
from specdelta.ingest.chunk import is_note_row, mentioned_notes, split_notes
from specdelta.ingest.parse_docx import doc_info, load_clauses

SPEC = "38.101-1"
BAND_TABLE = "Table 5.2-1:"
POWER_CLASS_TABLE = "Table 6.2.1-1:"

NOTE_MARK = re.compile(r"\s*\(note [\d, ]+\)", re.IGNORECASE)
FREQUENCY_RANGE = re.compile(r"([\d.]+)\s*MHz\s*[–-]\s*([\d.]+)\s*MHz")
POWER_CLASS_HEADER = re.compile(r"Class\s+([\d.]+)")


@dataclass
class Band:
    release: str
    band: str  # "n78"
    band_number: int
    ul_low_mhz: float | None  # None for SDL bands
    ul_high_mhz: float | None
    dl_low_mhz: float | None  # None for SUL bands
    dl_high_mhz: float | None
    duplex_mode: str  # FDD, TDD, SDL, SUL
    notes: str


@dataclass
class PowerClass:
    release: str
    band: str
    band_number: int
    power_class: str  # "3", "1.5", ...
    max_power_dbm: float
    tolerance_db: str  # kept as text, e.g. "+2/-3" or "±2"
    notes: str


def find_table(release: str, caption_start: str) -> dict:
    for clause in load_clauses(SPEC, release):
        for block in clause.blocks:
            if block["type"] == "table" and block["caption"].startswith(caption_start):
                return block
    raise ValueError(f"{caption_start} not found in {SPEC} {release}")


def strip_notes(cell: str) -> str:
    return NOTE_MARK.sub("", cell).strip(" ,")


def notes_for(cells: list[str], notes: dict[str, str]) -> str:
    """Text of the notes that the given cells refer to."""
    numbers = mentioned_notes(" ".join(cells))
    return " ".join(notes[n] for n in sorted(numbers, key=int) if n in notes)


def frequency_range(cell: str) -> tuple[float | None, float | None]:
    match = FREQUENCY_RANGE.search(cell)
    if match is None:  # "N/A"
        return None, None
    return float(match.group(1)), float(match.group(2))


def parse_bands(release: str) -> list[Band]:
    table = find_table(release, BAND_TABLE)
    rows = table["rows"][table["header_rows"] :]
    notes = split_notes([row for row in rows if is_note_row(row)])
    bands = []
    for row in rows:
        if is_note_row(row):
            continue
        band = strip_notes(row[0])
        if not re.fullmatch(r"n\d+", band):
            continue
        ul_low, ul_high = frequency_range(row[1])
        dl_low, dl_high = frequency_range(row[2])
        bands.append(
            Band(release, band, int(band[1:]), ul_low, ul_high, dl_low, dl_high,
                 strip_notes(row[3]), notes_for(row, notes))
        )  # fmt: skip
    return bands


def parse_power_classes(release: str) -> list[PowerClass]:
    """The table has one (dBm, tolerance) column pair per power class."""
    table = find_table(release, POWER_CLASS_TABLE)
    header = table["rows"][0]
    rows = table["rows"][table["header_rows"] :]
    notes = split_notes([row for row in rows if is_note_row(row)])
    class_columns = [
        (POWER_CLASS_HEADER.search(cell).group(1), i)
        for i, cell in enumerate(header)
        if POWER_CLASS_HEADER.search(cell)
    ]
    result = []
    for row in rows:
        band = strip_notes(row[0])
        if is_note_row(row) or not re.fullmatch(r"n\d+", band):
            continue
        for power_class, column in class_columns:
            power = strip_notes(row[column])
            if not power:
                continue  # band does not support this class
            tolerance = row[column + 1]
            row_notes = notes_for([row[0], row[column], tolerance], notes)
            result.append(
                PowerClass(release, band, int(band[1:]), power_class, float(power),
                           strip_notes(tolerance), row_notes)
            )  # fmt: skip
    return result


def write_jsonl(records: list, name: str) -> None:
    with (config.PARSED_DIR / name).open("w") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def main() -> None:
    releases = [doc_info(name)[1] for name in config.DOCUMENTS if name.startswith("38101-1")]
    bands = [band for release in releases for band in parse_bands(release)]
    power_classes = [pc for release in releases for pc in parse_power_classes(release)]
    write_jsonl(bands, "bands.jsonl")
    write_jsonl(power_classes, "power_classes.jsonl")
    for release in releases:
        band_count = sum(1 for b in bands if b.release == release)
        class_count = sum(1 for p in power_classes if p.release == release)
        print(f"{SPEC} {release}: {band_count} bands, {class_count} power class rows")


if __name__ == "__main__":
    main()
