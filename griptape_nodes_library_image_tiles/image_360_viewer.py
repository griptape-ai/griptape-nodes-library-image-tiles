"""360 Image Viewer node — interactive equirectangular viewer widget."""

from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlFromPathRequest,
    CreateStaticFileDownloadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.slider import Slider
from griptape_nodes.traits.widget import Widget

logger = logging.getLogger(__name__)


class Image360Viewer(DataNode):
    """Preview an equirectangular image in an interactive 360 spherical viewer."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.set_initial_node_size(width=980, height=760)

        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Equirectangular image input (2:1 aspect ratio recommended).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image", "expander": True},
                hide_property=True,
            )
        )

        hfov_param = ParameterInt(
            name="hfov",
            tooltip="Initial horizontal field of view in degrees (smaller = zoomed in).",
            default_value=95,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": "Field of View", "step": 1},
        )
        hfov_param.add_child(Slider(min_val=40, max_val=140))
        self.add_parameter(hfov_param)

        self.add_parameter(
            ParameterDict(
                name="viewer_state",
                default_value={"image_url": "", "hfov": 95},
                tooltip="Internal widget state for the 360 viewer.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Widget(name="Image360ViewerWidget", library="Image Tiles Library")},
                ui_options={"display_name": "Viewer"},
            )
        )

        self.add_parameter(
            Parameter(
                name="image_url",
                type="str",
                output_type="str",
                tooltip="Browser-accessible URL of the image used by the viewer.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Image URL"},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ("image", "hfov"):
            self._update_viewer_state()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        self._update_viewer_state()

    def _update_viewer_state(self) -> None:
        image_value = self.get_parameter_value("image")
        hfov = max(40, min(140, int(self.get_parameter_value("hfov") or 95)))

        browser_url = self._resolve_browser_url(image_value)

        state = {"image_url": browser_url, "hfov": hfov}
        self.parameter_output_values["viewer_state"] = state
        self.parameter_output_values["image_url"] = browser_url
        self.publish_update_to_parameter("viewer_state", state)

    def _resolve_browser_url(self, image_value: Any) -> str:
        """Resolve a Griptape Nodes image value to a browser-accessible URL."""
        if image_value is None:
            return ""

        macro_path: str | None = None

        if hasattr(image_value, "value") and isinstance(image_value.value, str):
            macro_path = image_value.value
        elif isinstance(image_value, dict):
            macro_path = image_value.get("value")
        elif isinstance(image_value, str) and image_value:
            macro_path = image_value

        if not macro_path:
            return ""

        try:
            resolved = File(macro_path).resolve()
            result = GriptapeNodes.handle_request(CreateStaticFileDownloadUrlFromPathRequest(file_path=resolved))
            if isinstance(result, CreateStaticFileDownloadUrlResultSuccess):
                return result.url
        except Exception:
            logger.debug("Could not resolve image URL for 360 viewer", exc_info=True)

        return macro_path
