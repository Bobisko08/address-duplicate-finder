import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dedup import clean, clean_name, find_duplicates, name_similarity  # noqa: E402


def record(id_, name, street="Harbour Road 5", postcode="20457", city="Hamburg", country="DE", **extra):
    row = {"id": id_, "name": name, "street": street, "postcode": postcode, "city": city,
           "country": country, "pobox": "", "pobox_postcode": "", "status": "ACTIVE"}
    row.update(extra)
    return row


def test_clean_unifies_street_words():
    assert clean("Harbour Road 5") == clean("harbour rd. 5")
    assert clean("Kaistrasse 3") == clean("Kaistr. 3")


def test_legal_words_are_ignored_in_names():
    assert clean_name("Atlas Freight Ltd") == clean_name("ATLAS FREIGHT LIMITED")
    assert name_similarity("Atlas Freight Ltd", "Atlas Freight GmbH") == 1.0


def test_same_name_same_address_is_high_confidence_duplicate():
    result = find_duplicates([record("1", "Atlas Freight Ltd"), record("2", "ATLAS FREIGHT LIMITED", street="Harbour Rd 5")])
    assert len(result.duplicates) == 1
    assert result.duplicates[0].confidence == "HIGH"


def test_different_companies_in_same_building_are_not_duplicates():
    result = find_duplicates([record("1", "Atlas Freight Ltd"), record("2", "Blue Textiles BV")])
    assert result.duplicates == []
    assert len(result.shared_address_different_names) == 1


def test_records_without_address_are_reported():
    result = find_duplicates([record("1", "Atlas Freight Ltd", street="", postcode="")])
    assert len(result.no_usable_address) == 1


def test_verified_record_is_kept():
    rows = [record("1", "Atlas Freight Ltd", status="ACTIVE"), record("2", "Atlas Freight Ltd", status="VERIFIED")]
    assert find_duplicates(rows).duplicates[0].keep_id == "2"
