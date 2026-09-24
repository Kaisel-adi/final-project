"""
Geometry validation/repair for jurisdiction polygons before they go into
MongoDB. PRD §8 gotcha: "Validate polygons before insert."

MongoDB's 2dsphere index will reject self-intersecting or otherwise
invalid GeoJSON polygons at insert time, which is exactly the failure
mode we want to catch here instead — with a coordinate we can point at.
"""
from dataclasses import dataclass

import geopandas as gpd
from shapely.validation import explain_validity, make_valid


@dataclass
class ValidationResult:
    total: int
    invalid_before: int
    repaired: int
    still_invalid: int
    still_invalid_rows: list[int]


def validate_and_repair(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, ValidationResult]:
    """
    Attempts shapely.make_valid() on any invalid geometry. Returns the
    (possibly repaired) GeoDataFrame plus a report. Rows still invalid
    after repair are NOT dropped automatically — the caller decides,
    since silently dropping a jurisdiction is worse than a loud failure.
    """
    total = len(gdf)
    is_valid = gdf.geometry.is_valid
    invalid_before = int((~is_valid).sum())

    repaired = 0
    still_invalid_rows: list[int] = []

    for idx in gdf.index[~is_valid]:
        original = gdf.at[idx, "geometry"]
        fixed = make_valid(original)
        if fixed.is_valid and not fixed.is_empty:
            gdf.at[idx, "geometry"] = fixed
            repaired += 1
        else:
            still_invalid_rows.append(idx)

    # re-check after repair attempts
    still_invalid_mask = ~gdf.geometry.is_valid
    still_invalid_rows = list(gdf.index[still_invalid_mask])

    result = ValidationResult(
        total=total,
        invalid_before=invalid_before,
        repaired=repaired,
        still_invalid=len(still_invalid_rows),
        still_invalid_rows=still_invalid_rows,
    )
    return gdf, result


def explain_invalid(gdf: gpd.GeoDataFrame, row_idx: int) -> str:
    """Human-readable reason a specific row's geometry is invalid."""
    return explain_validity(gdf.at[row_idx, "geometry"])


def drop_empty_and_null(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    before = len(gdf)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    dropped = before - len(gdf)
    if dropped:
        print(f"  dropped {dropped} row(s) with empty/null geometry")
    return gdf
