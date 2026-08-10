"""360 Seam Blend node — blend the left/right seam of a panoramic image."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import numpy as np
from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

BLEND_MODES = ["cosine", "linear", "smooth"]


class SeamBlend360(DataNode):
    """Blend the left/right seam of a panoramic equirectangular image."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Panoramic equirectangular image to blend.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image", "expander": True},
                hide_property=True,
            )
        )

        blend_width_param = ParameterInt(
            name="blend_width",
            tooltip="Width in pixels of the blend zone at the left/right seam.",
            default_value=16,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Blend Width (px)", "step": 1},
        )
        blend_width_param.add_child(Slider(min_val=1, max_val=256))
        self.add_parameter(blend_width_param)

        self.add_parameter(
            ParameterString(
                name="blend_mode",
                tooltip="Curve shape for blending across the seam zone.",
                default_value="cosine",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=BLEND_MODES)},
                ui_options={"display_name": "Blend Mode"},
            )
        )

        seam_blur_radius_param = ParameterInt(
            name="seam_blur_radius",
            tooltip="Gaussian blur radius applied near the seam (0 = disabled).",
            default_value=2,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Seam Blur Radius", "step": 1},
        )
        seam_blur_radius_param.add_child(Slider(min_val=0, max_val=32))
        self.add_parameter(seam_blur_radius_param)

        seam_blur_mix_param = ParameterFloat(
            name="seam_blur_mix",
            tooltip="How much of the blurred image to mix near the seam (0 = none, 1 = full).",
            default_value=0.35,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Seam Blur Mix"},
        )
        seam_blur_mix_param.add_child(Slider(min_val=0.0, max_val=1.0))
        self.add_parameter(seam_blur_mix_param)

        self.add_parameter(
            ParameterImage(
                name="output_image",
                tooltip="Seam-blended panoramic image.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Output Image", "expander": True},
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

        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                type="float",
                output_type="float",
                tooltip="Output width / height ratio.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Aspect Ratio"},
            )
        )

        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename="seam_blend.png",
        )
        self._output_file.add_parameter()

    def process(self) -> None:
        image_value = self.get_parameter_value("image")
        blend_width = max(1, int(self.get_parameter_value("blend_width") or 16))
        blend_mode = str(self.get_parameter_value("blend_mode") or "cosine").strip().lower()
        seam_blur_radius = max(0, int(self.get_parameter_value("seam_blur_radius") or 0))
        seam_blur_mix = max(0.0, min(1.0, float(self.get_parameter_value("seam_blur_mix") or 0.0)))

        src = self._load_pil(image_value).convert("RGB")
        arr = np.asarray(src, dtype=np.float32)

        arr = self._blend_edges(arr, blend_width, blend_mode)

        if seam_blur_radius > 0 and seam_blur_mix > 0.0:
            arr = self._apply_seam_blur(arr, seam_blur_radius, seam_blur_mix, blend_width)

        result = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")

        buf = BytesIO()
        result.save(buf, format="PNG")

        dest = self._output_file.build_file()
        saved = dest.write_bytes(buf.getvalue())
        artifact = ImageUrlArtifact(saved.location)

        self.parameter_output_values["output_image"] = artifact
        self.parameter_output_values["width"] = result.width
        self.parameter_output_values["height"] = result.height
        self.parameter_output_values["aspect_ratio"] = result.width / max(1, result.height)

    def _blend_edges(self, arr: np.ndarray, blend_width: int, blend_mode: str) -> np.ndarray:
        """Average left-edge and mirrored right-edge pixels across the blend zone."""
        h, w = arr.shape[:2]
        bw = min(blend_width, w // 4)
        result = arr.copy()

        alphas = self._make_alpha_curve(bw, blend_mode)

        for i in range(bw):
            alpha = alphas[i]
            left_col = arr[:, i, :]
            right_col = arr[:, w - 1 - i, :]
            blended = alpha * left_col + (1.0 - alpha) * right_col
            result[:, i, :] = blended
            result[:, w - 1 - i, :] = blended

        return result

    def _make_alpha_curve(self, bw: int, blend_mode: str) -> np.ndarray:
        t = np.linspace(0.0, 1.0, bw, dtype=np.float32)
        match blend_mode:
            case "cosine":
                return (0.5 * (1.0 + np.cos(np.pi * t))).astype(np.float32)
            case "linear":
                return (1.0 - t).astype(np.float32)
            case "smooth":
                return (1.0 - (3.0 * t**2 - 2.0 * t**3)).astype(np.float32)
            case _:
                msg = f"Unknown blend_mode: {blend_mode!r}"
                raise ValueError(msg)

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

    def _apply_seam_blur(
        self,
        arr: np.ndarray,
        blur_radius: int,
        mix: float,
        blend_width: int,
    ) -> np.ndarray:
        """Mix a Gaussian-blurred version near the seam edges."""
        src_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
        blurred = np.asarray(src_img.filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.float32)

        h, w = arr.shape[:2]
        zone = min(blend_width * 2, w // 4)
        result = arr.copy()

        for i in range(zone):
            t = float(i) / max(1, zone - 1)
            weight = mix * (1.0 - t)
            result[:, i, :] = (1.0 - weight) * arr[:, i, :] + weight * blurred[:, i, :]
            result[:, w - 1 - i, :] = (1.0 - weight) * arr[:, w - 1 - i, :] + weight * blurred[:, w - 1 - i, :]

        return result
