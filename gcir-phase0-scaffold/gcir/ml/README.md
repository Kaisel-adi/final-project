# ML (offline, run locally — PRD §6, §7)

- Hotspots: DBSCAN (haversine metric) on report coordinates -> writes
  reports.cluster_id
- Duplicate suggestion: within ~200m + TF-IDF cosine similarity above
  a tuned threshold -> writes reports.duplicate_of

Not started — this is a Week 6 deliverable.
