import pytest
from app.complaints.router import lookup_authority_for_point
from scripts.etl_boundaries import seed_database, generate_curated_seed_jurisdictions


def test_authority_router_karol_bagh(mock_db):
    seed_database(mock_db)
    # Coordinates inside Karol Bagh zone: [77.190, 28.650]
    auth = lookup_authority_for_point(77.190, 28.650, "pothole", db=mock_db)
    assert "Karol Bagh" in auth["name"]
    assert auth["level"] == "ward"
    assert "dc-karolbagh@mcd.nic.in" == auth["contact_email"]
    assert auth["is_fallback"] is False


def test_authority_router_ndmc(mock_db):
    seed_database(mock_db)
    # Connaught Place inside NDMC: [77.2167, 28.6315]
    auth = lookup_authority_for_point(77.2167, 28.6315, "garbage", db=mock_db)
    assert "New Delhi Municipal Council" in auth["name"]
    assert "complaints@ndmc.gov.in" == auth["contact_email"]


def test_authority_router_noida(mock_db):
    seed_database(mock_db)
    # Noida Sector 18: [77.325, 28.570]
    auth = lookup_authority_for_point(77.325, 28.570, "pothole", db=mock_db)
    assert "Noida Authority" in auth["name"]
    assert auth["level"] == "district"
    assert "noida@noidaauthorityonline.in" == auth["contact_email"]


def test_authority_router_ghaziabad(mock_db):
    seed_database(mock_db)
    # Ghaziabad RDC: [77.440, 28.680]
    auth = lookup_authority_for_point(77.440, 28.680, "garbage", db=mock_db)
    assert "Ghaziabad Nagar Nigam" in auth["name"]
    assert "gmc@onlinegnn.com" == auth["contact_email"]


def test_authority_router_fallback(mock_db):
    seed_database(mock_db)
    # Point outside city bounds: [80.0, 30.0]
    auth = lookup_authority_for_point(80.0, 30.0, "pothole", db=mock_db)
    assert auth["level"] == "state"
    assert auth["is_fallback"] is True
