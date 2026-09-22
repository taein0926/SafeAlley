import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from preprocess.pedestrian_references import read_pedestrian_references


def feature(identity="test", kind="intersection"):
    return {"id": identity, "type": "Feature", "geometry": {"type": "Point", "coordinates": [126.68, 37.46]},
            "properties": {"kind": kind, "source": "test", "source_id": identity,
                           "position_semantics": "representative_point", "validation_status": "unverified"}}


def write_collection(tmp_path, features, **extra):
    path = tmp_path / "references.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features, **extra}), encoding="utf-8")
    return path


def test_preserves_reference_provenance_and_duplicate_positions(tmp_path):
    features = [feature("a"), feature("b"), feature("c", "bridge")]
    assert read_pedestrian_references(write_collection(tmp_path, features)) == features


@pytest.mark.parametrize("problem", ["duplicate-id", "coordinates", "geometry", "kind", "provenance", "crs", "empty"])
def test_invalid_references_fail_before_loading(tmp_path, problem):
    features = [feature()]
    extra = {}
    if problem == "duplicate-id": features.append(feature())
    if problem == "coordinates": features[0]["geometry"]["coordinates"] = [900000, 1900000]
    if problem == "geometry": features[0]["geometry"]["type"] = "LineString"
    if problem == "kind": features[0]["properties"]["kind"] = "invented"
    if problem == "provenance": del features[0]["properties"]["validation_status"]
    if problem == "crs": extra["crs"] = {"properties": {"name": "EPSG:5179"}}
    if problem == "empty": features = []
    with pytest.raises(ValueError):
        read_pedestrian_references(write_collection(tmp_path, features, **extra))


def test_supplied_michuhol_counts():
    path = Path(__file__).parents[1] / "raw/pedestrian_references/pedestrian_references.geojson"
    if not path.exists(): pytest.skip("Local reference input not supplied")
    features = read_pedestrian_references(path)
    assert sum(f["properties"]["kind"] == "bridge" for f in features) == 9
    assert sum(f["properties"]["kind"] == "intersection" for f in features) == 341


@pytest.mark.skipif(not os.environ.get("DB_HOST"), reason="PostGIS integration requires configured test DB")
def test_linker_unions_duplicates_preserves_topology_and_only_matches_mapped_bridges():
    from loaders.postgis import database_connection
    from loaders.pedestrian_references import link_reference_metadata

    source = "ref-test-" + uuid4().hex[:12]
    ids = [source + suffix for suffix in ("-i1", "-i2", "-b")]
    with database_connection() as connection:
        # No test rows or metadata survive the test, even when an assertion fails.
        with connection.transaction(force_rollback=True):
            with connection.cursor() as cursor:
                for identity, kind in zip(ids, ("intersection", "intersection", "bridge")):
                    cursor.execute("""INSERT INTO pedestrian_references VALUES
                        (%s, %s, '{}'::jsonb, ST_SetSRID(ST_MakePoint(900050,1900000),5179))""", (identity, kind))
                for suffix, bridge in (("ground", False), ("bridge", True)):
                    props = {"highway": "footway", "is_steps": True, "osm_tags": {"bridge": "yes" if bridge else "no"}}
                    cursor.execute("""INSERT INTO road_segments
                        (source, source_id, source_node_id, target_node_id, geom, length_m, safety_score, properties)
                        VALUES (%s, %s, 1, 2, ST_GeomFromText('LINESTRING(900000 1900000,900100 1900000)',5179), 100, 73, %s)
                    """, (source, suffix, Jsonb(props)))
                first = link_reference_metadata(cursor, [ids[0], ids[2]], source)
                second = link_reference_metadata(cursor, ids, source)
                assert first == second
                assert second["annotated_edges"] == 2
                assert second["bridge_edges"] == 1
                assert second["matched_bridge_ids"] == [ids[2]]
                cursor.execute("""SELECT source_id, safety_score, length_m, properties,
                    ST_AsText(geom), source_node_id, target_node_id
                    FROM road_segments WHERE source = %s ORDER BY source_id""", (source,))
                rows = cursor.fetchall()
                assert len(rows) == 2
                for identity, safety, length, props, geometry, start, end in rows:
                    assert float(safety) == 73 and float(length) == 100
                    assert props["is_steps"] is True
                    assert (start, end) == (1, 2)
                    assert geometry == "LINESTRING(900000 1900000,900100 1900000)"
                    exposure = props["pedestrian_reference"]["intersection_exposure_m"]
                    assert exposure == pytest.approx(0 if identity == "bridge" else 70)
