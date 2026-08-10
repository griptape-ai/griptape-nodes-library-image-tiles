"""Image Tile Splitter node."""

from __future__ import annotations

import logging
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Any

from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_json import ParameterJson
from griptape_nodes.files.file import File
from griptape_nodes.traits.slider import Slider
from griptape_nodes.utils import async_utils
from PIL import Image

logger = logging.getLogger(__name__)

# Named tuple-style dataclass would be overkill for 8 fields used in one place.
type _TileData = tuple[str, bytes, int, int, int, int, int, int]  # name, png_bytes, row, col, x, y, w, h


class ImageTileSplitter(DataNode):
    """Split an image into square tiles and emit a manifest JSON string for reassembly."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Image to split into tiles.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image", "expander": True},
                hide_property=True,
            )
        )

        tile_size_param = ParameterInt(
            name="tile_size",
            tooltip="Square tile size in pixels.",
            default_value=512,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Tile Size", "step": 64},
        )
        tile_size_param.add_child(Slider(min_val=64, max_val=2048))
        self.add_parameter(tile_size_param)

        self.add_parameter(
            Parameter(
                name="pad_to_fit",
                type="bool",
                default_value=True,
                tooltip="Pad image to a full tile grid. The merger crops back to the original size.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Pad to Fit"},
            )
        )

        self.add_parameter(
            Parameter(
                name="tile_count",
                type="int",
                output_type="int",
                tooltip="Total number of tiles generated.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Tile Count"},
            )
        )

        self.add_parameter(
            Parameter(
                name="rows",
                type="int",
                output_type="int",
                tooltip="Number of tile rows.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Rows"},
            )
        )

        self.add_parameter(
            Parameter(
                name="columns",
                type="int",
                output_type="int",
                tooltip="Number of tile columns.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Columns"},
            )
        )

        self.add_parameter(
            ParameterJson(
                name="manifest_json",
                tooltip="Tile grid metadata and tile URLs. Connect to an Image Tile Merger.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Manifest JSON"},
            )
        )

        self._tile_file = ProjectFileParameter(
            node=self,
            name="tile_file",
            default_filename="tiles/tile.png",
        )
        self._tile_file.add_parameter()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def process(self) -> None:
        self._process_sync()

    async def aprocess(self) -> None:
        image_value = self.get_parameter_value("image")
        tile_size = int(self.get_parameter_value("tile_size") or 512)
        pad_to_fit = bool(self.get_parameter_value("pad_to_fit"))
        user_stem = Path(self.get_parameter_value("tile_file") or self._tile_file._default_filename).stem

        tiles_data, original_w, original_h, rows, cols = await async_utils.to_thread(
            self._compute_tile_data, image_value, tile_size, pad_to_fit
        )

        manifest_tiles: list[dict[str, Any]] = []
        for _, tile_bytes, row, col, x, y, w, h in tiles_data:
            dest = self._tile_file.build_file(file_name_base=f"{user_stem}_r{row:04d}_c{col:04d}")
            saved = await dest.awrite_bytes(tile_bytes)
            artifact = ImageUrlArtifact(saved.location)
            manifest_tiles.append({"row": row, "col": col, "x": x, "y": y, "width": w, "height": h, "url": artifact.value})

        self._publish_outputs(manifest_tiles, tile_size, pad_to_fit, original_w, original_h, rows, cols)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _process_sync(self) -> None:
        image_value = self.get_parameter_value("image")
        tile_size = int(self.get_parameter_value("tile_size") or 512)
        pad_to_fit = bool(self.get_parameter_value("pad_to_fit"))
        user_stem = Path(self.get_parameter_value("tile_file") or self._tile_file._default_filename).stem

        tiles_data, original_w, original_h, rows, cols = self._compute_tile_data(image_value, tile_size, pad_to_fit)

        manifest_tiles: list[dict[str, Any]] = []
        for _, tile_bytes, row, col, x, y, w, h in tiles_data:
            dest = self._tile_file.build_file(file_name_base=f"{user_stem}_r{row:04d}_c{col:04d}")
            saved = dest.write_bytes(tile_bytes)
            artifact = ImageUrlArtifact(saved.location)
            manifest_tiles.append({"row": row, "col": col, "x": x, "y": y, "width": w, "height": h, "url": artifact.value})

        self._publish_outputs(manifest_tiles, tile_size, pad_to_fit, original_w, original_h, rows, cols)

    def _compute_tile_data(
        self, image_value: Any, tile_size: int, pad_to_fit: bool
    ) -> tuple[list[_TileData], int, int, int, int]:
        """Load the image and produce PNG bytes for every tile. Runs in a worker thread."""
        if tile_size <= 0:
            msg = "tile_size must be greater than 0"
            raise ValueError(msg)

        src = self._load_pil(image_value).convert("RGBA")
        original_width, original_height = src.size

        columns = ceil(original_width / tile_size)
        rows = ceil(original_height / tile_size)

        if pad_to_fit:
            canvas = Image.new("RGBA", (columns * tile_size, rows * tile_size), (0, 0, 0, 0))
            canvas.paste(src, (0, 0))
            working = canvas
        else:
            working = src

        working_w, working_h = working.size
        tiles: list[_TileData] = []

        for row in range(rows):
            for col in range(columns):
                x = col * tile_size
                y = row * tile_size
                right = min(x + tile_size, working_w)
                bottom = min(y + tile_size, working_h)
                if right <= x or bottom <= y:
                    continue
                tile = working.crop((x, y, right, bottom))
                buf = BytesIO()
                tile.save(buf, format="PNG")
                tiles.append((f"tile_r{row:04d}_c{col:04d}.png", buf.getvalue(), row, col, x, y, right - x, bottom - y))

        return tiles, original_width, original_height, rows, columns

    def _publish_outputs(
        self,
        manifest_tiles: list[dict[str, Any]],
        tile_size: int,
        pad_to_fit: bool,
        original_w: int,
        original_h: int,
        rows: int,
        cols: int,
    ) -> None:
        manifest = {
            "tile_size": tile_size,
            "pad_to_fit": pad_to_fit,
            "original_width": original_w,
            "original_height": original_h,
            "rows": rows,
            "columns": cols,
            "tile_count": len(manifest_tiles),
            "tiles": manifest_tiles,
        }
        self.parameter_output_values["manifest_json"] = manifest
        self.parameter_output_values["tile_count"] = len(manifest_tiles)
        self.parameter_output_values["rows"] = rows
        self.parameter_output_values["columns"] = cols
        logger.info("Split %dx%d into %d tiles (%d rows × %d cols)", original_w, original_h, len(manifest_tiles), rows, cols)

    def _load_pil(self, value: Any) -> Image.Image:
        if isinstance(value, dict):
            url = value.get("value", "")
        elif hasattr(value, "value"):
            url = value.value
        else:
            url = str(value)
        if not url:
            msg = "No image URL provided"
            raise ValueError(msg)
        return Image.open(BytesIO(File(url).read_bytes()))
