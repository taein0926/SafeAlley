from copy import deepcopy

from preprocess.osm_pedestrian import pedestrian_metadata


def road(identity, way, start, end, length=10):
    return dict(id=identity, source_node_id=start, target_node_id=end, length_m=length,
                properties={"osm_way_id": way, "safety_score": 83, "is_steps": False})


def way(identity, nodes, **tags):
    return dict(id=identity, type="way", nodes=nodes, tags=tags)


def test_split_crossing_counts_once_and_has_fixed_total_penalty():
    doc = {"elements": [way(1, [1,2,3], highway="footway", footway="crossing"),
                        way(2, [3,4], highway="footway", footway="crossing")]}
    roads = [road(1,1,1,2), road(2,1,2,3), road(3,2,3,4)]
    before = deepcopy(roads)
    result = pedestrian_metadata(doc, roads)
    assert len({m["crossing_group"] for m in result.values()}) == 1
    assert sum(m["crossing_cost_units"] for m in result.values()) == 1
    assert roads == before


def test_crossings_are_separate_at_branches_and_sidewalk_landings():
    tags = dict(highway="footway", footway="crossing")
    doc = {"elements": [way(1, [1, 2], **tags), way(2, [2, 3], **tags),
                        way(3, [2, 4], **tags)]}
    roads = [road(1, 1, 1, 2), road(2, 2, 2, 3), road(3, 3, 2, 4)]
    result = pedestrian_metadata(doc, roads)
    assert len({m["crossing_group"] for m in result.values()}) == 3
    doc["elements"][2]["tags"]["footway"] = "sidewalk"
    result = pedestrian_metadata(doc, roads)
    assert result[1]["crossing_group"] != result[2]["crossing_group"]
    assert result[1]["crossing_cost_units"] == result[2]["crossing_cost_units"] == 1


def test_crossing_point_is_not_a_crossing_for_a_sidewalk_passby():
    doc = {"elements": [way(1,[1,2],highway="footway",footway="sidewalk"),
                        dict(id=2,type="node",tags={"highway":"crossing"})]}
    m = pedestrian_metadata(doc,[road(1,1,1,2)])[1]
    assert m["crossing_node_ids"] == [2]
    assert m["sidewalk"] and m["sidewalk_confirmed"]
    assert not m["is_crossing"] and m["crossing_group"] is None


def test_centreline_is_marked_incomplete_and_no_edge_is_invented():
    doc = {"elements": [way(1,[1,2],highway="secondary"),
                        way(2,[3,4],highway="footway",footway="sidewalk")]}
    result = pedestrian_metadata(doc,[road(1,1,1,2),road(2,2,3,99)])
    assert result[1]["allowed"]
    assert result[1]["centreline_fallback"]
    assert 2 not in result


def test_bridge_and_access_restrictions_preserved():
    doc = {"elements": [way(1,[1,2],highway="footway",footway="crossing",bridge="yes"),
                        way(2,[2,3],highway="footway",foot="no")]}
    result = pedestrian_metadata(doc,[road(1,1,1,2),road(2,2,2,3)])
    assert not result[1]["is_crossing"]
    assert not result[2]["allowed"]
