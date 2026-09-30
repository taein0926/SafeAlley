"""Only explicit OSM topology is trusted; proximity never creates a crossing."""
from collections import defaultdict

from preprocess.osm_roads import _is_walkable, _sidewalk_status, _walking_directions

VERSION = "osm-pedestrian-juan-v1"
MAJOR = {"primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link"}


def pedestrian_metadata(document: dict, roads: list[dict]) -> dict[int, dict]:
    ways = {e["id"]: e for e in document["elements"] if e["type"] == "way"}
    crossing_nodes = {e["id"] for e in document["elements"]
                      if e["type"] == "node" and e.get("tags", {}).get("highway") == "crossing"}
    updates = {}
    crossing_edges = []
    for road in roads:
        props = road["properties"]
        way = ways.get(props.get("osm_way_id"))
        if way is None:
            continue
        s, t = road["source_node_id"], road["target_node_id"]
        # Do not attach new geometry/tags to an old edge whose topology changed.
        pairs = set(zip(way["nodes"], way["nodes"][1:]))
        if (s, t) not in pairs and (t, s) not in pairs:
            continue
        tags = way.get("tags", {})
        highway = tags.get("highway")
        grade_separated = (tags.get("bridge", "no") not in {"no", "false", "0", ""}
                           or tags.get("tunnel", "no") not in {"no", "false", "0", ""}
                           or tags.get("layer", "0") != "0")
        is_crossing = tags.get("footway") == "crossing" and not grade_separated
        # Retain the existing OSM road network where separate sidewalks are missing.
        # Mark centre lines as incomplete crossing topology, never as zero crossings.
        allowed = _is_walkable(tags)
        forward, reverse = _walking_directions(tags)
        if (s, t) not in pairs:
            forward, reverse = reverse, forward
        updates[road["id"]] = {
            "version": VERSION, "allowed": allowed,
            "centreline_fallback": highway in MAJOR,
            "forward_allowed": forward, "reverse_allowed": reverse,
            "is_crossing": is_crossing, "crossing_group": None,
            "crossing_cost_units": 0.0,
            "crossing_node_ids": sorted({s, t} & crossing_nodes),
            "sidewalk": tags.get("footway") == "sidewalk",
            "sidewalk_confirmed": _sidewalk_status(tags) in {"confirmed", "dedicated_or_shared_space"},
            "basis": "OSM tags and shared node IDs; no field verification",
        }
        if is_crossing and allowed:
            crossing_edges.append(road)
    # Join split pieces, but stop at branches/sidewalk landings: an entire
    # intersection's connected crossing network must not count as one crossing.
    incident = defaultdict(set)
    landings = set()
    for road in roads:
        if updates.get(road["id"], {}).get("sidewalk"):
            landings.update((road["source_node_id"], road["target_node_id"]))
    for road in crossing_edges:
        for node in (road["source_node_id"], road["target_node_id"]):
            incident[node].add(road["id"])
    neighbors = defaultdict(set)
    for node, edges in incident.items():
        if len(edges) == 2 and node not in landings:
            a, b = edges
            neighbors[a].add(b)
            neighbors[b].add(a)
    groups = {}
    for road in crossing_edges:
        identity = road["id"]
        if identity in groups:
            continue
        component = {identity}
        stack = [identity]
        while stack:
            for other in neighbors[stack.pop()]:
                if other not in component:
                    component.add(other)
                    stack.append(other)
        groups.update({edge: min(component) for edge in component})
    lengths = defaultdict(float)
    for road in crossing_edges:
        lengths[groups[road["id"]]] += road["length_m"]
    for road in crossing_edges:
        group = groups[road["id"]]
        updates[road["id"]].update(
            crossing_group=group,
            crossing_cost_units=road["length_m"] / lengths[group],
        )
    return updates
