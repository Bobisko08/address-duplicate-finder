# Address Duplicate Finder

A Python tool that finds duplicate customer addresses in a large CSV export and sorts them into groups a business team can actually review.

I built the original version during my IT internship at a logistics company, where the customer address table had around 250,000 records. This repository is a clean rewrite of the same idea with invented sample data. It contains no company code or data.

## The problem

A first, simple version that matched on address alone flagged more than 10,000 records as possible duplicates. That was technically correct but useless: nobody can review 10,000 rows, and many of them were different companies sharing one office building.

After talking to the people who would use the results, I changed the approach:

1. **Normalise** every address (case, punctuation, `Road`/`Rd`, `Strasse`/`Str.`) so small typing differences don't hide a match.
2. **Group** records by normalised street address and, separately, by P.O. Box.
3. Inside each group, **compare company names** after removing legal words such as `Ltd`, `GmbH` or `Inc`, using a similarity score (`difflib.SequenceMatcher`). Only records with the same or very similar names count as duplicates.
4. **Split the output into categories**: high-confidence duplicates (identical names), medium-confidence ones (similar names), shared addresses with different companies (not duplicates), and records with no usable address.
5. **Suggest which record to keep** in each group: verified first, then the most complete record, then the oldest id.

In the real data this brought the list down to around 1,200 exact duplicates the team could clean up first, with the rest grouped by type for later review.

## Run it

Requires Python 3.10 or newer. No third-party packages are needed.

```bash
python generate_sample_data.py          # creates sample_data/addresses.csv (fake data)
python dedup.py sample_data/addresses.csv --out output
```

Output files in `output/`:

| File | Contents |
|------|----------|
| `duplicates.csv` | Every duplicate group, with a KEEP or REVIEW_FOR_DELETION suggestion per record |
| `shared_address_different_names.csv` | Same address, different companies, so not duplicates |
| `no_usable_address.csv` | Records with no street address or P.O. Box |
| `summary.md` | Counts for each category |

Change how strict name matching is with `--threshold` (default 0.88).

## Tests

```bash
pip install pytest
pytest
```

## What I learned

- A correct result is not automatically a useful one. The biggest improvement came from asking how the team would use the output, not from changing the matching code.
- Normalising data before comparing it removes most false negatives.
- Splitting results by confidence lets people act on the safe cases straight away.
