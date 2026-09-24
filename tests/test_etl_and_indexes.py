import pytest
from shapely.geometry import Point, shape
from scripts.etl_boundaries import (
    validate_and_normalize_geometry,
    compile_seed_data,
    generate_curated_seed_jurisdictions
)
from app.db import init_db_indexes


def test_geometry_validation_valid():
    """Verify that a standard valid GeoJSON polygon passes unchanged."""
    valid_box = {
        "type": "Polygon",
        "coordinates": [[[77.10, 28.50], [77.20, 28.50], [77.20, 28.60], [77.10, 28.60], [77.10, 28.50]]]
    }
    result = validate_and_normalize_geometry(valid_box)
    assert result["type"] == "Polygon"
    assert len(result["coordinates"][0]) == 5
    poly = shape(result)
    assert poly.is_valid


def test_geometry_validation_self_intersecting_bow_tie():
    """Verify that a self-intersecting 'bow-tie' polygon is repaired by make_valid."""
    bow_tie = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0], [0.0, 0.0]]]
    }
    result = validate_and_normalize_geometry(bow_tie)
    poly = shape(result)
    assert poly.is_valid
    assert poly.geom_type in ("Polygon", "MultiPolygon")


def test_generate_curated_seed_jurisdictions():
    """Verify that curated seed jurisdictions are generated with valid geometries and contacts."""
    jurisdictions = generate_curated_seed_jurisdictions()
    assert len(jurisdictions) >= 12  # At least 10 zones + NDMC + State bodies + NCR
    
    levels = {j["level"] for j in jurisdictions}
    assert "ward" in levels
    assert "district" in levels
    assert "state" in levels

    for j in jurisdictions:
        assert "@" in j["contact_email"], f"Invalid email in {j['name']}"
        assert len(j["categories"]) > 0
        poly = shape(j["geometry"])
        assert poly.is_valid, f"Invalid geometry in {j['name']}"


def test_spot_check_with_shapely():
    """Verify spot check coordinates accurately intersect expected zones using Shapely."""
    jurisdictions = generate_curated_seed_jurisdictions()
    
    test_cases = [
        {"name": "Karol Bagh Market", "coords": (77.190, 28.650), "expected_sub": "Karol Bagh"},
        {"name": "Connaught Place", "coords": (77.2167, 28.6315), "expected_sub": "NDMC"},
        {"name": "Rohini", "coords": (77.110, 28.720), "expected_sub": "Rohini"},
        {"name": "Noida Sec 18", "coords": (77.325, 28.570), "expected_sub": "Noida"},
        {"name": "Ghaziabad RDC", "coords": (77.440, 28.680), "expected_sub": "Ghaziabad"},
    ]

    for tc in test_cases:
        pt = Point(tc["coords"])
        matched = [j for j in jurisdictions if shape(j["geometry"]).contains(pt)]
        assert len(matched) > 0, f"No jurisdiction matched for {tc['name']} at {tc['coords']}"
        names = " ".join([m["name"] for m in matched])
        assert tc["expected_sub"] in names, f"{tc['expected_sub']} not found in matches: {names}"


def test_init_db_indexes(mock_db):
    """Verify that database indexes are properly declared on mock db."""
    indexes = init_db_indexes(mock_db)
    assert "reports" in indexes
    assert "users" in indexes
    assert "upvotes" in indexes
    assert "jurisdictions" in indexes
    assert "digest_log" in indexes
