# GCIR — Geo-Tagged Civic Issue Reporter

Scaffold for the app described in `GCIR_PRD_v2.md`. Delhi / Greater Noida /
Ghaziabad pilot; Flask + MongoDB Atlas + Leaflet.

## Status: Phase 0 — scaffolding

What exists now:
- App factory (`app/__init__.py`) wiring config, Mongo, Flask-Login, and
  six blueprints: `auth`, `reports`, `feed`, `drafter`, `admin`, `jobs`
- `app/config.py` — all tunables from PRD §4/§5.5/§6 as env vars
  (`VERIFY_THRESHOLD`, `UPVOTE_PROXIMITY_KM`, digest cap, duplicate radius)
- `app/extensions.py` — shared Mongo client/db handle
- `app/models/schemas.py` — reference for the 5 collections in PRD §8
  (nothing enforced yet — Mongo has no foreign keys, so this is just docs)
- Route stubs for every endpoint implied by PRD §5, each with a `TODO`
  pointing at its milestone week
- `etl/` and `ml/` — empty, READMEs point at their PRD sections (Weeks 1, 6)
- `.env.example` — every secret/config the app needs, none filled in

Nothing here talks to a real database yet — `create_app()` builds a Mongo
client but PyMongo connects lazily, so it imports fine with no Atlas
cluster configured.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in MONGO_URI at minimum to actually run
python run.py
```

## Next (Week 1 per PRD §14)

1. Stand up the Atlas cluster, create the 5 collections, add the
   `2dsphere` indexes listed in `app/models/schemas.py`
2. `etl/` — pull DataMeet + Opencity boundary sources, validate/reproject
   with GeoPandas, load into `jurisdictions`
3. Decide the pilot area (PRD §10 open item) based on which boundaries
   are actually clean enough to use
