"""Reference for the MongoDB collections — PRD §8. Not enforced by
Mongo itself (no foreign keys), so validate in code at insert time.

users:          name, email, password_hash, role,
                home_location (Point), last_login_location (Point),
                last_login_at, digest_opt_in, digest_radius_km
reports:        author_id, category, description, photo_url,
                location (Point), status, upvote_count, cluster_id,
                duplicate_of, status_log[], created_at
upvotes:        report_id, user_id, created_at
jurisdictions:  name, level (ward/sector/district/state), body,
                categories[], contact_email,
                geometry (Polygon/MultiPolygon), source, source_date
digest_log:     user_id, report_ids[], sent_at

Indexes to create once collections exist (Week 1):
  reports.location            -> 2dsphere
  users.home_location         -> 2dsphere
  jurisdictions.geometry      -> 2dsphere
  upvotes (report_id,user_id) -> unique compound

GeoJSON coordinate order is [longitude, latitude] — PRD §8 Gotchas.
"""

REPORT_STATUSES = ("Reported", "Verified", "Removed", "Complained", "Resolved")
JURISDICTION_LEVELS = ("ward", "sector", "district", "state")
