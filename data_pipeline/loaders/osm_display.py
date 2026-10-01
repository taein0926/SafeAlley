"""Load all collected highway ways for display only; never change routing roads."""
import argparse
import json
from math import isfinite
from pathlib import Path

from psycopg.types.json import Jsonb
from loaders.postgis import database_connection
from loaders.osm_refresh import validate_snapshot


def display_ways(document):
    nodes = {e['id']: [e['lon'], e['lat']] for e in document['elements']
             if e['type'] == 'node' and 'lon' in e and 'lat' in e}
    ways = {}
    for e in document['elements']:
        if e['type'] != 'way' or not e.get('tags', {}).get('highway'):
            continue
        coordinates = [nodes[n] for n in e['nodes']]
        if len(coordinates) < 2 or any(not (isfinite(x) and isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90) for x,y in coordinates):
            raise ValueError(f"Invalid highway geometry: {e['id']}")
        ways[e['id']] = {'id': e['id'], 'tags': e['tags'],
                         'geometry': {'type': 'LineString', 'coordinates': coordinates}}
    if not ways:
        raise ValueError('No highway ways in snapshot')
    return list(ways.values())


def load_display_roads(path):
    document = json.loads(path.read_text(encoding='utf-8'))
    metadata = json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'))
    timestamp = validate_snapshot(document, metadata)
    ways = display_ways(document)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('LOCK TABLE osm_display_roads IN SHARE ROW EXCLUSIVE MODE')
            for way in ways:
                cursor.execute("""
                    INSERT INTO osm_display_roads (osm_way_id,tags,geom,snapshot_at)
                    VALUES (%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),5179),%s)
                    ON CONFLICT(osm_way_id) DO UPDATE SET tags=EXCLUDED.tags,
                        geom=EXCLUDED.geom,snapshot_at=EXCLUDED.snapshot_at
                """, (way['id'],Jsonb(way['tags']),json.dumps(way['geometry']),timestamp))
            cursor.execute('DELETE FROM osm_display_roads WHERE NOT(osm_way_id=ANY(%s))',
                           ([w['id'] for w in ways],))
    print(json.dumps({'display_ways':len(ways),'snapshot_at':timestamp,'routing_changed':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    load_display_roads(parser.parse_args().input)
