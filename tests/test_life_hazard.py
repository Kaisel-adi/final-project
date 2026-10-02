import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.reports.services import create_report
from app.services.emergency import (
    check_and_escalate_life_hazards,
    get_emergency_authority,
    send_emergency_dispatch,
    EMERGENCY_SERVICES
)
from app.feed.routes import fetch_feed_reports, build_feed_match_query
from app.auth.models import User
from app import create_app
from app.config import TestConfig


def test_emergency_services_directory_completeness():
    """Verifies that all 6 critical emergency services are properly configured with their official dial numbers."""
    numbers = {s["service"]: s["number"] for s in EMERGENCY_SERVICES}
    assert numbers["POLICE"] == "112"
    assert numbers["FIRE"] == "101"
    assert numbers["AMBULANCE"] == "102"
    assert numbers["Children In Difficult Situation"] == "1098"
    assert numbers["LPG Leak Helpline"] == "1906"
    assert numbers["Disaster Management Services"] == "108"


def test_minimal_form_life_hazard_description_optional(mock_db):
    """Someone in danger won't fill out fields: description is optional for life hazards."""
    author = User.create(name="Citizen", email="citizen@example.com", password="pwd", db=mock_db)
    coords = [77.2090, 28.6139]

    # Empty description for life_hazard should succeed with default text
    rep1 = create_report(author.id, "life_hazard", "", "", coords, db=mock_db)
    assert rep1["category"] == "life_hazard"
    assert rep1["description"] == "Immediate life hazard reported at coordinates."
    assert rep1["status"] == "Reported"

    # Non-empty description is preserved
    rep2 = create_report(author.id, "life_hazard", "Live wire fallen in water puddle!", "", coords, db=mock_db)
    assert rep2["description"] == "Live wire fallen in water puddle!"

    # Other categories still enforce min 10 chars
    with pytest.raises(ValueError, match="at least 10 characters"):
        create_report(author.id, "pothole", "", "", coords, db=mock_db)


def test_rate_limiting_life_hazards_five_per_hour(mock_db):
    """Rate limit: 5 reports per user within 1 hour; 6th report raises ValueError."""
    author = User.create(name="Urgent User", email="urgent@example.com", password="pwd", db=mock_db)
    coords = [77.21, 28.62]

    # Create 5 reports
    for i in range(5):
        rep = create_report(author.id, "life_hazard", f"Emergency incident #{i+1}", "", coords, db=mock_db)
        assert rep["_id"] is not None

    # 6th report within 1 hour must fail
    with pytest.raises(ValueError, match="Rate limit exceeded: You can submit at most 5 life hazard reports per hour"):
        create_report(author.id, "life_hazard", "Emergency incident #6", "", coords, db=mock_db)

    # Different user can still post
    other_user = User.create(name="Other User", email="other@example.com", password="pwd", db=mock_db)
    other_rep = create_report(other_user.id, "life_hazard", "Other incident", "", coords, db=mock_db)
    assert other_rep["_id"] is not None


def test_duplicates_treated_as_corroboration_no_merging_delay(mock_db):
    """Life hazard duplicates are treated as corroboration, not suppressed or delayed."""
    u1 = User.create(name="User 1", email="u1@example.com", password="pwd", db=mock_db)
    u2 = User.create(name="User 2", email="u2@example.com", password="pwd", db=mock_db)
    coords = [77.2090, 28.6139]

    rep1 = create_report(u1.id, "life_hazard", "Transformer sparking violently near metro gate", "", coords, db=mock_db)
    rep2 = create_report(u2.id, "life_hazard", "Transformer sparking violently near metro gate", "", coords, db=mock_db)

    # Neither report has duplicate_of set (no delay/suppression)
    assert rep1.get("duplicate_of") is None
    assert rep2.get("duplicate_of") is None

    # rep1 was corroborated by rep2
    updated_rep1 = mock_db.reports.find_one({"_id": rep1["_id"]})
    assert updated_rep1.get("corroboration_count", 0) >= 1


def test_direct_routing_authority():
    """Verifies direct routing replaces authority emails with lalitnegi0002@gmail.com while testing."""
    auth = get_emergency_authority(77.2090, 28.6139)
    assert "fire_email" in auth
    assert "police_email" in auth
    assert "contact_email" in auth
    assert auth["contact_email"] == "lalitnegi0002@gmail.com"
    assert auth["fire_email"] == "lalitnegi0002@gmail.com"
    assert auth["police_email"] == "lalitnegi0002@gmail.com"


def test_escalation_timers_sixty_minutes(mock_db):
    """If a life hazard report is unacknowledged for 60 minutes, it automatically escalates."""
    author = User.create(name="Citizen", email="timer@example.com", password="pwd", db=mock_db)
    coords = [77.2090, 28.6139]

    # 1. Fresh report (0 mins old)
    fresh_rep = create_report(author.id, "life_hazard", "Gas smell spreading", "", coords, db=mock_db)

    # 2. Older report (65 mins old, unacknowledged / status="Reported")
    old_time = datetime.now(timezone.utc) - timedelta(minutes=65)
    old_rep = create_report(author.id, "life_hazard", "Collapsed wall blocking road", "", coords, db=mock_db)
    mock_db.reports.update_one({"_id": old_rep["_id"]}, {"$set": {"created_at": old_time}})

    # Run escalation check
    escalated_ids = check_and_escalate_life_hazards(db=mock_db)

    assert str(old_rep["_id"]) in escalated_ids
    assert str(fresh_rep["_id"]) not in escalated_ids

    # Check updated document status in DB
    updated_old = mock_db.reports.find_one({"_id": old_rep["_id"]})
    assert updated_old["status"] == "Escalated"
    assert updated_old["is_escalated"] is True
    assert any(log["status"] == "Escalated" for log in updated_old["status_log"])


def test_life_hazard_top_priority_in_feed_across_filters(mock_db):
    """Life hazard reports hold top priority in every field even after any filter is applied until resolved."""
    author = User.create(name="Citizen", email="prio@example.com", password="pwd", db=mock_db)
    coords = [77.2090, 28.6139]

    # Create standard pothole reports
    pothole1 = create_report(author.id, "pothole", "Deep crater on outer ring road lane 1", "", coords, db=mock_db)
    pothole2 = create_report(author.id, "pothole", "Crater on inner ring road lane 2", "", coords, db=mock_db)

    # Create life hazard report
    life_rep = create_report(author.id, "life_hazard", "Live sparking high-voltage electrical cable on waterlogged street", "", coords, db=mock_db)

    # Filter by category="pothole"
    query = build_feed_match_query(category_filter="pothole")
    reports, total = fetch_feed_reports(
        db=mock_db,
        center_lon=77.2090,
        center_lat=28.6139,
        radius_km=100.0,
        match_query=query,
        sort_by="date"
    )

    # Life hazard MUST be included and at the very top (index 0) even though filter is category="pothole"
    assert total >= 3
    assert reports[0]["_id"] == life_rep["_id"]
    assert reports[0]["category"] == "life_hazard"

    # Once resolved, it should no longer be injected when filtering for pothole
    mock_db.reports.update_one({"_id": life_rep["_id"]}, {"$set": {"status": "Resolved"}})
    reports_after_resolve, total_after = fetch_feed_reports(
        db=mock_db,
        center_lon=77.2090,
        center_lat=28.6139,
        radius_km=100.0,
        match_query=query,
        sort_by="date"
    )
    # The resolved life hazard is no longer injected into pothole filter
    rep_ids = [r["_id"] for r in reports_after_resolve]
    assert life_rep["_id"] not in rep_ids


def test_report_view_renders_emergency_buttons_and_action_sheet(mock_db):
    """Report view renders Call 112, Emergency Call, and the static Emergency Action Sheet for life hazards."""
    app = create_app(TestConfig)
    with app.test_client() as client:
        author = User.create(name="Citizen", email="viewer@example.com", password="pwd", db=mock_db)
        coords = [77.2090, 28.6139]
        rep = create_report(author.id, "life_hazard", "Massive gas pipe leak near public school", "", coords, db=mock_db)

        response = client.get(f"/reports/{rep['_id']}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        # Call 112 button present
        assert "tel:112" in html
        assert "Call 112" in html

        # Emergency Call button present
        assert "Emergency Call" in html
        assert "openEmergencyActionSheet()" in html

        # MCD formal complaint link replaced / not rendered
        assert "View &amp; Dispatch MCD Formal Complaint Letter" not in html

        # Static Emergency Action Sheet with all 6 numbers present
        assert "tel:101" in html  # Fire
        assert "tel:102" in html  # Ambulance
        assert "tel:1098" in html  # Childline
        assert "tel:1906" in html  # LPG Leak
        assert "tel:108" in html   # Disaster Management
