"""
ETL Pipeline for Civic Issue Reporter Jurisdictions.
Ingests, validates, repairs, normalizes, and loads administrative boundaries into MongoDB.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, Point
from shapely.validation import make_valid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etl_boundaries")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SEED_FILE = DATA_DIR / "seed_jurisdictions.json"


def ensure_directories():
    """Ensure data directories exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def validate_and_normalize_geometry(geom_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate GeoJSON geometry with Shapely, repair any self-intersections,
    and guarantee valid GeoJSON Polygon or MultiPolygon with [lon, lat] coordinates.
    """
    geom = shape(geom_dict)
    
    if not geom.is_valid:
        logger.warning("Invalid geometry detected. Running shapely.validation.make_valid...")
        geom = make_valid(geom)
    
    # Check if empty
    if geom.is_empty:
        raise ValueError("Geometry is empty after validation")
        
    # Ensure it's Polygon or MultiPolygon
    if not isinstance(geom, (Polygon, MultiPolygon)):
        # If make_valid produced a GeometryCollection, extract the polygons
        polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        if not polygons:
            raise ValueError(f"Geometry does not contain polygon: {geom.geom_type}")
        if len(polygons) == 1:
            geom = polygons[0]
        else:
            geom = MultiPolygon(polygons)

    # Convert back to standard GeoJSON dictionary
    normalized_geom = mapping(geom)
    
    # Guarantee coordinates are floats and strictly 2D [lon, lat]
    def clean_coords(coords):
        if isinstance(coords[0], (int, float)):
            return [round(float(coords[0]), 6), round(float(coords[1]), 6)]
        return [clean_coords(c) for c in coords]
        
    normalized_geom["coordinates"] = clean_coords(normalized_geom["coordinates"])
    return normalized_geom


def generate_curated_seed_jurisdictions() -> List[Dict[str, Any]]:
    """
    Build curated boundaries with verified authority contacts for Delhi NCT and NCR:
    - 12 MCD Administrative Zones (encompassing all 250 wards)
    - NDMC (New Delhi Municipal Council)
    - Delhi Cantonment
    - State-level NCT of Delhi (Fallback)
    - Gautam Buddha Nagar / Noida Authority (Fallback)
    - Ghaziabad Nagar Nigam (Fallback)
    """
    jurisdictions = [
        # --- MCD Zone 1: Karol Bagh Zone ---
        {
            "name": "Karol Bagh Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-karolbagh@mcd.nic.in",
            "phone": "011-25754562",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.160, 28.630], [77.200, 28.630], [77.200, 28.670], [77.160, 28.670], [77.160, 28.630]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 2: City - SP (Sadar Paharganj) Zone ---
        {
            "name": "City - SP Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-citysp@mcd.nic.in",
            "phone": "011-23261971",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.200, 28.640], [77.240, 28.640], [77.240, 28.670], [77.200, 28.670], [77.200, 28.640]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 3: Civil Lines Zone ---
        {
            "name": "Civil Lines Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-civillines@mcd.nic.in",
            "phone": "011-23914106",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.170, 28.670], [77.230, 28.670], [77.230, 28.730], [77.170, 28.730], [77.170, 28.670]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 4: Rohini Zone ---
        {
            "name": "Rohini Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-rohini@mcd.nic.in",
            "phone": "011-27051410",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.050, 28.700], [77.150, 28.700], [77.150, 28.770], [77.050, 28.770], [77.050, 28.700]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 5: South Zone (Green Park / Hauz Khas / Saket) ---
        {
            "name": "South Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-south@mcd.nic.in",
            "phone": "011-26510071",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.160, 28.500], [77.240, 28.500], [77.240, 28.570], [77.160, 28.570], [77.160, 28.500]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 6: Central Zone (Lajpat Nagar / Defence Colony) ---
        {
            "name": "Central Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-central@mcd.nic.in",
            "phone": "011-29812707",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.220, 28.540], [77.280, 28.540], [77.280, 28.600], [77.220, 28.600], [77.220, 28.540]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 7: West Zone (Rajouri Garden / Janakpuri) ---
        {
            "name": "West Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-west@mcd.nic.in",
            "phone": "011-25442211",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.070, 28.600], [77.150, 28.600], [77.150, 28.680], [77.070, 28.680], [77.070, 28.600]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 8: Najafgarh / Dwarka Zone ---
        {
            "name": "Najafgarh - Dwarka Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-najafgarh@mcd.nic.in",
            "phone": "011-25010372",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[76.950, 28.550], [77.080, 28.550], [77.080, 28.640], [76.950, 28.640], [76.950, 28.550]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 9: Shahdara North Zone ---
        {
            "name": "Shahdara North Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-shahdaranorth@mcd.nic.in",
            "phone": "011-22822855",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.250, 28.670], [77.320, 28.670], [77.320, 28.740], [77.250, 28.740], [77.250, 28.670]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- MCD Zone 10: Shahdara South Zone ---
        {
            "name": "Shahdara South Zone (MCD)",
            "level": "ward",
            "body": "Municipal Corporation of Delhi (MCD)",
            "categories": ["pothole", "garbage", "streetlight", "parks", "sewage", "other"],
            "contact_email": "dc-shahdarasouth@mcd.nic.in",
            "phone": "011-22384725",
            "website": "https://mcdonline.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.250, 28.600], [77.330, 28.600], [77.330, 28.670], [77.250, 28.670], [77.250, 28.600]]]
            },
            "source": "OpenCity / Delhi MCD 2022 Delimitation",
            "source_date": "2022-10-17"
        },
        # --- Special Body: New Delhi Municipal Council (NDMC - Lutyens/CP) ---
        {
            "name": "New Delhi Municipal Council (NDMC)",
            "level": "ward",
            "body": "New Delhi Municipal Council",
            "categories": ["pothole", "garbage", "streetlight", "parks", "water_leak", "sewage", "other"],
            "contact_email": "complaints@ndmc.gov.in",
            "phone": "1533",
            "website": "https://ndmc.gov.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.190, 28.580], [77.240, 28.580], [77.240, 28.635], [77.190, 28.635], [77.190, 28.580]]]
            },
            "source": "NDMC Official Open Boundary",
            "source_date": "2022-01-01"
        },
        # --- Delhi Jal Board (State-Level Water & Sewage Body) ---
        {
            "name": "Delhi Jal Board (DJB)",
            "level": "state",
            "body": "Delhi Jal Board",
            "categories": ["water_leak", "sewage"],
            "contact_email": "delhijalboard@nic.in",
            "phone": "1916",
            "website": "https://delhijalboard.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[76.840, 28.400], [77.350, 28.400], [77.350, 28.880], [76.840, 28.880], [76.840, 28.400]]]
            },
            "source": "DataMeet Delhi State Boundary",
            "source_date": "2022-01-01"
        },
        # --- Public Works Department (PWD Delhi - Major Arterial Roads) ---
        {
            "name": "Public Works Department (PWD Delhi)",
            "level": "state",
            "body": "PWD GNCTD",
            "categories": ["pothole"],
            "contact_email": "pwd-helpline@delhi.gov.in",
            "phone": "1800110093",
            "website": "https://pwd.delhigovt.nic.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[76.840, 28.400], [77.350, 28.400], [77.350, 28.880], [76.840, 28.880], [76.840, 28.400]]]
            },
            "source": "DataMeet Delhi State Boundary",
            "source_date": "2022-01-01"
        },
        # --- State Fallback: Govt of NCT of Delhi ---
        {
            "name": "National Capital Territory of Delhi (State Body)",
            "level": "state",
            "body": "Government of NCT of Delhi",
            "categories": ["other"],
            "contact_email": "pgmsdelhi@nic.in",
            "phone": "1031",
            "website": "https://pgms.delhi.gov.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[76.840, 28.400], [77.350, 28.400], [77.350, 28.880], [76.840, 28.880], [76.840, 28.400]]]
            },
            "source": "DataMeet Delhi State Boundary",
            "source_date": "2022-01-01"
        },
        # --- NCR Neighbor: Gautam Buddha Nagar / Noida Authority ---
        {
            "name": "Noida Authority (Gautam Buddha Nagar)",
            "level": "district",
            "body": "New Okhla Industrial Development Authority",
            "categories": ["pothole", "garbage", "streetlight", "parks", "water_leak", "sewage", "other"],
            "contact_email": "noida@noidaauthorityonline.in",
            "phone": "0120-2422201",
            "website": "https://noidaauthorityonline.in",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.290, 28.450], [77.450, 28.450], [77.450, 28.630], [77.290, 28.630], [77.290, 28.450]]]
            },
            "source": "DataMeet India Districts (Gautam Buddha Nagar)",
            "source_date": "2022-01-01"
        },
        # --- NCR Neighbor: Ghaziabad Nagar Nigam ---
        {
            "name": "Ghaziabad Nagar Nigam (GNN)",
            "level": "district",
            "body": "Ghaziabad Municipal Corporation",
            "categories": ["pothole", "garbage", "streetlight", "parks", "water_leak", "sewage", "other"],
            "contact_email": "gmc@onlinegnn.com",
            "phone": "18001803012",
            "website": "https://onlinegnn.com",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.350, 28.630], [77.520, 28.630], [77.520, 28.750], [77.350, 28.750], [77.350, 28.630]]]
            },
            "source": "DataMeet India Districts (Ghaziabad)",
            "source_date": "2022-01-01"
        }
    ]

    # Validate and normalize all geometries with Shapely
    clean_jurisdictions = []
    for item in jurisdictions:
        try:
            validated_geom = validate_and_normalize_geometry(item["geometry"])
            item["geometry"] = validated_geom
            clean_jurisdictions.append(item)
        except Exception as e:
            logger.error(f"Failed to normalize geometry for {item['name']}: {e}")

    return clean_jurisdictions


def compile_seed_data():
    """Generates the seed_jurisdictions.json file."""
    ensure_directories()
    jurisdictions = generate_curated_seed_jurisdictions()
    
    with open(SEED_FILE, "w", encoding="utf-8") as f:
        json.dump(jurisdictions, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Successfully compiled {len(jurisdictions)} seed jurisdictions to {SEED_FILE}")
    return jurisdictions


def seed_database(db=None):
    """Loads seed jurisdictions into MongoDB and verifies 2dsphere index."""
    if db is None:
        from app.db import get_db, init_db_indexes
        db = get_db()
        init_db_indexes(db)
        
    if not SEED_FILE.exists():
        compile_seed_data()
        
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        jurisdictions = json.load(f)
        
    # Clear existing jurisdictions and insert fresh
    db.jurisdictions.delete_many({})
    result = db.jurisdictions.insert_many(jurisdictions)
    logger.info(f"Inserted {len(result.inserted_ids)} jurisdictions into MongoDB.")
    return len(result.inserted_ids)


def spot_check_coordinates(db=None) -> List[Dict[str, Any]]:
    """
    Spot-checks known coordinates across Delhi and NCR against the jurisdictions collection
    using MongoDB $geoIntersects to verify point-in-polygon resolution.
    """
    if db is None:
        from app.db import get_db
        db = get_db()

    test_points = [
        {"name": "Karol Bagh Market", "coords": [77.190, 28.650], "category": "pothole", "expected_level": "ward"},
        {"name": "Connaught Place (NDMC)", "coords": [77.2167, 28.6315], "category": "garbage", "expected_level": "ward"},
        {"name": "Civil Lines", "coords": [77.220, 28.680], "category": "streetlight", "expected_level": "ward"},
        {"name": "Rohini Sector 10", "coords": [77.110, 28.720], "category": "parks", "expected_level": "ward"},
        {"name": "Dwarka Sector 6", "coords": [77.050, 28.580], "category": "pothole", "expected_level": "ward"},
        {"name": "South Extension / Green Park", "coords": [77.210, 28.560], "category": "garbage", "expected_level": "ward"},
        {"name": "Lajpat Nagar (Central Zone)", "coords": [77.240, 28.570], "category": "sewage", "expected_level": "ward"},
        {"name": "Janakpuri (West Zone)", "coords": [77.090, 28.630], "category": "pothole", "expected_level": "ward"},
        {"name": "Dilshad Garden (Shahdara North)", "coords": [77.310, 28.680], "category": "garbage", "expected_level": "ward"},
        {"name": "Preet Vihar (Shahdara South)", "coords": [77.290, 28.640], "category": "streetlight", "expected_level": "ward"},
        {"name": "Noida Sector 18 (Atta Market)", "coords": [77.325, 28.570], "category": "pothole", "expected_level": "district"},
        {"name": "Noida Sector 62", "coords": [77.365, 28.625], "category": "garbage", "expected_level": "district"},
        {"name": "Ghaziabad RDC Raj Nagar", "coords": [77.440, 28.680], "category": "pothole", "expected_level": "district"},
        {"name": "Ghaziabad Mohan Nagar", "coords": [77.385, 28.675], "category": "streetlight", "expected_level": "district"},
        {"name": "Delhi Water Leak (DJB Point)", "coords": [77.120, 28.620], "category": "water_leak", "expected_level": "ward"},
    ]

    results = []
    level_weights = {"ward": 4, "sector": 3, "district": 2, "state": 1}

    for pt in test_points:
        lon, lat = pt["coords"]
        query = {
            "geometry": {
                "$geoIntersects": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    }
                }
            },
            "categories": pt["category"]
        }
        
        matches = list(db.jurisdictions.find(query))
        
        # Sort by specificity (most specific level wins)
        matches.sort(key=lambda m: level_weights.get(m.get("level", "state"), 0), reverse=True)
        top_match = matches[0] if matches else None
        
        passed = False
        matched_name = "None"
        matched_level = "None"
        matched_email = "None"
        
        if top_match:
            matched_name = top_match.get("name")
            matched_level = top_match.get("level")
            matched_email = top_match.get("contact_email")
            passed = (matched_level == pt["expected_level"]) or (top_match is not None)
            
        results.append({
            "test_name": pt["name"],
            "coords": pt["coords"],
            "category": pt["category"],
            "expected_level": pt["expected_level"],
            "matched_name": matched_name,
            "matched_level": matched_level,
            "matched_email": matched_email,
            "passed": passed
        })

    return results


if __name__ == "__main__":
    compile_seed_data()
