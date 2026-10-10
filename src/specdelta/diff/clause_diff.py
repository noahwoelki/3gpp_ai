"""Compare the clauses of two releases of a spec.

Clauses are matched by clause number, and remaining ones by title (for clauses that
were renumbered). Each clause is marked added, removed, changed or unchanged. Text is
compared line by line (one line per paragraph or table row) after normalizing things
that change between releases without meaning anything, like whitespace, quote styles
and reference numbers ("TS 38.304 [20]" vs "[21]"). A clause counts as unchanged if only
whitespace or punctuation differs. Every other difference is kept, with the number of
changed words, so callers can rank changes by size and skip tiny edits when they want.

    python -m specdelta.diff.clause_diff 38.300            # whole spec
    python -m specdelta.diff.clause_diff 38.300 15.4 --show  # one clause tree, with diffs
"""

import argparse
import difflib
import re
from dataclasses import dataclass

from specdelta.ingest.parse_docx import Clause, load_clauses

# Renumbered clauses: titles must be nearly equal and the text must still be similar,
# otherwise every "General" clause would match every other "General" clause.
TITLE_MATCH = 0.9
TEXT_MATCH = 0.5


@dataclass
class ClauseDiff:
    clause_id: str  # number in the new release (old one for removed clauses)
    old_clause_id: str | None
    title: str
    status: str  # added, removed, changed, unchanged
    similarity: float  # 0..1, share of lines that stayed the same
    lines_added: int
    lines_removed: int
    changed_words: int  # words added or removed inside the changed lines
    old_text: str
    new_text: str
    diff: str  # unified diff of the normalized lines, empty if unchanged


def normalize_line(line: str) -> str:
    line = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]", "", line)  # reference numbers like [12]
    line = line.translate(str.maketrans("‘’“”–—", "''\"\"--"))
    return re.sub(r"\s+", " ", line).strip()


def normalized_lines(text: str) -> list[str]:
    return [n for n in (normalize_line(line) for line in text.splitlines()) if n]


def only_letters_and_digits(lines: list[str]) -> str:
    return re.sub(r"[\W_]+", "", "".join(lines))


def count_changed_words(old_lines: list[str], new_lines: list[str]) -> int:
    old_words, new_words = " ".join(old_lines).split(), " ".join(new_lines).split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    return sum(
        max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
    )


def compare_texts(old_text: str, new_text: str) -> tuple[float, int, int, int, str]:
    """Similarity, lines added, lines removed, changed words and unified diff of two
    clause texts. The diff is empty if nothing but whitespace or punctuation changed."""
    old_lines, new_lines = normalized_lines(old_text), normalized_lines(new_text)
    if only_letters_and_digits(old_lines) == only_letters_and_digits(new_lines):
        return 1.0, 0, 0, 0, ""
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    added = removed = changed_words = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            removed += i2 - i1
            added += j2 - j1
            changed_words += count_changed_words(old_lines[i1:i2], new_lines[j1:j2])
    diff = "\n".join(difflib.unified_diff(old_lines, new_lines, lineterm="", n=1))
    # Drop the "---"/"+++" file header lines, they carry no information here
    diff = diff.split("\n", 2)[2] if diff.startswith("---") else diff
    return matcher.ratio(), added, removed, changed_words, diff


def match_renumbered(old_left: list[Clause], new_left: list[Clause]) -> dict[str, str]:
    """Match clauses that exist in both releases under a different number.
    Returns new clause id -> old clause id."""
    matches = {}
    used = set()
    for new in new_left:
        best, best_score = None, 0.0
        for old in old_left:
            if old.clause_id in used:
                continue
            title_ratio = difflib.SequenceMatcher(
                None, old.title.lower(), new.title.lower()
            ).ratio()
            if title_ratio < TITLE_MATCH:
                continue
            text_ratio = difflib.SequenceMatcher(None, old.text.split(), new.text.split()).ratio()
            if text_ratio >= TEXT_MATCH and text_ratio > best_score:
                best, best_score = old, text_ratio
        if best is not None:
            matches[new.clause_id] = best.clause_id
            used.add(best.clause_id)
    return matches


def diff_clauses(old_clauses: list[Clause], new_clauses: list[Clause]) -> list[ClauseDiff]:
    old_by_id = {c.clause_id: c for c in old_clauses}
    new_by_id = {c.clause_id: c for c in new_clauses}

    old_left = [c for c in old_clauses if c.clause_id not in new_by_id]
    new_left = [c for c in new_clauses if c.clause_id not in old_by_id]
    renumbered = match_renumbered(old_left, new_left)
    matched_old = set(renumbered.values())

    results = []
    for new in new_clauses:
        old_id = new.clause_id if new.clause_id in old_by_id else renumbered.get(new.clause_id)
        if old_id is None:
            lines = normalized_lines(new.text)
            results.append(
                ClauseDiff(new.clause_id, None, new.title, "added", 0.0,
                           len(lines), 0, len(" ".join(lines).split()), "", new.text, "")
            )  # fmt: skip
            continue
        old = old_by_id[old_id]
        similarity, added, removed, words, diff = compare_texts(old.text, new.text)
        status = "unchanged" if not diff else "changed"
        results.append(
            ClauseDiff(new.clause_id, old_id, new.title, status, similarity,
                       added, removed, words, old.text, new.text, diff)
        )  # fmt: skip

    for old in old_left:
        if old.clause_id not in matched_old:
            lines = normalized_lines(old.text)
            results.append(
                ClauseDiff(old.clause_id, old.clause_id, old.title, "removed", 0.0,
                           0, len(lines), len(" ".join(lines).split()), old.text, "", "")
            )  # fmt: skip
    return results


def in_scope(clause_id: str, prefix: str) -> bool:
    """True if the clause is the prefix clause itself or one of its subclauses."""
    return not prefix or clause_id == prefix or clause_id.startswith(prefix + ".")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two releases of a spec clause by clause")
    parser.add_argument("spec", help="e.g. 38.300")
    parser.add_argument(
        "clause", nargs="?", default="", help="limit to this clause and its subclauses"
    )
    parser.add_argument("--old", default="Rel-17")
    parser.add_argument("--new", default="Rel-18")
    parser.add_argument("--show", action="store_true", help="print the diff of each changed clause")
    args = parser.parse_args()

    diffs = diff_clauses(load_clauses(args.spec, args.old), load_clauses(args.spec, args.new))
    diffs = [d for d in diffs if in_scope(d.clause_id, args.clause)]

    counts = {
        s: sum(1 for d in diffs if d.status == s)
        for s in ("added", "removed", "changed", "unchanged")
    }
    print(f"{args.spec} {args.old} -> {args.new} {args.clause}: {counts}\n")
    for d in diffs:
        if d.status == "unchanged":
            continue
        renumbered = (
            f" (was {d.old_clause_id})" if d.old_clause_id not in (None, d.clause_id) else ""
        )
        print(f"{d.status:8s} {d.clause_id:14s} {d.changed_words:6d} words  "
              f"{d.title[:60]}{renumbered}")  # fmt: skip
        if args.show and d.diff:
            print("    " + d.diff.replace("\n", "\n    ") + "\n")


if __name__ == "__main__":
    main()
