"""Image Tile Merger node."""

from __future__ import annotations

import logging
from io import BytesIO
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
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


def _parse_manifest(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    msg = f"manifest_json must be a dict, got {type(value).__name__}"
    raise ValueError(msg)


class ImageTileMerger(DataNode):
    """Merge tiles back into a single image using a manifest from Image Tile Splitter."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterJson(
                name="manifest_json",
                tooltip="Tile grid manifest from an Image Tile Splitter node.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Manifest JSON"},
            )
        )

        seam_blur_param = ParameterInt(
            name="seam_blur_px",
            tooltip="Blur radius applied at tile seams (0 = disabled).",
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Seam Blur (px)", "step": 1},
        )
        seam_blur_param.add_child(Slider(min_val=0, max_val=32))
        self.add_parameter(seam_blur_param)

        self.add_parameter(
            ParameterImage(
                name="merged_image",
                tooltip="Reassembled image.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Merged Image", "expander": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="width",
                type="int",
                output_type="int",
                tooltip="Output image width in pixels.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Width"},
            )
        )

        self.add_parameter(
            Parameter(
                name="height",
                type="int",
                output_type="int",
                tooltip="Output image height in pixels.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Height"},
            )
        )

        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename="merged.png",
        )
        self._output_file.add_parameter()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def process(self) -> None:
        self._process_sync()

    async def aprocess(self) -> None:
        manifest_value = self.get_parameter_value("manifest_json")
        seam_blur_px = int(self.get_parameter_value("seam_blur_px") or 0)

        manifest = _parse_manifest(manifest_value)

        # Tile loading + canvas assembly run in a worker thread (disk I/O + PIL).
        result_bytes, w, h = await async_utils.to_thread(self._reassemble, manifest, seam_blur_px)

        dest = self._output_file.build_file()
        saved = await dest.awrite_bytes(result_bytes)
        artifact = ImageUrlArtifact(saved.location)

        self._publish_outputs(artifact, w, h, len(manifest["tiles"]))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _process_sync(self) -> None:
        manifest_value = self.get_parameter_value("manifest_json")
        seam_blur_px = int(self.get_parameter_value("seam_blur_px") or 0)

        manifest = _parse_manifest(manifest_value)
        result_bytes, w, h = self._reassemble(manifest, seam_blur_px)

        dest = self._output_file.build_file()
        saved = dest.write_bytes(result_bytes)
        artifact = ImageUrlArtifact(saved.location)

        self._publish_outputs(artifact, w, h, len(manifest["tiles"]))

    def _reassemble(self, manifest: dict[str, Any], seam_blur_px: int) -> tuple[bytes, int, int]:
        """Load all tiles and compose the final image. Runs in a worker thread."""
        original_width: int = manifest["original_width"]
        original_height: int = manifest["original_height"]
        rows: int = manifest["rows"]
        columns: int = manifest["columns"]
        tile_size: int = manifest["tile_size"]

        canvas = Image.new("RGBA", (columns * tile_size, rows * tile_size), (0, 0, 0, 0))

        for tile in manifest["tiles"]:
            tile_data = File(tile["url"]).read_bytes()
            tile_img = Image.open(BytesIO(tile_data)).convert("RGBA")
            canvas.paste(tile_img, (tile["x"], tile["y"]))

        result = canvas.crop((0, 0, original_width, original_height))

        if seam_blur_px > 0:
            result = self._soften_seams(result, manifest, seam_blur_px)

        buf = BytesIO()
        result.convert("RGB").save(buf, format="PNG")
        return buf.getvalue(), result.width, result.height

    def _publish_outputs(self, artifact: ImageUrlArtifact, w: int, h: int, tile_count: int) -> None:
        self.parameter_output_values["merged_image"] = artifact
        self.parameter_output_values["width"] = w
        self.parameter_output_values["height"] = h
        logger.info("Merged %d tiles into %dx%d image", tile_count, w, h)

    def _soften_seams(self, image: Image.Image, manifest: dict[str, Any], blur_px: int) -> Image.Image:
        """Apply a narrow Gaussian blur mask along every internal tile boundary."""
        import numpy as np

        tile_size: int = manifest["tile_size"]
        rows: int = manifest["rows"]
        columns: int = manifest["columns"]
        w, h = image.size

        blurred = image.filter(ImageFilter.GaussianBlur(radius=blur_px))
        half = max(1, blur_px)
        mask_arr = np.zeros((h, w), dtype=np.uint8)

        for col in range(1, columns):
            x = col * tile_size
            mask_arr[:, max(0, x - half) : min(w, x + half)] = 255

        for row in range(1, rows):
            y = row * tile_size
            mask_arr[max(0, y - half) : min(h, y + half), :] = 255

        mask = Image.fromarray(mask_arr, mode="L")
        return Image.composite(blurred, image, mask)
