import pytest
from loaders.osm_display import display_ways


def document(tags):
    return {'elements': [
        {'type':'node','id':1,'lon':126.66,'lat':37.46},
        {'type':'node','id':2,'lon':126.67,'lat':37.47},
        {'type':'way','id':3,'nodes':[1,2],'tags':tags}]}


@pytest.mark.parametrize('tags', [
    {'highway':'motorway','foot':'no'}, {'highway':'trunk'},
    {'highway':'service','access':'private'}, {'highway':'construction'},
    {'highway':'pedestrian','area':'yes'}, {'highway':'footway'},
])
def test_display_does_not_apply_walking_access_filters(tags):
    ways = display_ways(document(tags))
    assert len(ways) == 1
    assert ways[0]['tags'] == tags
    assert ways[0]['geometry']['coordinates'][0] == [126.66,37.46]


def test_incomplete_geometry_is_not_silently_skipped():
    doc = document({'highway':'motorway'})
    doc['elements'].pop(0)
    with pytest.raises(KeyError):
        display_ways(doc)
