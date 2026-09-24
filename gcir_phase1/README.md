# GCIR — Phase 1 (Week 1: ETL, jurisdictions, schema)

Scaffolding for the "ETL, jurisdictions, schema" milestone in the PRD's
Week 1 deliverable. Nothing here talks to Flask yet — that's Week 2.

## What's here

```
config/settings.py        - env-driven config (Mongo URI, VERIFY_THRESHOLD, CRS)
db/connection.py          - single get_db() the rest of the app will import
db/init_schema.py         - creates all indexes from PRD §8 (run once)
etl/validate.py           - geometry validation/repair (make_valid), unit-tested
etl/load_jurisdictions.py - CLI: shapefile/KML -> validated GeoJSON -> jurisdictions
tests/test_validate.py    - synthetic-geometry tests (passing, no real data needed)
data/raw/                 - put downloaded boundary files + contact CSVs here
```

## Setup

```bash
pip install -r requirements.txt
export GCIR_MONGO_URI="mongodb+srv://..."   # Atlas connection string
python -m db.init_schema
```

## Running the ETL

You'll need to download the source files yourself — they're not bundled
(and this environment's network is locked to package registries, so I
couldn't fetch them for you):

- **DataMeet India boundaries** — shapefiles, CC BY 4.0.
- **Delhi MCD wards** — Opencity 2022 KML, 250 wards, public domain.

Once a file is in `data/raw/`:

```bash
python -m etl.load_jurisdictions \
  --input data/raw/delhi_mcd_wards.kml \
  --source-type delhi_wards \
  --level ward \
  --categories pothole,garbage,water_leak \
  --contacts data/raw/ward_contacts.csv \
  --source "Opencity 2022" \
  --source-date 2022-01-01 \
  --dry-run     # drop this flag once the sample doc looks right
```

`--contacts` is optional but per PRD §10 the authority contact table is
hand-built — start from `data/raw/ward_contacts_template.csv` and fill in
`jurisdiction_name,body,contact_email` rows as you find them. Any
jurisdiction without a contact_email still loads fine; it'll just surface
the "no direct contact found" fallback in the complaint drafter (§5.4).

The script validates every geometry (`shapely.make_valid`), reprojects to
EPSG:4326, and **aborts before writing anything** if a geometry can't be
repaired — better to fix the source file than insert something the
2dsphere index will silently choke on later.

## Verified this phase

- `pytest tests/` — 4/4 passing (valid/invalid/empty/mixed geometry cases)
- Full CLI dry-run smoke-tested against a synthetic 3-ward KML — reprojects,
  validates, flags missing contacts, prints a correct sample GeoJSON doc

## Open items carried from the PRD (§10)

1. **Pilot area isn't fixed yet.** Delhi has a clean ward file; Noida/
   Greater Noida/Ghaziabad don't. `config/settings.PILOT_AREA_NAME`
   defaults to `"delhi"` — override via `GCIR_PILOT_AREA` once decided.
2. **`--source-type` only knows `datameet` and `delhi_wards`.** If you
   end up digitizing Noida/Ghaziabad sectors by hand, add a name-column
   entry to `NAME_FIELD_CANDIDATES` in `load_jurisdictions.py` first.
3. **No real boundary files were run through the pipeline** — only the
   synthetic smoke test above. First real run should use `--dry-run` and
   eyeball the sample doc before dropping the flag.

## Next (Week 2 per PRD milestones)

Auth, report posting, image upload.
