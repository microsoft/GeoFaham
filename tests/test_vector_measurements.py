"""Area regressions: WGS84, ring orientation, multipart and mixed geometries."""

import unittest
import json
from unittest.mock import AsyncMock, patch

from pyproj import Geod
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping

from agents.shared.analysis import analyze_geojson_features
from agents.core.types import GeoFahamToolResponse
from agents.vector_agent.tools import VectorQueryExecutor


GEOD = Geod(ellps="WGS84")


def stats(*geometries):
    return analyze_geojson_features([
        {"type": "Feature", "properties": {}, "geometry": mapping(geometry)}
        for geometry in geometries
    ])


def ring_area(ring):
    lon, lat = zip(*ring.coords)
    return abs(GEOD.polygon_area_perimeter(lon, lat)[0])


class PolygonAreaTests(unittest.TestCase):
    def test_area_at_different_latitudes_and_ring_directions(self):
        for latitude in (0, 38.655, 60, -45):
            polygon = box(-90.305, latitude, -90.295, latitude + .01)
            expected = ring_area(polygon.exterior)
            for geom in (polygon, Polygon(list(polygon.exterior.coords)[::-1])):
                with self.subTest(latitude=latitude, reversed=geom.exterior.is_ccw):
                    result = stats(geom)
                    self.assertAlmostEqual(result["poly_total_area_m2"], expected, places=4)
                    self.assertAlmostEqual(result["poly_average_area_m2"], expected, places=4)

    def test_holes_subtract_even_with_same_orientation_as_shell(self):
        outer = box(-90.31, 38.65, -90.29, 38.67)
        hole = box(-90.305, 38.655, -90.295, 38.665)
        polygon = Polygon(outer.exterior.coords, [hole.exterior.coords])
        expected = ring_area(outer.exterior) - ring_area(hole.exterior)
        self.assertAlmostEqual(stats(polygon)["poly_total_area_m2"], expected, places=4)

    def test_multipart_components_with_opposite_winding_add(self):
        first = box(-90.31, 38.65, -90.30, 38.66)
        second = box(-90.29, 38.65, -90.28, 38.66)
        multipart = MultiPolygon([first, Polygon(list(second.exterior.coords)[::-1])])
        expected = ring_area(first.exterior) + ring_area(second.exterior)
        self.assertAlmostEqual(stats(multipart)["poly_total_area_m2"], expected, places=4)

    def test_average_counts_only_polygon_features(self):
        first = box(-90.31, 38.65, -90.30, 38.66)
        second = box(-90.29, 38.65, -90.27, 38.66)
        result = stats(first, second, Point(-90.3, 38.65), LineString([(-90.3, 38.65), (-90.3, 38.66)]))
        expected = ring_area(first.exterior) + ring_area(second.exterior)
        self.assertEqual(result["feature_count"], 4)
        self.assertAlmostEqual(result["poly_total_area_m2"], expected, places=4)
        self.assertAlmostEqual(result["poly_average_area_m2"], expected / 2, places=4)


class VectorTotalTests(unittest.IsolatedAsyncioTestCase):
    async def test_total_after_many_features_is_rejected_instead_of_lost(self):
        executor = VectorQueryExecutor.__new__(VectorQueryExecutor)
        road = {"geom": json.dumps(mapping(LineString([(-90.3, 38.65), (-90.3, 38.66)]))),
                "length_m": 1000}
        rows = [dict(road) for _ in range(482)] + [{"geom": None, "length_m": 482}]
        for include_table in (True, False):
            with self.subTest(include_table=include_table):
                with patch("agents.vector_agent.tools.results_to_geojson", new_callable=AsyncMock) as save:
                    result = await executor._build_layer_response(
                        rows, "review_mixed_total", "Roads and total", "geom", False, include_table
                    )
                response = GeoFahamToolResponse.model_validate_json(result)
                self.assertEqual(response.type, "error")
                self.assertIn("separate queries", response.error_message)
                self.assertIn("return_layer=False", response.error_message)
                save.assert_not_awaited()

    async def test_separate_total_is_returned_with_explicit_units(self):
        executor = VectorQueryExecutor.__new__(VectorQueryExecutor)
        result = executor._build_data_response(
            [{"total_length_km": 47.69483721}], "review_total", "Total clipped road length", None
        )
        response = GeoFahamToolResponse.model_validate_json(result)
        self.assertEqual(response.type, "data")
        self.assertEqual(response.data, [{"total_length_km": 47.69483721}])


if __name__ == "__main__":
    unittest.main()
