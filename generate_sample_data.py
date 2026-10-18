"""Create a fake address export with planted duplicates for trying the tool.

All company names and addresses are invented.
"""

import csv
import random
from pathlib import Path

FIELDS = ["id", "name", "street", "postcode", "city", "country", "pobox", "pobox_postcode", "status"]

PREFIXES = ["North", "Blue", "Harbour", "Atlas", "Delta", "Summit", "Bright", "Iron", "Silver", "Green", "Coastal", "Union"]
NOUNS = ["Freight", "Trading", "Logistics", "Cargo", "Supplies", "Imports", "Marine", "Foods", "Textiles", "Steel"]
SUFFIXES = ["Ltd", "GmbH", "BV", "Inc", "Limited", "Ltd.", "SA"]
STREETS = ["Harbour Road", "Market Street", "Mill Lane", "Station Avenue", "Kaistrasse", "Dock Road", "High Street",
           "Canal Street", "Quay Road", "Bridge Street", "Hafenstrasse", "Park Avenue", "Church Lane", "Ferry Road"]
CITIES = [("Hamburg", "DE", "20457"), ("Rotterdam", "NL", "3011"), ("Cardiff", "GB", "CF10"), ("Antwerp", "BE", "2000"), ("Izmir", "TR", "35210")]


def company_name(rng: random.Random) -> str:
    return f"{rng.choice(PREFIXES)} {rng.choice(NOUNS)} {rng.choice(SUFFIXES)}"


def make_record(rng: random.Random, record_id: int) -> dict:
    city, country, postcode = rng.choice(CITIES)
    return {
        "id": f"A{record_id:06d}",
        "name": company_name(rng),
        "street": f"{rng.choice(STREETS)} {rng.randint(1, 400)}",
        "postcode": postcode,
        "city": city,
        "country": country,
        "pobox": "",
        "pobox_postcode": "",
        "status": rng.choice(["ACTIVE", "ACTIVE", "VERIFIED", "UNKNOWN"]),
    }


def messy_copy(rng: random.Random, row: dict, new_id: int) -> dict:
    """Same company and address, typed slightly differently."""
    copy = dict(row, id=f"A{new_id:06d}", status=rng.choice(["ACTIVE", "UNKNOWN"]))
    name = row["name"]
    variants = [name.upper(), name.replace("Ltd", "Limited"), name.replace(" ", "  "), name.rstrip(".") + ".", name.replace("Logistics", "Logistic")]
    copy["name"] = rng.choice(variants)
    copy["street"] = row["street"].replace("Road", "Rd").replace("Street", "St.").replace("strasse", "str.")
    return copy


def generate(count: int = 2000, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = [make_record(rng, i) for i in range(1, count + 1)]
    next_id = count + 1

    for row in rng.sample(rows, k=count // 20):          # real duplicates
        rows.append(messy_copy(rng, row, next_id))
        next_id += 1

    for row in rng.sample(rows, k=count // 50):          # different firms, same building
        neighbour = dict(row, id=f"A{next_id:06d}", name=company_name(rng))
        rows.append(neighbour)
        next_id += 1

    for row in rng.sample(rows, k=count // 100):         # records with no usable address
        row.update(street="", postcode="", pobox="")

    rng.shuffle(rows)
    return rows


if __name__ == "__main__":
    out = Path("sample_data/addresses.csv")
    out.parent.mkdir(exist_ok=True)
    data = generate()
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    print(f"wrote {len(data)} records to {out}")
