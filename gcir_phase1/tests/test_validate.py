"""
Synthetic tests for etl/validate.py. No real boundary data needed here —
these just prove the repair/rejection logic works before it's pointed at
DataMeet/Opencity files.
"""
import geopandas as gpd
from shapely.geometry import Polygon

from etl.validate import drop_empty_and_null, validate_and_repair


def make_valid_square():
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def make_bowtie():
    # self-intersecting "bowtie" polygon — classic invalid geometry
    return Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])


def test_valid_geometry_passes_through_unchanged():
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[make_valid_square()], crs="EPSG:4326")
    result_gdf, result = validate_and_repair(gdf)
    assert result.invalid_before == 0
    assert result.repaired == 0
    assert result.still_invalid == 0
    assert result_gdf.geometry.iloc[0].equals(make_valid_square())


def test_bowtie_is_repaired():
    gdf = gpd.GeoDataFrame({"name": ["b"]}, geometry=[make_bowtie()], crs="EPSG:4326")
    assert not gdf.geometry.iloc[0].is_valid  # sanity check on the fixture itself

    result_gdf, result = validate_and_repair(gdf)
    assert result.invalid_before == 1
    assert result.repaired == 1
    assert result.still_invalid == 0
    assert result_gdf.geometry.iloc[0].is_valid


def test_empty_and_null_geometry_dropped():
    gdf = gpd.GeoDataFrame(
        {"name": ["valid", "empty", "null"]},
        geometry=[make_valid_square(), Polygon(), None],
        crs="EPSG:4326",
    )
    cleaned = drop_empty_and_null(gdf)
    assert list(cleaned["name"]) == ["valid"]


def test_mixed_batch_reports_correct_counts():
    gdf = gpd.GeoDataFrame(
        {"name": ["ok1", "bad1", "ok2"]},
        geometry=[make_valid_square(), make_bowtie(), make_valid_square()],
        crs="EPSG:4326",
    )
    _, result = validate_and_repair(gdf)
    assert result.total == 3
    assert result.invalid_before == 1
    assert result.repaired == 1
    assert result.still_invalid == 0
