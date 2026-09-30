"""Additive pedestrian metadata load. Never replace roads or safety scores."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from collectors.osm_pedestrian import collect_pedestrian_tags
from loaders.postgis import database_connection
from preprocess.osm_pedestrian import pedestrian_metadata


def load_pedestrian_metadata(document: dict, backup_dir: Path) -> dict:
    with database_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, source_node_id, target_node_id, length_m, properties FROM road_segments WHERE source='osm' FOR UPDATE")
            roads = cur.fetchall()
            updates = pedestrian_metadata(document, roads)
            if not updates:
                raise ValueError("No existing OSM edges matched; database unchanged")
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
            backup.write_text(json.dumps([
                {"id": r["id"], "osm_pedestrian": r["properties"].get("osm_pedestrian")}
                for r in roads if r["id"] in updates
            ]), encoding="utf-8")
            for identity, metadata in updates.items():
                cur.execute("UPDATE road_segments SET properties=jsonb_set(properties, '{osm_pedestrian}', %s) WHERE id=%s", (Jsonb(metadata), identity))
    return {
        "updated_edges": len(updates), "crossing_edges": sum(m["is_crossing"] for m in updates.values()),
        "sidewalk_edges": sum(m["sidewalk"] for m in updates.values()),
        "excluded_restricted_edges": sum(not m["allowed"] for m in updates.values()),
        "backup": str(backup),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("raw/osm/juan_pedestrian.json"))
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    document = collect_pedestrian_tags(args.input) if args.collect else json.loads(args.input.read_text(encoding="utf-8"))
    if args.apply:
        print(json.dumps(load_pedestrian_metadata(document, Path("raw/osm/pedestrian_backups")), ensure_ascii=False))
    else:
        print(json.dumps({"elements": len(document["elements"]), "scope": document.get("safealley_scope")}))
