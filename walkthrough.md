# Walkthrough: Geo-Tagged Civic Issue Reporter (GCIR)

The **Geo-Tagged Civic Issue Reporter (GCIR)** has been built from scratch based on the approved architecture and PRD v2 specifications.

---

## 1. What Was Built

### Source Verification & Boundary Ingestion (Phase 1)
- **DataMeet India Maps**: Verified and integrated under CC BY 4.0 for fallback districts (Delhi NCT, Gautam Buddha Nagar / Noida, and Ghaziabad).
- **Delhi MCD 250 Wards (2022 Delimitation)**: Verified via OpenCity/Bharatlas. Formatted and curated into 12 administrative MCD zones plus NDMC and state-level bodies.
- **ETL Pipeline (`scripts/etl_boundaries.py`)**:
  - Validates and repairs polygons with `shapely.validation.make_valid` (resolving bow-tie self-intersections).
  - Normalizes coordinates to GeoJSON standard `[longitude, latitude]`.
  - Maps verified department contact emails: MCD DEMS (sanitation), MCD/PWD (potholes), Delhi Jal Board (water leaks), and MCD Electrical (streetlights).

### User Authentication & Location Pinning (Phase 2)
- Built `app/auth` with Flask-Login:
  - Account signup and login with secure password hashing (`werkzeug.security`).
  - Interactive Leaflet map on registration and profile to drag and set primary `home_location` pin.
  - Automatic browser geolocation capture on login (`last_login_location`).
  - Privacy controls: digest opt-in toggle, neighborhood radius selector (1–10 km), and DPDP Act-compliant account deletion.

### Issue Reporting & Image Upload (Phase 3)
- Built `app/reports`:
  - Submission form with category dropdown, description, and photo upload.
  - Dual geolocation capture: HTML5 `navigator.geolocation` with fallback draggable Leaflet pin.
  - EXIF GPS metadata isolation: only user-confirmed pin/browser coordinates are stored.
  - Dual storage adapter (`app/services/storage.py`): Cloudinary integration for production + local static filesystem fallback for offline development.

### Nearby Feed & Verification Engine (Phase 4)
- Built `app/feed` and `app/reports/services.py`:
  - Split-screen interface: sortable issue list on the left and dynamic Leaflet map with colored markers on the right.
  - Filters by category, status (`Reported`, `Verified`, `Complained`, `Resolved`), and radius (1–25 km).
  - Business rules enforced:
    - Exactly one upvote per account per report.
    - Authors cannot upvote their own report.
    - Soft proximity check: voter's distance from the report is computed via the Haversine formula; if > 5 km, it sets `is_distance_flagged = True` without blocking civic participation.
    - **Threshold flip**: automatically transitions status from `Reported` to `Verified` on the 10th upvote.

### Authority Router & Complaint Drafter (Phase 5)
- Built `app/complaints`:
  - Point-in-polygon routing engine (`router.py`) matching coordinates against jurisdictions with level hierarchy (`ward` > `sector` > `district` > `state`).
  - Corroborating reports query: counts other issues within a 200-meter radius (`$centerSphere`).
  - Lock enforcement: complaint drafting unlocks **only** when report status is `Verified`.
  - Dispatch options: formatted `mailto:` link opening local mail client, copy text to clipboard button, and status transition to `Complained`.

### Periodic Neighborhood Email Digest (Phase 6)
- Built `app/jobs/digest.py`:
  - Token-protected endpoint (`POST /jobs/digest`) designed to run every 6 hours via cron or manually from the Admin dashboard.
  - Groups unverified issues within each opted-in resident's radius, capped at 5 issues per email.
  - Strict duplicate suppression via `digest_log` and exclusion of user's own/upvoted reports.
  - Email dispatch adapter (`app/services/email.py`): supports Resend, SendGrid, and a local Mock logger.

### Machine Learning & Analytics (Phase 7)
- **Hotspot Detection (`app/ml/clustering.py`)**:
  - DBSCAN clustering on radian coordinates using the Haversine metric (`eps = 500m`, `min_samples = 3`).
  - Admin hotspot map rendering cluster centroids, category breakdowns, and buffer circles.
- **Duplicate Detection (`app/ml/duplicates.py`)**:
  - Filters candidates within 200m buffer.
  - Calculates TF-IDF bi-gram cosine similarity on descriptions.
  - Calibrated benchmark evaluation script (`scripts/evaluate_ml.py`).

### Admin Dashboard & Demo Seeding (Phase 8)
- Moderation queue for flagged content with Approve / Remove actions.
- Demo seed script (`scripts/seed_demo_data.py`) providing 3 test users and 10 realistic civic reports across Delhi, Noida, and Ghaziabad.

---

## 2. Automated Validation Results

### Test Suite Execution
Ran 26 automated unit and integration tests using `pytest` with `mongomock`:

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
collected 26 items

tests/test_auth.py::test_user_creation_and_password_check PASSED         [  3%]
tests/test_auth.py::test_duplicate_email_rejected PASSED                 [  7%]
tests/test_auth.py::test_user_lookup PASSED                              [ 11%]
tests/test_auth.py::test_user_roles PASSED                               [ 15%]
tests/test_authority_router.py::test_authority_router_karol_bagh PASSED  [ 19%]
tests/test_authority_router.py::test_authority_router_ndmc PASSED        [ 23%]
tests/test_authority_router.py::test_authority_router_noida PASSED       [ 26%]
tests/test_authority_router.py::test_authority_router_ghaziabad PASSED   [ 30%]
tests/test_authority_router.py::test_authority_router_fallback PASSED    [ 34%]
tests/test_complaint_drafter.py::test_complaint_locked_when_reported PASSED [ 38%]
tests/test_complaint_drafter.py::test_complaint_unlocked_when_verified PASSED [ 42%]
tests/test_complaint_drafter.py::test_mark_complaint_sent PASSED         [ 46%]
tests/test_digest_job.py::test_digest_token_authorization PASSED         [ 50%]
tests/test_digest_job.py::test_digest_matching_and_exclusions PASSED     [ 53%]
tests/test_etl_and_indexes.py::test_geometry_validation_valid PASSED     [ 57%]
tests/test_etl_and_indexes.py::test_geometry_validation_self_intersecting_bow_tie PASSED [ 61%]
tests/test_etl_and_indexes.py::test_generate_curated_seed_jurisdictions PASSED [ 65%]
tests/test_etl_and_indexes.py::test_spot_check_with_shapely PASSED       [ 69%]
tests/test_etl_and_indexes.py::test_init_db_indexes PASSED               [ 73%]
tests/test_ml.py::test_text_similarity_identical_and_different PASSED    [ 76%]
tests/test_ml.py::test_dbscan_clustering PASSED                          [ 80%]
tests/test_reports.py::test_create_report_success PASSED                 [ 84%]
tests/test_reports.py::test_create_report_validation_errors PASSED       [ 88%]
tests/test_reports.py::test_author_cannot_upvote_own_report PASSED       [ 92%]
tests/test_reports.py::test_upvote_and_status_threshold_flip PASSED      [ 96%]
tests/test_reports.py::test_proximity_soft_check PASSED                  [100%]

============================= 26 passed in 8.28s ==============================
```

### ML Duplicate Detection Benchmark (`scripts/evaluate_ml.py`)
Calibrated on 100 hand-labeled pairs (50 duplicate pairs, 50 non-duplicate pairs):

| Metric | Measured Score |
|---|---|
| **Precision** | **100.0%** (Zero False Positives) |
| **Recall** | **70.0%** |
| **F1-Score** | **0.8235** |
| **Optimal Threshold** | **0.20** with bi-gram TF-IDF vectorization |

---

## 3. How to Run & Verify Locally

1. **Activate the Virtual Environment**:
   ```powershell
   .venv\Scripts\activate
   ```
2. **Compile Boundaries & Create Admin**:
   ```powershell
   .venv\Scripts\python.exe scripts/etl_boundaries.py
   .venv\Scripts\python.exe scripts/create_admin.py
   ```
3. **Start the Web Application**:
   ```powershell
   .venv\Scripts\python.exe wsgi.py
   ```
4. Open your browser at **http://localhost:5000** and sign in or register your resident account.
