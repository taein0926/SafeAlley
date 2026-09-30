"""Snap to connected existing OSM nodes, never invent pedestrian connections."""
from math import asin, cos, radians, sin, sqrt

from app.services.routing.astar import PathNotFoundError, find_path


def metres(a, b):
    lon1, lat1, lon2, lat2 = map(radians, (*a, *b))
    return 12742000 * asin(min(1, sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2)))


def connected_node_pair(graph, origin, destination, max_distance):
    coordinates = {}
    adjacent = {n: set() for n in graph.nodes}
    for edges in graph.adjacency.values():
        for edge in edges:
            coordinates[edge.from_node_id] = edge.coordinates[0]
            coordinates[edge.to_node_id] = edge.coordinates[-1]
            adjacent[edge.from_node_id].add(edge.to_node_id)
            adjacent[edge.to_node_id].add(edge.from_node_id)
    components = {}
    for node in adjacent:
        if node in components:
            continue
        components[node] = node
        todo = [node]
        while todo:
            for other in adjacent[todo.pop()]:
                if other not in components:
                    components[other] = node
                    todo.append(other)
    nearest = []
    for point in (origin, destination):
        per_component = {}
        for node, coordinate in coordinates.items():
            distance = metres(point, coordinate)
            component = components[node]
            if distance <= max_distance and (component not in per_component or distance < per_component[component][0]):
                per_component[component] = (distance, node)
        nearest.append(per_component)
    pairs = sorted((nearest[0][c][0] + nearest[1][c][0], nearest[0][c], nearest[1][c])
                   for c in nearest[0].keys() & nearest[1].keys())
    for _, start, end in pairs:
        try:
            find_path(graph, start[1], end[1], lambda e: e.distance_m, 1)
        except PathNotFoundError:
            continue
        return [(node, coordinates[node], distance) for distance, node in (start,end)]
    raise PathNotFoundError("No connected OSM pedestrian nodes within the snapping limit")
