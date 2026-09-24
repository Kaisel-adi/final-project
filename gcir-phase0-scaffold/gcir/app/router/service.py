"""Authority router — PRD §5.4, §7.

Point-in-polygon on jurisdictions ($geoIntersects), filtered by
category, most specific level wins. Falls back to district/state body
with a "no direct contact found" notice.
"""


def find_authority(db, point, category):
    """point: GeoJSON Point dict [lon, lat]. Returns a jurisdiction doc or None.

    TODO: Week 4 — $geoIntersects on jurisdictions.geometry, filter by
    category in jurisdictions.categories, sort by level specificity
    (ward/sector > district > state), take the first match.
    """
    raise NotImplementedError
