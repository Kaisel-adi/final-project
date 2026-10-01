import io
import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage
from app.auth.models import User
from app.reports.services import create_report
from app.services.storage import save_image


def test_base_renders_mobile_navigation_and_performance_elements(client):
    res = client.get("/auth/login")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Check mobile navigation toggle & hamburger
    assert "nav-toggle" in html
    assert "hamburger-bar" in html

    # Check mobile thumb-friendly bottom navigation bar
    assert "mobile-bottom-nav" in html
    assert "mobile-nav-cta" in html

    # Check offline / weak connection status toast
    assert "offline-toast" in html

    # Check DNS prefetch and preconnect hints for weak network performance
    assert 'rel="dns-prefetch" href="https://tile.openstreetmap.org"' in html
    assert 'rel="preconnect" href="https://unpkg.com"' in html


def test_feed_page_renders_view_switcher_and_svg_pins(client, mock_db):
    author = User.create(name="Feed Citizen", email="feedcitizen@test.com", password="pass", db=mock_db)
    create_report(
        author_id=author.id,
        category="pothole",
        description="Dangerous road crater on outer ring road.",
        photo_url="/static/uploads/road_pothole.jpg",
        coordinates=[77.21, 28.61],
        db=mock_db
    )

    res = client.get("/feed?lat=28.61&lon=77.21&radius=5.0")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Check Mobile view switcher (List vs Map)
    assert "feed-view-toggle-bar" in html
    assert "btn-view-list" in html
    assert "btn-view-map" in html
    assert "setFeedMobileView" in html

    # Check lazy loading and async decoding for media to save weak network bandwidth
    assert 'loading="lazy"' in html
    assert 'decoding="async"' in html

    # Check zero-network SVG map marker generation (replaces slow GitHub raw PNG downloads)
    assert "createSvgPin" in html
    assert "custom-map-pin" in html


def test_report_create_renders_client_compression_and_responsive_grid(client, mock_db):
    user = User.create(name="Reporter Citizen", email="reporterc@test.com", password="pass", db=mock_db)
    with client.session_transaction() as sess:
        sess["_user_id"] = user.id

    res = client.get("/reports/create")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Check client-side downscaling & compression function for mobile cameras
    assert "compressImageIfNeeded" in html
    assert "compression-badge" in html

    # Check responsive form grid
    assert "form-grid-2col" in html


def test_report_view_renders_responsive_detail_layout(client, mock_db):
    author = User.create(name="Incident Poster", email="incident@test.com", password="pass", db=mock_db)
    rep = create_report(
        author_id=author.id,
        category="garbage",
        description="Municipal waste overflowing on neighborhood corner.",
        photo_url="/static/uploads/garbage_overflow.jpg",
        coordinates=[77.22, 28.63],
        db=mock_db
    )

    res = client.get(f"/reports/{rep['_id']}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Verify responsive CSS grid classes are used instead of hard-coded inline 1fr 1fr styles
    assert "report-detail-layout" in html
    assert "report-detail-media" in html
    assert "report-detail-content" in html
    assert "report-detail-grid-bottom" in html


def test_static_asset_cache_headers(client):
    res = client.get("/static/css/style.css")
    assert res.status_code == 200
    cache_control = res.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "max-age=" in cache_control


def test_pillow_image_compression_in_storage(app):
    with app.app_context():
        # Create an uncompressed test image in memory
        img = Image.new("RGB", (2000, 1500), color=(255, 100, 50))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG", quality=100)
        img_bytes.seek(0)

        storage_file = FileStorage(
            stream=img_bytes,
            filename="large_photo.jpg",
            content_type="image/jpeg"
        )

        saved_url = save_image(storage_file)
        assert saved_url.startswith("/static/uploads/")
        assert saved_url.endswith(".jpg")


def test_feed_and_api_pagination_and_distance_caching(client, mock_db):
    author = User.create(name="Civic User", email="civic@test.com", password="pwd", db=mock_db)
    for i in range(5):
        create_report(
            author_id=author.id,
            category="pothole",
            description=f"Pothole issue number {i}",
            photo_url=f"/static/uploads/pothole_{i}.jpg",
            coordinates=[77.2090 + (i * 0.001), 28.6139 + (i * 0.001)],
            db=mock_db
        )

    # Test feed view pagination (page 1, per_page 2)
    res = client.get("/feed?lat=28.6139&lon=77.2090&radius=5.0&per_page=2&page=1")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Found <strong>5</strong> issues nearby" in html
    assert "Page 1 of 3" in html

    # Test feed view page 2
    res_p2 = client.get("/feed?lat=28.6139&lon=77.2090&radius=5.0&per_page=2&page=2")
    assert res_p2.status_code == 200
    html_p2 = res_p2.get_data(as_text=True)
    assert "Page 2 of 3" in html_p2

    # Test API pagination (/feed/api/reports)
    api_res = client.get("/feed/api/reports?lat=28.6139&lon=77.2090&radius=5.0&limit=2&page=1")
    assert api_res.status_code == 200
    data = api_res.get_json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["limit"] == 2
    assert "distance_km" in data["features"][0]["properties"]


def test_duplicate_batch_similarity_and_spatial_filtering(mock_db):
    from app.ml.duplicates import compute_batch_text_similarity, check_potential_duplicate, clear_duplicate_cache

    clear_duplicate_cache()
    # Test batch similarity
    target = "Dangerous massive pothole near metro pillar 45"
    candidates = [
        "Huge pothole near pillar 45 of metro",
        "Completely unrelated broken garbage bin",
        "Pothole crater at pillar 45"
    ]
    scores = compute_batch_text_similarity(target, candidates, db=mock_db)
    assert len(scores) == 3
    assert scores[0] > 0.15
    assert scores[1] < 0.10
    assert scores[2] > 0.15

    # Test spatial filtering in duplicate check
    author = User.create(name="Dup User", email="dup@test.com", password="pwd", db=mock_db)
    rep1 = create_report(
        author_id=author.id,
        category="pothole",
        description="Massive road crater near gate 2",
        photo_url="url1",
        coordinates=[77.2090, 28.6139],
        db=mock_db
    )

    # Nearby report (approx 50m away) with matching text
    new_doc_nearby = {
        "_id": "temp_id_1",
        "category": "pothole",
        "description": "Massive road crater right by gate 2",
        "location": {"coordinates": [77.2094, 28.6141]}
    }
    match = check_potential_duplicate(new_doc_nearby, radius_meters=200.0, db=mock_db)
    assert match is not None
    assert match["_id"] == rep1["_id"]

    # Distant report (5km away) with identical text should NOT match
    new_doc_far = {
        "_id": "temp_id_2",
        "category": "pothole",
        "description": "Massive road crater near gate 2",
        "location": {"coordinates": [77.2500, 28.6500]}
    }
    match_far = check_potential_duplicate(new_doc_far, radius_meters=200.0, db=mock_db)
    assert match_far is None


def test_profile_reports_pagination(client, mock_db):
    user = User.create(name="Profile User", email="profileuser@test.com", password="pwd", db=mock_db)
    for i in range(15):
        create_report(
            author_id=user.id,
            category="garbage",
            description=f"Garbage overflow spot {i}",
            photo_url="url",
            coordinates=[77.21, 28.61],
            db=mock_db
        )

    with client.session_transaction() as sess:
        sess["_user_id"] = user.id

    # Page 1
    res = client.get("/auth/profile?page=1")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "15 Total" in html
    assert "Page 1 of 2" in html
    assert "Next &rarr;" in html

    # Page 2
    res2 = client.get("/auth/profile?page=2")
    assert res2.status_code == 200
    html2 = res2.get_data(as_text=True)
    assert "Page 2 of 2" in html2
    assert "&larr; Previous" in html2


def test_email_caching_and_async_dispatch(app):
    from app.services.email import (
        _clean_str,
        _sanitize_from_email,
        send_email,
        send_email_async
    )

    # String cleaning caching
    raw = '  "test-config-value"  '
    c1 = _clean_str(raw)
    c2 = _clean_str(raw)
    assert c1 == "test-config-value"
    assert c1 is c2  # Returned cached reference

    # Sanitization caching
    s1 = _sanitize_from_email("alerts@gcir.local", "smtp", "alerts@gmail.com")
    s2 = _sanitize_from_email("alerts@gcir.local", "smtp", "alerts@gmail.com")
    assert s1 == "GCIR Civic Alerts <alerts@gmail.com>"
    assert s1 is s2

    # Async email dispatch
    with app.app_context():
        app.config["EMAIL_BACKEND"] = "mock"
        future = send_email_async("resident@test.com", "Async Subject", "<p>Content</p>")
        res = future.result(timeout=5)
        assert res[0] is True
        assert res[1] == "mock"

        # Non-blocking send_email with background=True
        sent_bg = send_email("resident@test.com", "Bg Subject", "<p>Content</p>", background=True)
        assert sent_bg is True


def test_clustering_cache_and_invalidation(mock_db):
    from app.ml.clustering import compute_dbscan_hotspots, clear_hotspots_cache

    clear_hotspots_cache()
    author = User.create(name="Clusterer", email="clust@test.com", password="pwd", db=mock_db)

    # Create 3 clustered reports
    create_report(author.id, "pothole", "Pothole crater at site A", "url", [77.1900, 28.6500], db=mock_db)
    create_report(author.id, "pothole", "Pothole crater at site B", "url", [77.1904, 28.6502], db=mock_db)
    create_report(author.id, "pothole", "Pothole crater at site C", "url", [77.1908, 28.6505], db=mock_db)

    # First call: computes clusters
    clusters_1 = compute_dbscan_hotspots(eps_km=0.5, min_samples=3, db=mock_db)
    assert len(clusters_1) == 1

    # Second call: served from cache
    clusters_2 = compute_dbscan_hotspots(eps_km=0.5, min_samples=3, db=mock_db)
    assert clusters_1 == clusters_2

    # Force refresh or clear cache
    clear_hotspots_cache()
    clusters_3 = compute_dbscan_hotspots(eps_km=0.5, min_samples=3, db=mock_db, force_refresh=True)
    assert len(clusters_3) == 1


def test_db_indexes_comprehensive(mock_db):
    from app.db import init_db_indexes
    indexes = init_db_indexes(mock_db)
    assert "reports" in indexes
    report_idx_names = indexes["reports"]
    assert "idx_reports_author_created" in report_idx_names
    assert "idx_reports_created" in report_idx_names
    assert "idx_reports_cat_status" in report_idx_names


def test_feed_radius_options_and_community_100km_default(client, mock_db):
    author = User.create(name="Radius Citizen", email="radius@test.com", password="pwd", db=mock_db)
    # Point at 28.6139, 77.2090
    # Create report at 8km away: approx 0.07 deg lat
    create_report(
        author_id=author.id,
        category="pothole",
        description="Pothole at 8km away",
        photo_url="/static/uploads/p1.jpg",
        coordinates=[77.2090, 28.6859],
        db=mock_db
    )
    # Create report at 40km away: approx 0.36 deg lat
    create_report(
        author_id=author.id,
        category="garbage",
        description="Garbage dump at 40km away",
        photo_url="/static/uploads/p2.jpg",
        coordinates=[77.2090, 28.9739],
        db=mock_db
    )

    # 1. Home dashboard default 5km (neither report matches)
    res_5km = client.get("/feed?lat=28.6139&lon=77.2090&view=dashboard")
    assert res_5km.status_code == 200
    html_5km = res_5km.get_data(as_text=True)
    assert "No Active Civic Issues Nearby" in html_5km

    # 2. Home dashboard set to 10km (8km report matches, 40km does not)
    res_10km = client.get("/feed?lat=28.6139&lon=77.2090&view=dashboard&radius=10.0")
    assert res_10km.status_code == 200
    html_10km = res_10km.get_data(as_text=True)
    assert "Pothole at 8km away" in html_10km
    assert "Garbage dump at 40km away" not in html_10km

    # 3. Community list view default (fixed 100km: both 8km and 40km reports match!)
    res_comm = client.get("/feed?lat=28.6139&lon=77.2090&view=list")
    assert res_comm.status_code == 200
    html_comm = res_comm.get_data(as_text=True)
    assert "Pothole at 8km away" in html_comm
    assert "Garbage dump at 40km away" in html_comm
    assert "100 km (Fixed Region)" in html_comm


def test_feed_sorting_criteria(client, mock_db):
    author = User.create(name="Sort Citizen", email="sort@test.com", password="pwd", db=mock_db)
    
    r1 = create_report(author.id, "pothole", "Low likes recent issue", "url1", [77.2100, 28.6140], db=mock_db)
    r2 = create_report(author.id, "pothole", "High likes popular issue", "url2", [77.2110, 28.6150], db=mock_db)
    r3 = create_report(author.id, "pothole", "Verified civic hazard", "url3", [77.2120, 28.6160], db=mock_db)

    # Set upvotes and statuses
    mock_db.reports.update_one({"_id": r1["_id"]}, {"$set": {"upvote_count": 2, "status": "Reported"}})
    mock_db.reports.update_one({"_id": r2["_id"]}, {"$set": {"upvote_count": 25, "status": "Reported"}})
    mock_db.reports.update_one({"_id": r3["_id"]}, {"$set": {"upvote_count": 5, "status": "Verified"}})

    # 1. Sort by likes
    res_likes = client.get("/feed?lat=28.6139&lon=77.2090&view=list&sort=likes")
    assert res_likes.status_code == 200
    html_likes = res_likes.get_data(as_text=True)
    pos_high = html_likes.find("High likes popular issue")
    pos_low = html_likes.find("Low likes recent issue")
    assert pos_high != -1 and pos_low != -1
    assert pos_high < pos_low

    # 2. Sort by verified
    res_ver = client.get("/feed?lat=28.6139&lon=77.2090&view=list&sort=verified")
    assert res_ver.status_code == 200
    html_ver = res_ver.get_data(as_text=True)
    pos_ver = html_ver.find("Verified civic hazard")
    pos_rep = html_ver.find("High likes popular issue")
    assert pos_ver != -1 and pos_rep != -1
    assert pos_ver < pos_rep


def test_feed_chunk_infinite_scroll_api(client, mock_db):
    author = User.create(name="Chunk Citizen", email="chunk@test.com", password="pwd", db=mock_db)
    for i in range(16):
        create_report(
            author_id=author.id,
            category="pothole",
            description=f"Chunk test pothole #{i:02d}",
            photo_url=f"/static/uploads/c_{i}.jpg",
            coordinates=[77.2090 + (i * 0.0005), 28.6139 + (i * 0.0005)],
            db=mock_db
        )

    # Initial view loads 10 reports
    res_initial = client.get("/feed?lat=28.6139&lon=77.2090&view=list")
    assert res_initial.status_code == 200
    html_initial = res_initial.get_data(as_text=True)
    assert 'data-has-more="true"' in html_initial
    assert 'data-next-offset="10"' in html_initial

    # Chunk API request 1: offset=10, limit=5 (subsequent scroll loads 5)
    res_c1 = client.get("/feed/api/chunk?lat=28.6139&lon=77.2090&offset=10&limit=5&view=list")
    assert res_c1.status_code == 200
    data_c1 = res_c1.get_json()
    assert data_c1["success"] is True
    assert data_c1["count"] == 5
    assert data_c1["next_offset"] == 15
    assert data_c1["has_more"] is True
    assert "issue-card" in data_c1["html"]

    # Chunk API request 2: offset=15, limit=5 (remaining 1 report)
    res_c2 = client.get("/feed/api/chunk?lat=28.6139&lon=77.2090&offset=15&limit=5&view=list")
    assert res_c2.status_code == 200
    data_c2 = res_c2.get_json()
    assert data_c2["success"] is True
    assert data_c2["count"] == 1
    assert data_c2["next_offset"] == 16
    assert data_c2["has_more"] is False


def test_feed_chunk_filter_and_sorting_api(client, mock_db):
    author = User.create(name="Sort Citizen", email="sort@test.com", password="pwd", db=mock_db)
    
    rep1 = create_report(
        author_id=author.id,
        category="streetlight",
        description="Dark alley street light broken",
        photo_url="/static/uploads/light.jpg",
        coordinates=[77.2090, 28.6139],
        db=mock_db
    )
    rep2 = create_report(
        author_id=author.id,
        category="pothole",
        description="Big crater in avenue",
        photo_url="/static/uploads/pothole.jpg",
        coordinates=[77.2095, 28.6145],
        db=mock_db
    )
    # Upvote rep2 to 15 likes and verify it
    mock_db.reports.update_one({"_id": rep2["_id"]}, {"$set": {"upvote_count": 15, "status": "Verified"}})

    # 1. Filter by category
    res_cat = client.get("/feed/api/chunk?lat=28.6139&lon=77.2090&category=streetlight&view=list")
    assert res_cat.status_code == 200
    data_cat = res_cat.get_json()
    assert data_cat["total"] == 1
    assert "street light broken" in data_cat["html"]
    assert "data-category=\"streetlight\"" in data_cat["html"]
    assert "data-likes=\"0\"" in data_cat["html"]

    # 2. Filter by status
    res_stat = client.get("/feed/api/chunk?lat=28.6139&lon=77.2090&status=Verified&view=list")
    assert res_stat.status_code == 200
    data_stat = res_stat.get_json()
    assert data_stat["total"] == 1
    assert "Big crater" in data_stat["html"]
    assert "data-status=\"Verified\"" in data_stat["html"]
    assert "data-likes=\"15\"" in data_stat["html"]

    # 3. Sort by likes
    res_sort = client.get("/feed/api/chunk?lat=28.6139&lon=77.2090&sort=likes&view=list")
    assert res_sort.status_code == 200
    data_sort = res_sort.get_json()
    assert data_sort["total"] == 2
    pos_rep2 = data_sort["html"].find("Big crater")
    pos_rep1 = data_sort["html"].find("Dark alley")
    assert pos_rep2 < pos_rep1



