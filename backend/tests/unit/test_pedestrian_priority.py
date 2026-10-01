from dataclasses import replace
import pytest

from app.schemas.agent import RoutePreference
from app.services.routing.graph import RoadGraph, GraphNode, GraphEdge
from app.services.routing.astar import PathNotFoundError
from app.services.routing.pedestrian_priority import find_pedestrian_first_path, nonpreferred_distance
from app.services.routing.custom import find_custom_path
from app.services.routing.safety_cost import SafetyCostPolicy


def network(road_type='service', gap=False):
    g = RoadGraph()
    for n in range(1,6):
        g.add_node(GraphNode(n,0,0))
    # Two mapped crossings on the longer sidewalk vs an unrecorded road shortcut.
    for i,(s,t,d,h,c) in enumerate([
        (1,2,50,'footway',1),(2,4,50,'footway',2),
        (1,3,10,road_type,None),(3,4,10,road_type,None),
        (5,1,5,'service' if gap else 'footway',None),
    ]):
        g.add_edge(GraphEdge(i,str(i),None,s,t,d,50,50,0,50,((0,0),(0,0)),
            highway=h,sidewalk_confirmed=h=='footway',crossing_group=c,
            crossing_cost_units=1 if c else 0,pedestrian_version='osm-pedestrian-michuhol-v2',
            centreline_fallback=h=='secondary'))
    return g


@pytest.mark.parametrize('road_type',['service','residential','secondary'])
def test_crossing_avoidance_cannot_buy_carriageway_shortcut(road_type):
    g = network(road_type)
    for weight in (0,.5,1):
        p,base,limit,_ = find_custom_path(g,1,4,SafetyCostPolicy(1,0,crossing_weight=weight),[])
        assert p.total_distance_m == base == 100
        assert nonpreferred_distance(p.edges) == 0
        assert sum(e.crossing_cost_units for e in p.edges) == 2


def test_shortest_also_prefers_sidewalk_and_only_uses_unavoidable_gap():
    g = network(gap=True)
    p = find_pedestrian_first_path(g,5,4,lambda e:e.distance_m)
    assert p.total_distance_m == 105
    assert nonpreferred_distance(p.edges) == 5


def test_fewer_crossings_still_wins_between_pedestrian_paths():
    g = network('footway')
    p = find_custom_path(g,1,4,SafetyCostPolicy(1,0,crossing_weight=1),[])[0]
    assert p.total_distance_m == 20
    assert sum(e.crossing_cost_units for e in p.edges) == 0


def test_hard_stairs_constraint_remains_hard():
    g = network('footway')
    g.adjacency[1] = [replace(e,is_steps=True,highway='steps') for e in g.adjacency[1]]
    with pytest.raises(PathNotFoundError):
        find_custom_path(g,1,4,SafetyCostPolicy(1,0),[RoutePreference(factor='stairs_distance_m',direction='avoid')])


def test_directed_disconnected_and_same_node_cases():
    g = network()
    with pytest.raises(PathNotFoundError):
        find_pedestrian_first_path(g,4,1,lambda e:e.distance_m)
    assert find_pedestrian_first_path(g,1,1,lambda e:e.distance_m).edges == ()
