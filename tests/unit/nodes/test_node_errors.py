from __future__ import annotations

import pytest
from griptape_nodes.exe_types.core_types import NodeError

from griptape_nodes_library_image_tiles.image_tile_merger import ImageTileMerger, _parse_manifest
from griptape_nodes_library_image_tiles.image_tile_splitter import ImageTileSplitter
from griptape_nodes_library_image_tiles.seam_blend_360 import SeamBlend360
from griptape_nodes_library_image_tiles.to_latlong_2to1 import ToLatLong2to1


def test_manifest_must_be_a_dict() -> None:
    with pytest.raises(NodeError, match="Manifest JSON") as exc:
        _parse_manifest("not a dict")
    assert exc.value.fields == {"parameter": "manifest_json", "received_type": "str"}


def test_manifest_missing_keys_are_named() -> None:
    with pytest.raises(NodeError, match="missing rows, columns"):
        _parse_manifest({"original_width": 1, "original_height": 1, "tile_size": 1, "tiles": []})


def test_valid_manifest_passes_through() -> None:
    manifest = {"original_width": 1, "original_height": 1, "rows": 1, "columns": 1, "tile_size": 1, "tiles": []}
    assert _parse_manifest(manifest) is manifest


@pytest.mark.parametrize("node_cls", [ImageTileSplitter, SeamBlend360, ToLatLong2to1])
@pytest.mark.parametrize("value", [None, "", {"value": ""}])
def test_missing_image_is_a_node_error(node_cls: type, value: object) -> None:
    node = object.__new__(node_cls)
    with pytest.raises(NodeError, match="Connect an image to 'Image'") as exc:
        node._load_pil(value)
    assert exc.value.fields == {"parameter": "image"}


@pytest.mark.parametrize("node_cls", [ImageTileSplitter, SeamBlend360, ToLatLong2to1])
def test_unreadable_image_is_a_node_error(node_cls: type, tmp_path) -> None:
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    node = object.__new__(node_cls)
    with pytest.raises(NodeError, match="Could not read the image") as exc:
        node._load_pil({"value": str(bad)})
    assert exc.value.fields is not None
    assert exc.value.fields["parameter"] == "image"


def test_tile_size_must_be_positive() -> None:
    node = object.__new__(ImageTileSplitter)
    with pytest.raises(NodeError, match="'Tile Size' must be greater than 0. It's set to -4"):
        node._compute_tile_data({"value": "x"}, -4, False)


def test_unknown_blend_mode() -> None:
    node = object.__new__(SeamBlend360)
    with pytest.raises(NodeError, match="'Blend Mode' is set to 'bogus'"):
        node._make_alpha_curve(4, "bogus")


def test_merger_unreadable_tile(tmp_path) -> None:
    node = object.__new__(ImageTileMerger)
    manifest = {
        "original_width": 4,
        "original_height": 4,
        "rows": 1,
        "columns": 1,
        "tile_size": 4,
        "tiles": [{"row": 0, "col": 0, "x": 0, "y": 0, "url": str(tmp_path / "missing.png")}],
    }
    with pytest.raises(NodeError, match="row 0, column 0"):
        node._reassemble(manifest, 0)
