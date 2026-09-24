"""
ETL: raw boundary files (DataMeet shapefiles, Opencity Delhi MCD wards KML)
-> validated GeoJSON -> MongoDB `jurisdictions` collection.

PRD §10 data sources:
  - DataMeet India boundaries (shapefile, CC BY 4.0) — state/district/
    sub-district level, fallback jurisdictions. Attribute DataMeet.
  - Delhi MCD wards (Opencity 2022 KML, 250 wards, public domain).
  - Noida/Greater Noida/Ghaziabad: no clean official file yet (not
    handled by this script — see README "Open item").

Usage:
    python -m etl.load_jurisdictions \\
        --input data/raw/delhi_mcd_wards.kml \\
        --source-type delhi_wards \\
        --level ward \\
        --categories pothole,garbage,water_leak \\
        --contacts data/raw/ward_contacts.csv \\
        --source "Opencity 2022" \\
        --source-date 2022-01-01

    python -m etl.load_jurisdictions \\
        --input data/raw/datameet_districts.shp \\
        --source-type datameet \\
        --level district \\
        --categories pothole,garbage,water_leak \\
        --source "DataMeet India boundaries (CC BY 4.0)" \\
        --source-date 2011-01-01 \\
        --dry-run
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import geopandas as gpd
from pymongo.errors import BulkWriteError

from config.settings import TARGET_CRS
from db.connection import get_db
from etl.validate import drop_empty_and_null, validate_and_repair

# Column-name candidates per source, in priority order. Real shapefiles/
# KMLs are inconsistent about capitalization and abbreviation, so we
# search a short candidate list rather than hardcode one name.
NAME_FIELD_CANDIDATES = {
    "datameet": ["NAME", "DISTRICT", "district", "name", "Name"],
    "delhi_wards": ["Name", "WARD_NAME", "ward_name", "name"],
}


def load_source(input_path: str, source_type: str) -> gpd.GeoDataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{input_path} not found. Raw boundary files aren't bundled with "
            f"this repo (see PRD §10) — download them into data/raw/ first."
        )

    if path.suffix.lower() == ".kml":
        gdf = gpd.read_file(path, driver="KML")
    else:
        gdf = gpd.read_file(path)

    if gdf.crs is None:
        raise ValueError(
            f"{input_path} has no CRS defined — can't safely reproject. "
            f"Set it manually (gdf.set_crs(...)) once you've confirmed the "
            f"source CRS from its metadata."
        )
    return gdf


def find_name_column(gdf: gpd.GeoDataFrame, source_type: str) -> str:
    candidates = NAME_FIELD_CANDIDATES.get(source_type, [])
    for col in candidates:
        if col in gdf.columns:
            return col
    raise ValueError(
        f"No name column found for source_type={source_type!r}. "
        f"Available columns: {list(gdf.columns)}. "
        f"Add the right one to NAME_FIELD_CANDIDATES."
    )


def load_contacts(contacts_csv: str | None) -> dict:
    """
    Hand-built authority contact table (PRD §10). CSV columns expected:
    jurisdiction_name, body, contact_email
    Returns {jurisdiction_name: {"body": ..., "contact_email": ...}}.
    """
    if not contacts_csv:
        return {}
    contacts = {}
    with open(contacts_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            contacts[row["jurisdiction_name"].strip()] = {
                "body": row.get("body", "").strip(),
                "contact_email": row.get("contact_email", "").strip(),
            }
    return contacts


def build_documents(
    gdf: gpd.GeoDataFrame,
    source_type: str,
    level: str,
    categories: list[str],
    source: str,
    source_date: str,
    contacts: dict,
) -> list[dict]:
    name_col = find_name_column(gdf, source_type)
    docs = []
    missing_contact = []

    for _, row in gdf.iterrows():
        name = str(row[name_col]).strip()
        contact = contacts.get(name, {})
        body = contact.get("body") or ""
        contact_email = contact.get("contact_email") or ""
        if not contact_email:
            missing_contact.append(name)

        geom = json.loads(gpd.GeoSeries([row.geometry]).to_json())["features"][0]["geometry"]

        docs.append(
            {
                "name": name,
                "level": level,
                "body": body,
                "categories": categories,
                "contact_email": contact_email,
                "geometry": geom,
                "source": source,
                "source_date": source_date,
            }
        )

    if missing_contact:
        print(
            f"  WARNING: {len(missing_contact)} jurisdiction(s) have no contact_email "
            f"(complaint drafter will show 'no direct contact found', per PRD §5.4). "
            f"First few: {missing_contact[:5]}"
        )

    return docs


def run(
    input_path: str,
    source_type: str,
    level: str,
    categories: list[str],
    source: str,
    source_date: str,
    contacts_csv: str | None,
    dry_run: bool,
) -> None:
    print(f"[1/5] Reading {input_path} ({source_type})...")
    gdf = load_source(input_path, source_type)
    print(f"  {len(gdf)} feature(s) loaded, source CRS = {gdf.crs}")

    print(f"[2/5] Reprojecting to {TARGET_CRS}...")
    gdf = gdf.to_crs(TARGET_CRS)

    print("[3/5] Validating geometries...")
    gdf = drop_empty_and_null(gdf)
    gdf, result = validate_and_repair(gdf)
    print(
        f"  total={result.total} invalid_before={result.invalid_before} "
        f"repaired={result.repaired} still_invalid={result.still_invalid}"
    )
    if result.still_invalid:
        print(f"  ABORTING: unrepairable geometries at rows {result.still_invalid_rows}. "
              f"Fix the source file or exclude these rows and re-run.")
        sys.exit(1)

    print("[4/5] Building jurisdiction documents...")
    contacts = load_contacts(contacts_csv)
    docs = build_documents(gdf, source_type, level, categories, source, source_date, contacts)

    if dry_run:
        print(f"[5/5] DRY RUN — would insert {len(docs)} document(s). Sample:")
        print(json.dumps(docs[0], indent=2)[:800] if docs else "  (none)")
        return

    print(f"[5/5] Inserting {len(docs)} document(s) into MongoDB jurisdictions...")
    db = get_db()
    try:
        result = db.jurisdictions.insert_many(docs, ordered=False)
        print(f"  inserted {len(result.inserted_ids)} document(s)")
    except BulkWriteError as e:
        # 2dsphere rejects invalid GeoJSON at insert time even after our
        # own validation pass — surface exactly which ones failed.
        write_errors = e.details.get("writeErrors", [])
        print(f"  {len(write_errors)} document(s) FAILED to insert:")
        for err in write_errors[:10]:
            print(f"    index {err['index']}: {err['errmsg']}")
        raise


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="Path to shapefile (.shp) or KML (.kml)")
    p.add_argument("--source-type", required=True, choices=list(NAME_FIELD_CANDIDATES.keys()))
    p.add_argument("--level", required=True, choices=["ward", "sector", "district", "state"])
    p.add_argument("--categories", required=True, help="Comma-separated, e.g. pothole,garbage,water_leak")
    p.add_argument("--source", required=True, help='Attribution string, e.g. "DataMeet India boundaries (CC BY 4.0)"')
    p.add_argument("--source-date", required=True, help="ISO date, e.g. 2022-01-01")
    p.add_argument("--contacts", default=None, help="CSV: jurisdiction_name,body,contact_email")
    p.add_argument("--dry-run", action="store_true", help="Validate and print sample without writing to MongoDB")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        input_path=args.input,
        source_type=args.source_type,
        level=args.level,
        categories=[c.strip() for c in args.categories.split(",")],
        source=args.source,
        source_date=args.source_date,
        contacts_csv=args.contacts,
        dry_run=args.dry_run,
    )
