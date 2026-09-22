from app.repositories.pedestrian_reference_repository import list_pedestrian_bridges


def get_pedestrian_bridge_collection() -> dict:
    bridges = list_pedestrian_bridges()
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
