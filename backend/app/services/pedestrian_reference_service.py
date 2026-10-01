from app.repositories.pedestrian_reference_repository import list_pedestrian_bridges
from app.services.road_service import parse_bbox


def get_pedestrian_bridge_collection(bbox_value: str | None = None) -> dict:
    bridges = list_pedestrian_bridges(parse_bbox(bbox_value))
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": row["id"], "geometry": row["geometry"],
             "properties": {**row["properties"], "kind": "bridge",
                            "routing_connected": row["routing_connected"]}}
            for row in bridges
        ],
        "metadata": {"count": len(bridges), "crs": "EPSG:4326",
                     "routing_connected_count": sum(row["routing_connected"] for row in bridges)},
    }
