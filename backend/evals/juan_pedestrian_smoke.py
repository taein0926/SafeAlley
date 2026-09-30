"""Read-only local-data smoke test; no LLM, learning, or selection writes."""
import json
from datetime import time

from app.db.connection import connect_database
from app.repositories.place_repository import find_place
from app.schemas.agent import RouteOptimizationArguments
from app.services import route_ranking_service as ranking
from app.services.weather_service import RouteTimeContext
from app.services.route_service import get_custom_route, get_shortest_route, prepare_route


def run():
    ranking.resolve_route_time = lambda _: RouteTimeContext(time(21, 30), True, "fallback")
    for start, end in [("주안역", "인천사랑병원"), ("인천사랑병원", "석암초등학교")]:
        a, b = find_place(start), find_place(end)
        for crossing in (0, .5, 1):
            preferences = [dict(factor="distance_m", direction="minimize", weight=50),
                           dict(factor="safety_score", direction="maximize", weight=50)]
            arguments = RouteOptimizationArguments(
                origin={k: a[k] for k in ("longitude", "latitude")},
                destination={k: b[k] for k in ("longitude", "latitude")},
                source="osm", preferences=preferences, crossing_weight=crossing,
            )
            result = ranking.rank_route_candidates(arguments)
            assert {c["route_type"] for c in result["candidates"]} == {"shortest", "custom"}
            assert result["selected_route"] is not None
            summary = []
            for candidate in result["candidates"]:
                p = candidate["route"]["properties"]
                if p["centreline_fallback_distance_m"] > 0:
                    assert candidate["metrics"]["crosswalk_count"] is None
                summary.append({"type": candidate["route_type"], "distance": p["total_distance_m"],
                                "crossings": candidate["metrics"]["crosswalk_count"], "sidewalk_percent": p["sidewalk_coverage_percent"],
                                "coverage": p["pedestrian_metadata_coverage_percent"],
                                "snap": [p["start_snap_distance_m"],p["end_snap_distance_m"]]})
            print(json.dumps({"from": start, "to": end, "crossing_weight": crossing,
                              "routes": summary, "reason": result["recommendation_reason"]}, ensure_ascii=False), flush=True)
    with connect_database() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT ST_X(ST_Transform(ST_StartPoint(geom),4326)),ST_Y(ST_Transform(ST_StartPoint(geom),4326)),ST_X(ST_Transform(ST_EndPoint(geom),4326)),ST_Y(ST_Transform(ST_EndPoint(geom),4326)) FROM road_segments WHERE properties->'osm_pedestrian'->>'is_crossing'='true' ORDER BY length_m DESC LIMIT 1")
            x1, y1, x2, y2 = cur.fetchone()
            arguments = dict(start_longitude=x1, start_latitude=y1, end_longitude=x2, end_latitude=y2, source="osm")
            prepared = prepare_route(**arguments)
            context = RouteTimeContext(time(21, 30), True, "fallback")
            shortest = get_shortest_route(**arguments, prepared=prepared, time_context=context)
            custom = get_custom_route(prepared=prepared, time_context=context, preferences=[], crossing_weight=1)
            p = shortest["properties"]
            assert p["crossing_data_available"] and p["total_crosswalk_count"] >= 1
            c = custom["properties"]
            assert c["total_distance_m"] <= c["crossing_distance_limit_m"] + .01
            print("REGISTERED_CROSSING", json.dumps({"shortest_m": p["total_distance_m"], "crossings": p["total_crosswalk_count"], "custom_m": c["total_distance_m"], "penalty": sum(s["crossing_penalty"] for s in c["road_segments"]), "detour_limited": c["crossing_detour_limited"]}))
            cur.execute("SELECT count(*),md5(string_agg(concat_ws('|',id,source_id,source_node_id,target_node_id,ST_AsEWKB(geom),streetlight_score,cctv_score,help_point_score,safety_score,properties->>'is_steps',properties->'pedestrian_reference'),';' ORDER BY id)) FROM road_segments WHERE source='osm'")
            print("PRESERVATION", cur.fetchone())


if __name__ == "__main__":
    run()
