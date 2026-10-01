import json
import numpy as np
import pytest

from analysis import streetlight_heatmap as heatmap


def test_kernel_is_shared_across_tile_boundary_and_center_is_visible():
    # longitude 0 is precisely an XYZ tile boundary.
    tiles = heatmap.tile_index([(0, 0)], 17)
    assert len(tiles) == 4
    left = heatmap.render_tile(65535, 65535, tiles[(65535, 65535)])
    right = heatmap.render_tile(65536, 65535, tiles[(65536, 65535)])
    np.testing.assert_array_equal(left[:, -1], right[:, 0])
    assert left[:, :, 3].max() >= 65
    assert left[:, :, 3].max() <= 150
    assert heatmap.png_rgba(left).startswith(b"\x89PNG\r\n\x1a\n")


def test_build_is_versioned_reproducible_and_reuses_existing_tiles(tmp_path, monkeypatch):
    monkeypatch.setattr(heatmap, "MIN_ZOOM", 16)
    monkeypatch.setattr(heatmap, "MAX_ZOOM", 16)
    points = [(126.66, 37.46), (126.661, 37.461)]
    manifest = heatmap.build_tiles(points, tmp_path)
    tile = next((tmp_path / manifest["version"]).rglob("*.png"))
    before = tile.stat().st_mtime_ns
    assert heatmap.build_tiles(list(reversed(points)), tmp_path) == manifest
    assert tile.stat().st_mtime_ns == before
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    changed = heatmap.build_tiles(points + [(126.662, 37.462)], tmp_path)
    assert changed["version"] != manifest["version"]
    assert tile.exists()  # Older browsers retain immutable URLs.


def test_bad_input_does_not_replace_previous_manifest(tmp_path):
    marker = tmp_path / "manifest.json"
    marker.write_text("previous")
    for points in [[], [(float("nan"), 37)], [(126, 90)]]:
        with pytest.raises(ValueError):
            heatmap.build_tiles(points, tmp_path)
    assert marker.read_text() == "previous"
