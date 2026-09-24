# Geo-Tagged Civic Issue Reporter (GCIR)

**GCIR** is a community-driven, geo-spatial civic grievance platform. Residents report geo-tagged civic issues (potholes, garbage dumps, water leaks, broken streetlights), nearby neighbors verify them with upvotes, and upon community verification, the system automatically routes and drafts formal complaint emails addressed to the exact responsible authority (Ward > Sector > District > State).

---

## 🌟 Key Features

1. **High-Precision Geo-Reporting**:
   - Camera/image upload with HTML5 browser geolocation and Leaflet interactive draggable map pin fallback.
   - EXIF GPS metadata is isolated/untrusted for tamper resistance.
2. **Community Verification Engine**:
   - Enforces `VERIFY_THRESHOLD = 10` upvotes before complaint generation is unlocked.
   - One upvote per account; authors cannot upvote their own report.
   - Soft proximity check (~5 km): votes from distant locations are accepted but flagged for audit.
3. **Hierarchical Authority Complaint Router**:
   - Point-in-polygon spatial queries (`$geoIntersects`) resolving exact administrative boundaries: **250 MCD Wards (2022 Delimitation)**, NDMC, Noida Authority, and Ghaziabad Nagar Nigam.
   - Specificity priority: `ward` > `sector` > `district` > `state` with automatic supervisory fallback.
   - One-click `mailto:` dispatch and clipboard copy with pre-filled details, coordinates, photos, upvote metrics, and corroborating issue counts (<200m).
4. **Scheduled Neighborhood Email Digest**:
   - Token-secured endpoint (`/jobs/digest`) scheduled to run every 6 hours (4 times daily).
   - Groups unverified issues within each opted-in resident's radius (capped at 5 items).
   - Strict duplicate suppression via `digest_log` and exclusion of user's own/upvoted issues.
5. **Data & ML Analytics**:
   - **Hotspot Detection**: DBSCAN clustering using the Haversine metric on radian coordinates to locate dense civic problem zones.
   - **Duplicate Detection**: Spatial radius candidate filter (<200m) paired with calibrated TF-IDF bi-gram cosine similarity.

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.11+ (Validated on Python 3.13)
- Git

### 2. Environment Setup
```bash
# Clone the repository
git clone <repo-url>
cd Geo-TaggedCivicIssueReporter

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Key configuration values in `.env`:
- `MONGODB_URI`: Your MongoDB Atlas connection string (or local `mongodb://localhost:27017/gcir_db`).
- `USE_CLOUDINARY`: Set `True` if using Cloudinary, or `False` for local disk uploads during development.
- `EMAIL_BACKEND`: `mock` (logs to console), `resend`, or `sendgrid`.
- `CRON_SECRET_TOKEN`: Secret token protecting the scheduled digest endpoint.

### 4. Ingest Boundaries & Seed Demo Data
```bash
# 1. Ingest, repair, and seed administrative boundaries
python scripts/etl_boundaries.py

# 2. Seed realistic demo users, issues, and clusters across Delhi-NCR
python scripts/seed_demo_data.py
```

### 5. Run Development Server
```bash
python wsgi.py
```
Open your browser at **http://localhost:5000**.

---

## 👥 Demo Accounts

The seed script creates three ready-to-test accounts:

| Role | Email | Password | Home Pin Location |
|---|---|---|---|
| **Resident (Reporter)** | `resident@gcir.local` | `password123` | Karol Bagh, Delhi |
| **Resident (Voter)** | `voter@gcir.local` | `password123` | Karol Bagh (Nearby), Delhi |
| **Civic Moderator / Admin** | `admin@gcir.local` | `admin123` | Connaught Place, NDMC |

---

## 🧪 Testing & ML Evaluation

### Run Complete Automated Test Suite
```bash
python -m pytest tests/ -v
```
All 26 tests run in isolated memory using `mongomock` with zero external database dependencies.

### Evaluate ML Duplicate Detection
```bash
python scripts/evaluate_ml.py
```
Outputs Precision, Recall, and F1-score across 100 hand-labeled test pairs.

---

## 🌐 Deployment to Render

1. Connect your GitHub repository to **Render**.
2. Create a new **Web Service** with:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app`
3. Add Environment Variables in the Render dashboard:
   - `MONGODB_URI`: MongoDB Atlas connection string
   - `SECRET_KEY`: Production secret key
   - `USE_CLOUDINARY`: `True` (with Cloudinary keys)
   - `CRON_SECRET_TOKEN`: Secure random string
4. Configure an external cron job (e.g. at [cron-job.org](https://cron-job.org)) to call `POST https://your-app.onrender.com/jobs/digest` every 6 hours with header `X-Job-Token: <CRON_SECRET_TOKEN>`.
