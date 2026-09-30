from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.schemas.agent import RoutePreference
from app.services.routing.astar import PathNotFoundError
from app.services.routing.custom import custom_policy, find_custom_path
from app.services.routing.graph import GraphEdge, GraphNode, RoadGraph
from app.services.routing.safety_cost import SafetyCostPolicy


def graph(detour=26, *, stairs=False):
    g = RoadGraph()
    for n in (1,2,3,4):
        g.add_node(GraphNode(n,0,0))
    for i,(s,t,d,c) in enumerate([(1,2,10,True),(2,4,10,True),(1,3,detour/2,False),(3,4,detour/2,False)]):
        g.add_edge(GraphEdge(i,str(i),None,s,t,d,80,50,0,60,((0,0),(0,0)),
                            is_steps=stairs and c,crossing_group=2 if c else None,
                            crossing_cost_units=.5 if c else 0,pedestrian_version="osm-pedestrian-juan-v1"))
    return g


def test_crossing_avoidance_changes_search_not_only_candidate_ranking():
    g=graph()
    low=find_custom_path(g,1,4,SafetyCostPolicy(1,0),[])[0]
    high=find_custom_path(g,1,4,SafetyCostPolicy(1,0,crossing_weight=1),[])[0]
    assert low.total_distance_m == 20
    assert high.total_distance_m == 26
    assert all(e.crossing_group is None for e in high.edges)


def test_crossing_detour_is_bounded_but_hard_avoidance_is_not_relaxed():
    g=graph(40)
    result,baseline,limit,limited=find_custom_path(g,1,4,SafetyCostPolicy(1,0,crossing_weight=1),[])
    assert (result.total_distance_m,baseline,limit,limited)==(20,20,26,True)
    hard=[RoutePreference(factor="crosswalk_count",direction="avoid")]
    assert find_custom_path(g,1,4,SafetyCostPolicy(1,0,crossing_weight=1),hard)[0].total_distance_m == 40


def test_no_path_never_silently_relaxes_hard_stairs_constraint():
    g=graph(stairs=True)
    hard=[RoutePreference(factor="stairs_distance_m",direction="avoid")]
    assert find_custom_path(g,1,4,SafetyCostPolicy(1,0),hard)[0].total_distance_m==26
    g.adjacency[1]=g.adjacency[1][:1]
    with pytest.raises(PathNotFoundError):
        find_custom_path(g,1,4,SafetyCostPolicy(1,0),hard)


def test_slider_strength_and_night_facility_weights_are_used_during_search():
    settings=SimpleNamespace(safe_route_risk_weight=5,safety_cctv_weight=.4,safety_help_point_weight=.2)
    prefs=[RoutePreference(factor="safety_score",direction="maximize",weight=75),
           RoutePreference(factor="distance_m",direction="minimize",weight=50),
           RoutePreference(factor="crosswalk_count",direction="minimize",weight=50)]
    policy=custom_policy(prefs,stairs_weight=.5,crossing_weight=.5,is_night=True,settings=settings)
    assert policy.risk_weight==3
    assert policy.crossing_weight==.5
    assert policy.stairs_weight==.5
    edge=graph().neighbors(1)[0]
    assert policy.breakdown(edge).crossing_penalty==20
    assert replace(policy,streetlight_included=False).effective_safety_score(edge)==pytest.approx(100/3)


def test_unknown_centreline_is_not_a_free_crossing_avoidance_shortcut():
    edge = replace(graph().neighbors(1)[0], crossing_group=None, crossing_cost_units=0, centreline_fallback=True)
    low = SafetyCostPolicy(1, 0, pedestrian_weight=.5)
    high = replace(low, crossing_weight=1)
    assert high.edge_cost(edge) > low.edge_cost(edge)
    assert high.breakdown(edge).crossing_penalty == 0  # not a fabricated crossing


def test_node_only_marker_does_not_penalize_sidewalk_passby():
    edge=replace(graph().neighbors(1)[0],crossing_group=None,crossing_cost_units=0,crossing_node_ids=(42,))
    assert SafetyCostPolicy(1,0,crossing_weight=1).breakdown(edge).crossing_penalty==0


def test_natural_language_crossing_avoidance_is_soft_unless_explicitly_none():
    from app.schemas.agent import ParsedRouteIntent
    from app.services.local_llm_service import _preserve_crossing_preference
    for text, direction in [("건널목은 피해서 안내해줘", "minimize"),
                            ("횡단보도 없이 가줘", "avoid"),
                            ("건널목을 적게 지나가줘", "minimize")]:
        intent = ParsedRouteIntent(preferences=[])
        _preserve_crossing_preference(text, intent)
        assert [(p.factor, p.direction) for p in intent.preferences] == [("crosswalk_count",direction)]


def test_connected_snapping_does_not_create_edges_or_ignore_distance_limit():
    from app.services.routing.snapping import connected_node_pair
    g=graph()
    # Coordinate-only test; the existing path must remain unchanged.
    before = sum(map(len,g.adjacency.values()))
    result = connected_node_pair(g,(0,0),(0,0),10)
    assert len(result)==2
    assert sum(map(len,g.adjacency.values()))==before
    with pytest.raises(PathNotFoundError):
        connected_node_pair(g,(126,37),(126,37),10)
