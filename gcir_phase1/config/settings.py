"""
Central configuration for GCIR.

Per PRD §4: VERIFY_THRESHOLD must be configurable per pilot area (sparse
areas may never reach a fixed threshold). Per PRD §10: pilot area is not
yet fixed, so PILOT_AREA_NAME is a placeholder until boundary data
availability decides it.
"""
import os

# --- Database ---
MONGO_URI = os.environ.get("GCIR_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("GCIR_MONGO_DB", "gcir")

# --- Pilot area / verification ---
# PRD §10: Delhi MCD wards have a clean public-domain KML (250 wards).
# Noida/Greater Noida/Ghaziabad have no clean official boundary file yet.
# Default to Delhi until that's resolved.
PILOT_AREA_NAME = os.environ.get("GCIR_PILOT_AREA", "delhi")

VERIFY_THRESHOLD = int(os.environ.get("GCIR_VERIFY_THRESHOLD", "10"))

# Soft proximity check for upvotes (PRD §4) — flag, never block
UPVOTE_PROXIMITY_KM = float(os.environ.get("GCIR_UPVOTE_PROXIMITY_KM", "5"))

# Duplicate suggestion radius (PRD §6)
DUPLICATE_RADIUS_M = float(os.environ.get("GCIR_DUPLICATE_RADIUS_M", "200"))

# --- CRS ---
# All geometry stored in MongoDB must be WGS84 (EPSG:4326), GeoJSON
# order [lon, lat]. Source files vary; the ETL always reprojects to this.
TARGET_CRS = "EPSG:4326"

# --- Jurisdiction levels, most-specific-wins order (PRD §5.4) ---
JURISDICTION_LEVEL_PRIORITY = ["ward", "sector", "district", "state"]
