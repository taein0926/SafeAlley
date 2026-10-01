"""Refresh a complete district snapshot atomically, with real safety reanalysis.

Use a fresh administrative-area snapshot and a verified pg_dump backup first.
Default invocation only prepares/diffs; --apply commits after all analysis passes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from analysis.streetlight_safety import run_streetlight_safety_analysis
from analysis.safety_components import run_safety_component_analysis
from loaders.postgis import database_connection
from loaders.pedestrian_references import link_reference_metadata
from preprocess.osm_roads import preprocess_osm_roads
from preprocess.osm_pedestrian import pedestrian_metadata

VERSION = "osm-pedestrian-michuhol-v2"


def validate_snapshot(document, metadata):
    query = metadata.get("query", "")
    if metadata.get("area_name") != "미추홀구" or metadata.get("admin_level") != "6":
        raise ValueError("A full Michuhol administrative-area snapshot is required")
    if '(area.searchArea)' not in query or 'node["highway"="crossing"]' not in query:
        raise ValueError("Snapshot query must include district roads and crossing nodes")
    if document.get("remark") or not document.get("osm3s", {}).get("timestamp_osm_base"):
        raise ValueError("Incomplete or undated OSM response")
    elements = document.get("elements", [])
    if not any(e.get("type") == "way" for e in elements):
        raise ValueError("No OSM ways")
    return document["osm3s"]["timestamp_osm_base"]


def snapshot_crossings(document):
    return {e["id"]: e for e in document["elements"]
            if e.get("type") == "node" and e.get("tags", {}).get("highway") == "crossing"}


def refresh(input_path: Path, output_dir: Path, backup: Path, apply: bool):
    document = json.loads(input_path.read_text(encoding="utf-8"))
    metadata = json.loads(input_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    timestamp = validate_snapshot(document, metadata)
    if not backup.is_file() or backup.stat().st_size < 1000:
        raise ValueError("An existing verified pg_dump backup is required")
    with backup.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Expected a custom-format pg_dump backup")
    output_dir.mkdir(parents=True, exist_ok=True)
    processed = output_dir / "roads.geojson"
    # Tiny positive segments are real topology, not noise to drop.
    os.environ["OSM_MIN_SEGMENT_LENGTH_M"] = "0"
    os.environ["OSM_SAFETY_SCORE_MODE"] = "uniform"
    stats = preprocess_osm_roads(input_path, processed)
    features = json.loads(processed.read_text(encoding="utf-8"))["features"]
    incoming = {f["properties"]["source_id"] for f in features}
    if len(incoming) != len(features):
        raise ValueError("Duplicate incoming road source IDs")
    crossings = snapshot_crossings(document)
    report = {"timestamp": timestamp, "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "backup": str(backup), "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
              "preprocess": stats, "crossing_nodes": len(crossings), "applied": apply}
    with database_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, source_id, source_node_id, target_node_id FROM road_segments WHERE source='osm'")
            old = {r["source_id"]: r for r in cur.fetchall()}
            retired = sorted(old.keys() - incoming)
            report.update(new_source_ids=len(incoming-old.keys()), retired_source_ids=len(retired),
                          retained_source_ids=len(incoming & old.keys()))
            # Fail closed on a partial fetch / unexpected district change.
            if old and (len(features) < len(old)*0.8 or len(retired) > len(old)*0.2):
                raise ValueError("Unexpectedly large loss of existing roads; inspect before applying")
            if not apply:
                print(json.dumps(report, ensure_ascii=True), flush=True)
                return report
            cur.execute("SELECT pg_advisory_xact_lock(6010101)")
            cur.execute("LOCK TABLE road_segments IN SHARE ROW EXCLUSIVE MODE")
            # Source-key upsert retains IDs used by unchanged current roads.
            # Safety values are recomputed before this transaction is visible.
            for feature in features:
                p = feature["properties"]
                cur.execute("""
                    INSERT INTO road_segments (source,source_id,name,source_node_id,target_node_id,
                        forward_allowed,reverse_allowed,geom,length_m,streetlight_score,cctv_score,
                        population_score,safety_score,help_point_score,properties)
                    SELECT 'osm',%s,%s,%s,%s,%s,%s,g,ST_Length(g),0,0,0,0,0,%s
                    FROM (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),5179) AS g) t
                    ON CONFLICT (source,source_id) DO UPDATE SET
                        name=EXCLUDED.name,source_node_id=EXCLUDED.source_node_id,target_node_id=EXCLUDED.target_node_id,
                        forward_allowed=EXCLUDED.forward_allowed,reverse_allowed=EXCLUDED.reverse_allowed,
                        geom=EXCLUDED.geom,length_m=EXCLUDED.length_m,properties=EXCLUDED.properties,updated_at=NOW()
                """, (p["source_id"],p.get("name"),p["source_node_id"],p["target_node_id"],
                      p["forward_allowed"],p["reverse_allowed"],Jsonb(p),json.dumps(feature["geometry"])))
            cur.execute("DELETE FROM road_segments WHERE source='osm' AND source_id=ANY(%s)", (retired,))
            cur.execute("SELECT id,source_node_id,target_node_id,length_m,properties FROM road_segments WHERE source='osm'")
            rows = cur.fetchall()
            updates = pedestrian_metadata(document, rows, version=VERSION)
            if len(updates) != len(features):
                raise ValueError("Not all refreshed roads matched the pedestrian topology")
            for identity, values in updates.items():
                cur.execute("UPDATE road_segments SET properties=jsonb_set(properties,'{osm_pedestrian}',%s) WHERE id=%s",
                            (Jsonb(values),identity))
            for identity, node in crossings.items():
                cur.execute("""INSERT INTO public_crosswalks
                    (source,source_id,source_dataset,source_url,reference_date,geom)
                    VALUES ('osm-crossing-node',%s,'OpenStreetMap highway=crossing',%s,%s,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),5179))
                    ON CONFLICT(source,source_id) DO UPDATE SET geom=EXCLUDED.geom,
                        reference_date=EXCLUDED.reference_date,source_url=EXCLUDED.source_url
                """, (str(identity),f"https://www.openstreetmap.org/node/{identity}",timestamp[:10],node["lon"],node["lat"]))
            cur.execute("DELETE FROM public_crosswalks WHERE source='osm-crossing-node' AND NOT(source_id=ANY(%s))",
                        ([str(i) for i in crossings],))
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pedestrian_references")
            reference_ids = [r[0] for r in cur.fetchall()]
            report["references"] = link_reference_metadata(cur, reference_ids)
        print("Topology prepared; recomputing streetlight scores within the same transaction", flush=True)
        report["streetlights"] = run_streetlight_safety_analysis(streetlight_source="michuhol-public-data", connection=conn)
        print("Recomputing precise CCTV/help-point scores", flush=True)
        report["safety"] = run_safety_component_analysis(connection=conn)
        with conn.cursor() as cur:
            cur.execute("""SELECT count(*) FROM road_segments r WHERE source='osm' AND
                (NOT ST_IsValid(geom) OR length_m<=0 OR NOT EXISTS
                    (SELECT 1 FROM road_safety_segments s WHERE s.road_id=r.id))""")
            if cur.fetchone()[0]:
                raise ValueError("Road geometry or safety coverage validation failed")
            cur.execute("SELECT count(*) FROM road_segments WHERE source='osm' AND properties->>'highway'='steps'")
            report["stairs_segments"] = cur.fetchone()[0]
    (output_dir/"refresh-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"streetlights","safety"}},ensure_ascii=True), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    refresh(args.input,args.output,args.backup,args.apply)
