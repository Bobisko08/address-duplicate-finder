"""Find duplicate customer addresses in a CSV export.

Two records are treated as duplicates when they share the same normalised
address (country, postcode, city, street) or the same P.O. Box, AND their
company names are the same or very similar. Records that share an address
but have clearly different names (for example two companies in the same
office building) are reported separately instead of being flagged.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

# Words that say nothing about which company it is, so they are ignored
# when comparing names ("Acme Ltd" and "ACME Limited" are the same company).
LEGAL_WORDS = {
    "GMBH", "LTD", "LIMITED", "INC", "CORP", "CORPORATION", "CO", "COMPANY",
    "BV", "NV", "SA", "SAS", "SPA", "SRL", "LLC", "PLC", "KG", "AG", "AS",
    "AB", "OY", "PTE", "PTY", "THE", "AND",
}

STREET_ABBREVIATIONS = [
    (r"STRASSE\b", "STR"),
    (r"\bSTREET\b", "ST"),
    (r"\bROAD\b", "RD"),
    (r"\bAVENUE\b", "AVE"),
]

DEFAULT_SIMILARITY = 0.88

STATUS_RANK = {"VERIFIED": 3, "ACTIVE": 2, "UNKNOWN": 1}


def clean(value: object) -> str:
    """Upper-case, strip punctuation and unify common street abbreviations."""
    text = "" if value is None else str(value)
    text = text.upper().replace("&", " AND ").replace("ß", "SS")
    text = re.sub(r"[.,;:()\[\]{}'\"`/\\_-]", " ", text)
    for pattern, replacement in STREET_ABBREVIATIONS:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: object) -> str:
    """Letters and digits only, so '12-14' and '12 14' compare equal."""
    return re.sub(r"[^A-Z0-9]", "", clean(value))


def clean_name(value: object) -> str:
    return " ".join(word for word in clean(value).split() if word not in LEGAL_WORDS)


def name_similarity(left: object, right: object) -> float:
    a, b = clean_name(left), clean_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def has_street_address(row: dict) -> bool:
    return bool(compact(row.get("street")) and (compact(row.get("postcode")) or clean(row.get("city"))))


def has_pobox(row: dict) -> bool:
    return bool(compact(row.get("pobox")) and (compact(row.get("pobox_postcode")) or clean(row.get("city"))))


def street_key(row: dict) -> tuple:
    return (clean(row.get("country")), compact(row.get("postcode")), clean(row.get("city")), compact(row.get("street")))


def pobox_key(row: dict) -> tuple:
    return (clean(row.get("country")), compact(row.get("pobox_postcode")), clean(row.get("city")), compact(row.get("pobox")))


def group_similar_names(rows: list[dict], threshold: float) -> list[list[dict]]:
    """Split rows that share an address into groups of similar company names."""
    groups: list[list[dict]] = []
    for row in rows:
        for group in groups:
            if any(name_similarity(row.get("name"), other.get("name")) >= threshold for other in group):
                group.append(row)
                break
        else:
            groups.append([row])
    return [group for group in groups if len(group) > 1]


def choose_record_to_keep(rows: list[dict]) -> dict:
    """Prefer verified records, then the most complete one, then the oldest id."""
    def score(row: dict):
        status = STATUS_RANK.get(clean(row.get("status")), 0)
        filled = sum(1 for value in row.values() if str(value or "").strip())
        number = int(re.sub(r"\D", "", str(row.get("id", ""))) or 10**9)
        return (-status, -filled, number)

    return sorted(rows, key=score)[0]


@dataclass
class DuplicateGroup:
    group_id: str
    category: str
    confidence: str
    keep_id: str
    rows: list[dict]


@dataclass
class Result:
    duplicates: list[DuplicateGroup] = field(default_factory=list)
    shared_address_different_names: list[list[dict]] = field(default_factory=list)
    no_usable_address: list[dict] = field(default_factory=list)
    total_rows: int = 0

    @property
    def rows_to_review(self) -> int:
        return sum(len(group.rows) - 1 for group in self.duplicates)


def find_duplicates(rows: list[dict], threshold: float = DEFAULT_SIMILARITY) -> Result:
    result = Result(total_rows=len(rows))
    by_street: dict[tuple, list[dict]] = defaultdict(list)
    by_pobox: dict[tuple, list[dict]] = defaultdict(list)

    for row in rows:
        street, pobox = has_street_address(row), has_pobox(row)
        if not street and not pobox:
            result.no_usable_address.append(row)
        if street:
            by_street[street_key(row)].append(row)
        if pobox:
            by_pobox[pobox_key(row)].append(row)

    counter = 0
    for label, buckets in (("SAME_STREET_ADDRESS", by_street), ("SAME_PO_BOX", by_pobox)):
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            similar = group_similar_names(bucket, threshold)
            for group in similar:
                counter += 1
                same_name = len({clean_name(r.get("name")) for r in group}) == 1
                result.duplicates.append(DuplicateGroup(
                    group_id=f"DUP-{counter:05d}",
                    category=label,
                    confidence="HIGH" if same_name else "MEDIUM",
                    keep_id=choose_record_to_keep(group)["id"],
                    rows=group,
                ))
            if label == "SAME_STREET_ADDRESS":
                grouped = {id(r) for g in similar for r in g}
                leftovers = [r for r in bucket if id(r) not in grouped]
                if len(leftovers) > 1:
                    result.shared_address_different_names.append(leftovers)
    return result


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_reports(result: Result, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    dup_path = out_dir / "duplicates.csv"
    with dup_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group_id", "category", "confidence", "recommendation", "id", "name", "street", "postcode", "city", "country", "pobox", "status"])
        for group in result.duplicates:
            for row in group.rows:
                action = "KEEP" if row["id"] == group.keep_id else "REVIEW_FOR_DELETION"
                writer.writerow([group.group_id, group.category, group.confidence, action, row.get("id"), row.get("name"),
                                 row.get("street"), row.get("postcode"), row.get("city"), row.get("country"), row.get("pobox"), row.get("status")])
    written.append(dup_path)

    shared_path = out_dir / "shared_address_different_names.csv"
    with shared_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["shared_group", "id", "name", "street", "postcode", "city", "country"])
        for number, group in enumerate(result.shared_address_different_names, 1):
            for row in group:
                writer.writerow([f"SHARED-{number:05d}", row.get("id"), row.get("name"), row.get("street"), row.get("postcode"), row.get("city"), row.get("country")])
    written.append(shared_path)

    missing_path = out_dir / "no_usable_address.csv"
    with missing_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "city", "country"])
        for row in result.no_usable_address:
            writer.writerow([row.get("id"), row.get("name"), row.get("city"), row.get("country")])
    written.append(missing_path)

    high = sum(1 for g in result.duplicates if g.confidence == "HIGH")
    summary = out_dir / "summary.md"
    summary.write_text(
        "# Address duplicate check\n\n"
        f"- Records checked: {result.total_rows}\n"
        f"- Duplicate groups: {len(result.duplicates)} ({high} high confidence, {len(result.duplicates) - high} medium)\n"
        f"- Records to review for deletion: {result.rows_to_review}\n"
        f"- Shared addresses with different company names (not duplicates): {len(result.shared_address_different_names)} groups\n"
        f"- Records without a usable address: {len(result.no_usable_address)}\n",
        encoding="utf-8",
    )
    written.append(summary)
    return written


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="CSV file with address records")
    parser.add_argument("--out", type=Path, default=Path("output"), help="folder for the reports")
    parser.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY, help="name similarity needed (0-1)")
    args = parser.parse_args()

    result = find_duplicates(read_csv(args.input), args.threshold)
    for path in write_reports(result, args.out):
        print(f"wrote {path}")
    print((args.out / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
