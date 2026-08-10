"""To LatLong 2:1 node — convert any image into a 2:1 equirectangular canvas."""

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
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

FIT_MODES = ["pad_blur", "pad_black", "crop", "stretch"]


class ToLatLong2to1(DataNode):
    """Convert any image to a 2:1 equirectangular canvas for latlong workflows."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Input image to convert.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image", "expander": True},
                hide_property=True,
            )
        )

        output_width_param = ParameterInt(
            name="output_width",
            tooltip="Output canvas width in pixels. Height is always width / 2.",
            default_value=4096,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Output Width", "step": 64},
        )
        output_width_param.add_child(Slider(min_val=512, max_val=8192))
        self.add_parameter(output_width_param)

        self.add_parameter(
            ParameterString(
                name="fit_mode",
                tooltip="How to fit the source image into the 2:1 canvas.",
                default_value="pad_blur",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=FIT_MODES)},
                ui_options={"display_name": "Fit Mode"},
            )
        )

        background_blur_param = ParameterInt(
            name="background_blur",
            tooltip="Blur radius for the background fill in pad_blur mode (0 = sharp).",
            default_value=32,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Background Blur", "step": 1},
        )
        background_blur_param.add_child(Slider(min_val=0, max_val=128))
        self.add_parameter(background_blur_param)

        self.add_parameter(
            ParameterImage(
                name="output_image",
                tooltip="2:1 converted image.",
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
                tooltip="Output width / height ratio (should be 2.0).",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Aspect Ratio"},
            )
        )

        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename="latlong_2to1.png",
        )
        self._output_file.add_parameter()

    def process(self) -> None:
        image_value = self.get_parameter_value("image")
        output_width = max(512, int(self.get_parameter_value("output_width") or 4096))
        output_height = max(1, output_width // 2)
        fit_mode = str(self.get_parameter_value("fit_mode") or "pad_blur").strip().lower()
        blur_amount = max(0, int(self.get_parameter_value("background_blur") or 0))

        src = self._load_pil(image_value).convert("RGB")

        match fit_mode:
            case "stretch":
                out = src.resize((output_width, output_height), Image.Resampling.LANCZOS)
            case "crop":
                out = self._resize_cover(src, output_width, output_height)
            case "pad_blur":
                fg = self._resize_contain(src, output_width, output_height)
                bg = self._resize_cover(src, output_width, output_height)
                if blur_amount > 0:
                    bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_amount))
                out = self._paste_centered(fg, bg, output_width, output_height)
            case "pad_black":
                fg = self._resize_contain(src, output_width, output_height)
                bg = Image.new("RGB", (output_width, output_height), (0, 0, 0))
                out = self._paste_centered(fg, bg, output_width, output_height)
            case _:
                msg = f"Unknown fit_mode: {fit_mode!r}"
                raise ValueError(msg)

        buf = BytesIO()
        out.save(buf, format="PNG")

        dest = self._output_file.build_file()
        saved = dest.write_bytes(buf.getvalue())
        artifact = ImageUrlArtifact(saved.location)

        self.parameter_output_values["output_image"] = artifact
        self.parameter_output_values["width"] = out.width
        self.parameter_output_values["height"] = out.height
        self.parameter_output_values["aspect_ratio"] = out.width / max(1, out.height)

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

    def _resize_cover(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        scale = max(target_w / img.width, target_h / img.height)
        w = max(1, int(round(img.width * scale)))
        h = max(1, int(round(img.height * scale)))
        resized = img.resize((w, h), Image.Resampling.LANCZOS)
        left = max(0, (w - target_w) // 2)
        top = max(0, (h - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))

    def _resize_contain(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        scale = min(target_w / img.width, target_h / img.height)
        w = max(1, int(round(img.width * scale)))
        h = max(1, int(round(img.height * scale)))
        return img.resize((w, h), Image.Resampling.LANCZOS)

    def _paste_centered(
        self, fg: Image.Image, bg: Image.Image, target_w: int, target_h: int
    ) -> Image.Image:
        left = (target_w - fg.width) // 2
        top = (target_h - fg.height) // 2
        result = bg.copy()
        result.paste(fg, (left, top))
        return result
