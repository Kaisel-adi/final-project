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
