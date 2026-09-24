import pytest
from app.ml.clustering import compute_dbscan_hotspots
from app.ml.duplicates import compute_text_similarity, check_potential_duplicate
from app.reports.services import create_report
from app.auth.models import User


def test_text_similarity_identical_and_different():
    s1 = "Massive dangerous pothole right after Karol Bagh metro pillar 120"
    s2 = "Huge pothole and crater in road near pillar 120 Karol Bagh"
    sim_high = compute_text_similarity(s1, s2)
    assert sim_high > 0.15

    s3 = "Broken park bench in South Extension garden"
    sim_low = compute_text_similarity(s1, s3)
    assert sim_low < 0.10


def test_dbscan_clustering(mock_db):
    author = User.create(name="Author", email="cluster@example.com", password="pwd", db=mock_db)
    
    # Create 3 reports tightly clustered in Karol Bagh (within ~100m)
    r1 = create_report(author.id, "pothole", "Pothole near pillar 120", "url", [77.1900, 28.6500], db=mock_db)
    r2 = create_report(author.id, "pothole", "Pothole near pillar 121", "url", [77.1904, 28.6502], db=mock_db)
    r3 = create_report(author.id, "pothole", "Pothole near pillar 122", "url", [77.1908, 28.6505], db=mock_db)

    # Create 1 isolated report 15km away in Dwarka
    r4 = create_report(author.id, "pothole", "Pothole in Dwarka", "url", [77.0500, 28.5800], db=mock_db)

    clusters = compute_dbscan_hotspots(eps_km=0.5, min_samples=3, db=mock_db)
    assert len(clusters) == 1
    assert clusters[0]["size"] == 3
    assert clusters[0]["categories"]["pothole"] == 3

    # Check database updated cluster_ids
    doc1 = mock_db.reports.find_one({"_id": r1["_id"]})
    doc4 = mock_db.reports.find_one({"_id": r4["_id"]})
    assert doc1["cluster_id"] == 0
    assert doc4["cluster_id"] is None  # Noise point
