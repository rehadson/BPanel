from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
import numpy as np
from PIL import Image
import tifffile


CHANNEL_ORDER = ["brightfield", "shift", "width", "intensity"]
DATA_CHANNELS = {"shift", "width", "intensity"}

CHANNEL_FILE_PATTERNS = {
    "shift": re.compile(
        r"^(?P<prefix>.+?)(?:_BMrep(?P<bmrep>\d+))?_brillouin_shift_f\.tiff?$",
        re.IGNORECASE,
    ),
    "width": re.compile(
        r"^(?P<prefix>.+?)(?:_BMrep(?P<bmrep>\d+))?_brillouin_peak_fwhm_f\.tiff?$",
        re.IGNORECASE,
    ),
    "intensity": re.compile(
        r"^(?P<prefix>.+?)(?:_BMrep(?P<bmrep>\d+))?_brillouin_peak_intensity\.tiff?$",
        re.IGNORECASE,
    ),
    # Only the measurement-area crop is valid for publication panels.
    # Full-camera exports such as ``..._channelbrightfield.png`` and
    # ``..._channelbrightfield_aligned.png`` are intentionally ignored.
    "brightfield": re.compile(
        r"^(?P<prefix>.+?)_FLrep(?P<flrep>\d+)_channelbrightfield_BMrep(?P<bmrep>\d+)\.(?:png|jpg|jpeg|tiff?)$",
        re.IGNORECASE,
    ),
}


@dataclass
class Measurement:
    measurement_id: str
    prefix: str
    bmrep: Optional[int]
    label: str
    files: Dict[str, Path] = field(default_factory=dict)
    shapes: Dict[str, Tuple[int, ...]] = field(default_factory=dict)

    def has_channel(self, channel: str) -> bool:
        return channel in self.files and self.files[channel].exists()

    def available_channels(self) -> List[str]:
        return [ch for ch in CHANNEL_ORDER if self.has_channel(ch)]

    def channel_shape(self, channel: str) -> Optional[Tuple[int, ...]]:
        return self.shapes.get(channel)

    def plane_count(self, channel: str) -> int:
        if not self.has_channel(channel):
            return 0
        if channel == "brightfield":
            return 1
        shape = self.shapes.get(channel)
        if not shape:
            try:
                shape = data_shape(self.files[channel])
            except Exception:
                return 1
        if len(shape) == 2:
            return 1
        if len(shape) == 3:
            return int(shape[0])
        return 1

    def max_planes(self) -> int:
        depths = [self.plane_count(ch) for ch in DATA_CHANNELS if self.has_channel(ch)]
        return max(depths, default=1)

    def is_zstack(self) -> bool:
        return self.max_planes() > 1


@dataclass
class ScanResult:
    measurements: List[Measurement]
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChannelSettings:
    enabled: bool = True
    label: str = ""
    cmap: str = "viridis"
    custom_colors: str = ""
    range_mode: str = "manual"  # manual, data, percentile
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    percentile_low: float = 1.0
    percentile_high: float = 99.0
    scale_factor: float = 1.0
    offset: float = 0.0
    colorbar_label: str = ""
    colorbar_ticks: int = 6
    interpolation: str = "nearest"


@dataclass
class LayoutSettings:
    row_height_mm: float = 36.0
    hgap_mm: float = 2.0
    vgap_mm: float = 2.0
    left_label_width_mm: float = 13.0
    colorbar_gap_mm: float = 3.0
    colorbar_width_mm: float = 3.2
    right_margin_mm: float = 14.0
    top_margin_mm: float = 4.0
    bottom_margin_mm: float = 4.0
    title_height_mm: float = 7.0
    font_size_pt: float = 8.0
    title_font_size_pt: float = 8.0
    row_label_rotation: float = 90.0
    dpi: int = 300
    show_column_titles: bool = False
    show_missing_text: bool = False
    missing_text: str = "N/A"
    background: str = "white"


@dataclass
class StackSettings:
    panel_mode: str = "comparison"  # comparison, zstack
    comparison_plane_index: int = 0  # zero-based; applies only to stack measurements
    zstack_measurement_id: str = ""
    brightfield_mode: str = "first"  # first, repeat
    show_plane_titles: bool = True
    plane_title_prefix: str = "Z"


@dataclass
class PanelConfig:
    folder: str = ""
    measurement_order: List[str] = field(default_factory=list)
    selected_measurements: List[str] = field(default_factory=list)
    measurement_labels: Dict[str, str] = field(default_factory=dict)
    channel_order: List[str] = field(default_factory=lambda: CHANNEL_ORDER.copy())
    channels: Dict[str, ChannelSettings] = field(default_factory=dict)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    stack: StackSettings = field(default_factory=StackSettings)

    def to_dict(self) -> dict:
        return {
            "folder": self.folder,
            "measurement_order": list(self.measurement_order),
            "selected_measurements": list(self.selected_measurements),
            "measurement_labels": dict(self.measurement_labels),
            "channel_order": list(self.channel_order),
            "channels": {k: asdict(v) for k, v in self.channels.items()},
            "layout": asdict(self.layout),
            "stack": asdict(self.stack),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PanelConfig":
        channels = {
            key: ChannelSettings(**value)
            for key, value in data.get("channels", {}).items()
        }
        layout = LayoutSettings(**data.get("layout", {}))
        stack = StackSettings(**data.get("stack", {}))
        return cls(
            folder=data.get("folder", ""),
            measurement_order=list(data.get("measurement_order", [])),
            selected_measurements=list(data.get("selected_measurements", [])),
            measurement_labels=dict(data.get("measurement_labels", {})),
            channel_order=list(data.get("channel_order", CHANNEL_ORDER)),
            channels=channels,
            layout=layout,
            stack=stack,
        )


def default_channel_settings() -> Dict[str, ChannelSettings]:
    return {
        "brightfield": ChannelSettings(
            enabled=True,
            label="Brightfield",
            cmap="gray",
            range_mode="data",
            colorbar_label="",
            interpolation="bilinear",
        ),
        "shift": ChannelSettings(
            enabled=True,
            label="Brillouin shift",
            cmap="viridis",
            range_mode="manual",
            vmin=5.0,
            vmax=5.5,
            scale_factor=1e-4,
            offset=0.0,
            colorbar_label="vB [GHz]",
            colorbar_ticks=6,
            interpolation="nearest",
        ),
        "width": ChannelSettings(
            enabled=True,
            label="Brillouin width",
            cmap="viridis",
            range_mode="manual",
            vmin=0.0,
            vmax=1.2,
            scale_factor=1e-4,
            offset=0.0,
            colorbar_label="dB [GHz]",
            colorbar_ticks=7,
            interpolation="nearest",
        ),
        "intensity": ChannelSettings(
            enabled=True,
            label="Brillouin int.",
            cmap="viridis",
            range_mode="percentile",
            vmin=None,
            vmax=None,
            percentile_low=1.0,
            percentile_high=99.0,
            scale_factor=1.0,
            offset=0.0,
            colorbar_label="I [a.u.]",
            colorbar_ticks=6,
            interpolation="nearest",
        ),
    }


def make_default_config(folder: str = "") -> PanelConfig:
    return PanelConfig(folder=folder, channels=default_channel_settings())


def _make_measurement_id(prefix: str, bmrep: Optional[int]) -> str:
    rep_text = "none" if bmrep is None else str(bmrep)
    return f"{prefix}::BMrep{rep_text}"


def _squeezed_shape(shape: Sequence[int]) -> Tuple[int, ...]:
    squeezed = tuple(int(size) for size in shape if int(size) != 1)
    return squeezed or (1,)


def data_shape(path: str | Path) -> Tuple[int, ...]:
    """Return logical shape as (Y, X) or (Z, Y, X) without loading the full array."""
    with tifffile.TiffFile(path) as tif:
        if not tif.series:
            raise ValueError(f"No TIFF series found in {path}")
        series = tif.series[0]
        original_shape = tuple(int(v) for v in series.shape)
        axes = _axes_after_squeeze(getattr(series, "axes", ""), original_shape)
        shape = _squeezed_shape(original_shape)
    if len(shape) not in (2, 3):
        raise ValueError(
            f"Expected a 2D Brillouin map or 3D Z-stack, got shape {shape} for {path}"
        )
    if len(shape) == 3 and axes and len(axes) == 3 and "Y" in axes and "X" in axes:
        y_axis = axes.index("Y")
        x_axis = axes.index("X")
        other = [idx for idx in range(3) if idx not in (y_axis, x_axis)]
        if len(other) == 1:
            return (shape[other[0]], shape[y_axis], shape[x_axis])
    return shape


def _inspect_channel_shape(path: Path, channel: str) -> Tuple[int, ...]:
    if channel == "brightfield":
        with Image.open(path) as image:
            width, height = image.size
        return (int(height), int(width))
    return data_shape(path)


def scan_folder(folder: str | Path) -> ScanResult:
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise FileNotFoundError(f"Folder does not exist: {folder_path}")

    warnings: List[str] = []
    candidates: Dict[Tuple[str, Optional[int]], Dict[str, List[Path]]] = {}

    for path in sorted(folder_path.iterdir()):
        if not path.is_file():
            continue
        for channel, pattern in CHANNEL_FILE_PATTERNS.items():
            match = pattern.match(path.name)
            if not match:
                continue
            prefix = match.group("prefix")
            bmrep_text = match.groupdict().get("bmrep")
            bmrep = int(bmrep_text) if bmrep_text is not None else None
            key = (prefix, bmrep)
            candidates.setdefault(key, {}).setdefault(channel, []).append(path)
            break

    # Merge files without explicit BMrep into the most plausible numbered repetition.
    prefixes = sorted({key[0] for key in candidates})
    for prefix in prefixes:
        none_key = (prefix, None)
        if none_key not in candidates:
            continue
        numbered = sorted(
            key for key in candidates if key[0] == prefix and key[1] is not None
        )
        if len(numbered) == 1:
            target = numbered[0]
            for channel, paths in candidates[none_key].items():
                candidates[target].setdefault(channel, []).extend(paths)
            del candidates[none_key]
        elif any(key[1] == 0 for key in numbered):
            target = next(key for key in numbered if key[1] == 0)
            warnings.append(
                f"Files without BMrep for '{prefix}' were assigned to BMrep0 because multiple repetitions exist."
            )
            for channel, paths in candidates[none_key].items():
                candidates[target].setdefault(channel, []).extend(paths)
            del candidates[none_key]

    measurements: List[Measurement] = []
    prefix_counts: Dict[str, int] = {}
    for prefix, _rep in candidates:
        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    for (prefix, bmrep), by_channel in sorted(
        candidates.items(),
        key=lambda item: (
            item[0][0].lower(),
            -1 if item[0][1] is None else item[0][1],
        ),
    ):
        files: Dict[str, Path] = {}
        shapes: Dict[str, Tuple[int, ...]] = {}
        for channel, paths in by_channel.items():
            unique_paths = sorted(set(paths))
            chosen = unique_paths[0]
            files[channel] = chosen
            if len(unique_paths) > 1:
                warnings.append(
                    f"Multiple {channel} files matched '{prefix}' BMrep {bmrep}; using '{chosen.name}'."
                )
            try:
                shapes[channel] = _inspect_channel_shape(chosen, channel)
            except Exception as exc:
                warnings.append(f"Could not inspect '{chosen.name}': {exc}")

        if prefix_counts.get(prefix, 0) > 1 or (bmrep not in (None, 0)):
            label = f"{prefix} (BMrep {bmrep if bmrep is not None else '?'})"
        else:
            label = prefix

        measurements.append(
            Measurement(
                measurement_id=_make_measurement_id(prefix, bmrep),
                prefix=prefix,
                bmrep=bmrep,
                label=label,
                files=files,
                shapes=shapes,
            )
        )

    return ScanResult(measurements=measurements, warnings=warnings)


def load_brightfield(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def _axes_after_squeeze(axes: str, shape: Sequence[int]) -> str:
    if not axes or len(axes) != len(shape):
        return ""
    return "".join(axis for axis, size in zip(axes, shape) if int(size) != 1)


def load_data_stack(path: str | Path) -> np.ndarray:
    """Load a Brillouin TIFF as (Z, Y, X). A 2D map becomes a 1-plane stack."""
    with tifffile.TiffFile(path) as tif:
        if not tif.series:
            raise ValueError(f"No TIFF series found in {path}")
        series = tif.series[0]
        original_shape = tuple(int(v) for v in series.shape)
        axes = _axes_after_squeeze(getattr(series, "axes", ""), original_shape)
        array = np.asarray(series.asarray())

    array = np.squeeze(array)
    if array.ndim == 2:
        return array[np.newaxis, ...].astype(np.float64, copy=False)
    if array.ndim != 3:
        raise ValueError(
            f"Expected a 2D Brillouin map or 3D Z-stack, got shape {array.shape} for {path}"
        )

    # If TIFF metadata identifies Y and X, move the remaining axis to the front.
    if axes and len(axes) == 3 and "Y" in axes and "X" in axes:
        y_axis = axes.index("Y")
        x_axis = axes.index("X")
        other = [idx for idx in range(3) if idx not in (y_axis, x_axis)]
        if len(other) == 1:
            array = np.transpose(array, (other[0], y_axis, x_axis))
    # Otherwise the microscope export used by this app is interpreted as (Z, Y, X).

    return array.astype(np.float64, copy=False)


def load_data_image(path: str | Path, plane_index: int = 0) -> np.ndarray:
    """Compatibility helper returning one focal plane from a 2D map or Z-stack."""
    stack = load_data_stack(path)
    index = int(plane_index)
    if index < 0 or index >= stack.shape[0]:
        raise IndexError(
            f"Plane Z{index + 1} is not available in {path}; stack contains {stack.shape[0]} plane(s)."
        )
    return stack[index]


def transformed_stack(path: str | Path, settings: ChannelSettings) -> np.ndarray:
    array = load_data_stack(path)
    return array * settings.scale_factor + settings.offset


def transformed_data(
    path: str | Path, settings: ChannelSettings, plane_index: int = 0
) -> np.ndarray:
    array = load_data_image(path, plane_index=plane_index)
    return array * settings.scale_factor + settings.offset


def _finite_values(arrays: Iterable[np.ndarray]) -> np.ndarray:
    values: List[np.ndarray] = []
    for array in arrays:
        finite = np.asarray(array)[np.isfinite(array)]
        if finite.size:
            values.append(finite.ravel())
    if not values:
        return np.asarray([], dtype=float)
    return np.concatenate(values)


def _resolve_values_range(values: np.ndarray, settings: ChannelSettings) -> Tuple[float, float]:
    mode = settings.range_mode.lower()
    if mode == "manual" and settings.vmin is not None and settings.vmax is not None:
        vmin = float(settings.vmin)
        vmax = float(settings.vmax)
    elif values.size == 0:
        return 0.0, 1.0
    elif mode == "percentile":
        low = min(max(float(settings.percentile_low), 0.0), 100.0)
        high = min(max(float(settings.percentile_high), 0.0), 100.0)
        if high <= low:
            low, high = 1.0, 99.0
        vmin, vmax = np.percentile(values, [low, high])
    else:
        vmin = float(np.nanmin(values))
        vmax = float(np.nanmax(values))

    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return 0.0, 1.0
    if math.isclose(vmin, vmax):
        delta = abs(vmin) * 0.01 or 1.0
        vmin -= delta
        vmax += delta
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    return float(vmin), float(vmax)


def resolve_range(
    channel: str,
    measurements: Sequence[Measurement],
    settings: ChannelSettings,
    plane_index: Optional[int] = None,
    all_planes: bool = False,
) -> Tuple[float, float]:
    arrays: List[np.ndarray] = []
    for measurement in measurements:
        if not measurement.has_channel(channel):
            continue
        stack = transformed_stack(measurement.files[channel], settings)
        if all_planes:
            arrays.append(stack)
            continue
        if stack.shape[0] == 1:
            arrays.append(stack[0])
            continue
        index = 0 if plane_index is None else int(plane_index)
        if 0 <= index < stack.shape[0]:
            arrays.append(stack[index])
    return _resolve_values_range(_finite_values(arrays), settings)


def _aspect_ratio_for_measurement(measurement: Measurement) -> float:
    # Prefer Brillouin maps because those define the quantitative field.
    for channel in ("shift", "width", "intensity", "brightfield"):
        if not measurement.has_channel(channel):
            continue
        try:
            shape = measurement.channel_shape(channel)
            if not shape:
                shape = _inspect_channel_shape(measurement.files[channel], channel)
            height, width = int(shape[-2]), int(shape[-1])
            if height > 0:
                return max(0.2, min(8.0, float(width) / float(height)))
        except Exception:
            continue
    return 1.0


def _get_colormap(settings: ChannelSettings, channel: str):
    colors = [item.strip() for item in settings.custom_colors.split(",") if item.strip()]
    if len(colors) >= 2:
        return LinearSegmentedColormap.from_list(f"custom_{channel}", colors)
    try:
        return matplotlib.colormaps.get_cmap(settings.cmap)
    except Exception:
        return matplotlib.colormaps.get_cmap("viridis")


def _measurements_by_id(measurements: Sequence[Measurement]) -> Dict[str, Measurement]:
    return {measurement.measurement_id: measurement for measurement in measurements}


def selected_measurements_for_config(
    measurements: Sequence[Measurement], config: PanelConfig
) -> List[Measurement]:
    by_id = _measurements_by_id(measurements)
    order = config.measurement_order or [m.measurement_id for m in measurements]
    selected = set(config.selected_measurements or order)
    result = [by_id[mid] for mid in order if mid in selected and mid in by_id]
    for measurement in measurements:
        if measurement.measurement_id in selected and measurement not in result:
            result.append(measurement)
    return result


def _enabled_rows(selected: Sequence[Measurement], config: PanelConfig) -> List[str]:
    rows: List[str] = []
    for channel in config.channel_order:
        settings = config.channels.get(channel)
        if settings is None or not settings.enabled:
            continue
        if any(measurement.has_channel(channel) for measurement in selected):
            rows.append(channel)
    return rows


def _add_colorbar(
    figure,
    fig_w_mm: float,
    fig_h_mm: float,
    images_right_mm: float,
    row_bottom_mm: float,
    row_h: float,
    channel: str,
    settings: ChannelSettings,
    resolved_ranges: Dict[str, Tuple[float, float]],
    layout: LayoutSettings,
) -> None:
    cbar_left_mm = images_right_mm + layout.colorbar_gap_mm
    cax = figure.add_axes(
        [
            cbar_left_mm / fig_w_mm,
            row_bottom_mm / fig_h_mm,
            layout.colorbar_width_mm / fig_w_mm,
            row_h / fig_h_mm,
        ]
    )
    vmin, vmax = resolved_ranges[channel]
    cmap = _get_colormap(settings, channel)
    scalar = ScalarMappable(norm=Normalize(vmin=vmin, vmax=vmax), cmap=cmap)
    ticks = max(2, int(settings.colorbar_ticks))
    colorbar = figure.colorbar(scalar, cax=cax, ticks=np.linspace(vmin, vmax, ticks))
    colorbar.ax.tick_params(
        labelsize=max(5.0, layout.font_size_pt * 0.75), length=2
    )
    colorbar.ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:.4g}"))
    colorbar.outline.set_linewidth(0.5)
    if settings.colorbar_label:
        cax.set_title(
            settings.colorbar_label,
            fontsize=max(5.0, layout.font_size_pt * 0.72),
            pad=2,
        )


def _comparison_plane_image(
    measurement: Measurement,
    channel: str,
    settings: ChannelSettings,
    requested_plane: int,
) -> Optional[np.ndarray]:
    if channel == "brightfield":
        return load_brightfield(measurement.files[channel])
    stack = transformed_stack(measurement.files[channel], settings)
    if stack.shape[0] == 1:
        return stack[0]
    if requested_plane < 0 or requested_plane >= stack.shape[0]:
        return None
    return stack[requested_plane]


def _zstack_plane_image(
    measurement: Measurement,
    channel: str,
    settings: ChannelSettings,
    plane_index: int,
    brightfield_mode: str,
) -> Optional[np.ndarray]:
    if channel == "brightfield":
        if brightfield_mode == "repeat" or plane_index == 0:
            return load_brightfield(measurement.files[channel])
        return None
    stack = transformed_stack(measurement.files[channel], settings)
    if stack.shape[0] == 1:
        return stack[0] if plane_index == 0 else None
    if plane_index >= stack.shape[0]:
        return None
    return stack[plane_index]


def _render_grid(
    columns: Sequence[Tuple[str, float]],
    rows: Sequence[str],
    config: PanelConfig,
    image_provider,
    resolved_ranges: Dict[str, Tuple[float, float]],
    output_path: Optional[str | Path],
    preview: bool,
    show_titles_override: Optional[bool] = None,
):
    layout = config.layout
    mm_to_in = 1.0 / 25.4
    row_h = layout.row_height_mm
    col_widths = [row_h * aspect for _title, aspect in columns]
    images_width = sum(col_widths) + layout.hgap_mm * max(0, len(columns) - 1)

    any_data_row = any(channel in DATA_CHANNELS for channel in rows)
    cbar_block = (
        layout.colorbar_gap_mm + layout.colorbar_width_mm if any_data_row else 0.0
    )
    show_titles = (
        layout.show_column_titles
        if show_titles_override is None
        else bool(show_titles_override)
    )
    title_block = layout.title_height_mm if show_titles else 0.0

    fig_w_mm = (
        layout.left_label_width_mm
        + images_width
        + cbar_block
        + layout.right_margin_mm
    )
    fig_h_mm = (
        layout.top_margin_mm
        + title_block
        + len(rows) * row_h
        + layout.vgap_mm * max(0, len(rows) - 1)
        + layout.bottom_margin_mm
    )

    figure = plt.Figure(
        figsize=(fig_w_mm * mm_to_in, fig_h_mm * mm_to_in),
        dpi=100 if preview else layout.dpi,
        facecolor=layout.background,
    )

    x_positions: List[float] = []
    x_mm = layout.left_label_width_mm
    for width_mm in col_widths:
        x_positions.append(x_mm)
        x_mm += width_mm + layout.hgap_mm
    images_right_mm = x_positions[-1] + col_widths[-1]

    y_top_mm = fig_h_mm - layout.top_margin_mm - title_block

    if show_titles:
        title_y_center_mm = fig_h_mm - layout.top_margin_mm - title_block / 2.0
        for index, (title, _aspect) in enumerate(columns):
            center_x_mm = x_positions[index] + col_widths[index] / 2.0
            figure.text(
                center_x_mm / fig_w_mm,
                title_y_center_mm / fig_h_mm,
                title,
                ha="center",
                va="center",
                fontsize=layout.title_font_size_pt,
                color="black",
            )

    for row_index, channel in enumerate(rows):
        settings = config.channels[channel]
        row_top_mm = y_top_mm - row_index * (row_h + layout.vgap_mm)
        row_bottom_mm = row_top_mm - row_h

        figure.text(
            (layout.left_label_width_mm * 0.45) / fig_w_mm,
            (row_bottom_mm + row_h / 2.0) / fig_h_mm,
            settings.label or channel,
            ha="center",
            va="center",
            rotation=layout.row_label_rotation,
            fontsize=layout.font_size_pt,
            color="black",
        )

        for col_index, _column in enumerate(columns):
            left = x_positions[col_index] / fig_w_mm
            bottom = row_bottom_mm / fig_h_mm
            width = col_widths[col_index] / fig_w_mm
            height = row_h / fig_h_mm
            ax = figure.add_axes([left, bottom, width, height])
            ax.set_axis_off()
            ax.set_facecolor(layout.background)

            image = image_provider(channel, col_index)
            if image is None:
                if layout.show_missing_text:
                    ax.text(
                        0.5,
                        0.5,
                        layout.missing_text,
                        ha="center",
                        va="center",
                        fontsize=layout.font_size_pt,
                        transform=ax.transAxes,
                    )
                continue

            if channel == "brightfield":
                ax.imshow(image, interpolation=settings.interpolation, aspect="equal")
            else:
                vmin, vmax = resolved_ranges[channel]
                cmap = _get_colormap(settings, channel)
                ax.imshow(
                    image,
                    cmap=cmap,
                    vmin=vmin,
                    vmax=vmax,
                    interpolation=settings.interpolation,
                    aspect="equal",
                )
            ax.set_xlim(-0.5, image.shape[1] - 0.5)
            ax.set_ylim(image.shape[0] - 0.5, -0.5)

        if channel in DATA_CHANNELS:
            _add_colorbar(
                figure,
                fig_w_mm,
                fig_h_mm,
                images_right_mm,
                row_bottom_mm,
                row_h,
                channel,
                settings,
                resolved_ranges,
                layout,
            )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {"facecolor": layout.background}
        suffix = output_path.suffix.lower()
        if suffix in {".png", ".tif", ".tiff"}:
            save_kwargs["dpi"] = layout.dpi
        figure.savefig(output_path, **save_kwargs)

    return figure, resolved_ranges


def _render_comparison_panel(
    measurements: Sequence[Measurement],
    config: PanelConfig,
    output_path: Optional[str | Path],
    preview: bool,
):
    selected = selected_measurements_for_config(measurements, config)
    if not selected:
        raise ValueError("No measurements are selected.")

    rows = _enabled_rows(selected, config)
    if not rows:
        raise ValueError("No enabled channels are available in the selected measurements.")

    requested_plane = max(0, int(config.stack.comparison_plane_index))
    resolved_ranges: Dict[str, Tuple[float, float]] = {}
    for channel in rows:
        if channel in DATA_CHANNELS:
            resolved_ranges[channel] = resolve_range(
                channel,
                selected,
                config.channels[channel],
                plane_index=requested_plane,
                all_planes=False,
            )

    columns = [
        (
            config.measurement_labels.get(measurement.measurement_id, measurement.label),
            _aspect_ratio_for_measurement(measurement),
        )
        for measurement in selected
    ]

    def image_provider(channel: str, col_index: int) -> Optional[np.ndarray]:
        measurement = selected[col_index]
        if not measurement.has_channel(channel):
            return None
        return _comparison_plane_image(
            measurement,
            channel,
            config.channels[channel],
            requested_plane,
        )

    return _render_grid(
        columns,
        rows,
        config,
        image_provider,
        resolved_ranges,
        output_path,
        preview,
        show_titles_override=None,
    )


def _zstack_target(
    measurements: Sequence[Measurement], config: PanelConfig
) -> Measurement:
    by_id = _measurements_by_id(measurements)
    requested = config.stack.zstack_measurement_id
    if requested and requested in by_id:
        return by_id[requested]

    selected = selected_measurements_for_config(measurements, config)
    for measurement in selected:
        if measurement.is_zstack():
            return measurement
    for measurement in measurements:
        if measurement.is_zstack():
            return measurement
    if selected:
        return selected[0]
    if measurements:
        return measurements[0]
    raise ValueError("No measurements are available.")


def _render_zstack_panel(
    measurements: Sequence[Measurement],
    config: PanelConfig,
    output_path: Optional[str | Path],
    preview: bool,
):
    measurement = _zstack_target(measurements, config)
    rows = _enabled_rows([measurement], config)
    if not rows:
        raise ValueError("No enabled channels are available for this measurement.")

    plane_count = measurement.max_planes()
    if plane_count < 1:
        plane_count = 1

    resolved_ranges: Dict[str, Tuple[float, float]] = {}
    for channel in rows:
        if channel in DATA_CHANNELS:
            resolved_ranges[channel] = resolve_range(
                channel,
                [measurement],
                config.channels[channel],
                all_planes=True,
            )

    aspect = _aspect_ratio_for_measurement(measurement)
    prefix = config.stack.plane_title_prefix.strip() or "Z"
    columns = [(f"{prefix}{index + 1}", aspect) for index in range(plane_count)]

    def image_provider(channel: str, col_index: int) -> Optional[np.ndarray]:
        if not measurement.has_channel(channel):
            return None
        return _zstack_plane_image(
            measurement,
            channel,
            config.channels[channel],
            col_index,
            config.stack.brightfield_mode,
        )

    return _render_grid(
        columns,
        rows,
        config,
        image_provider,
        resolved_ranges,
        output_path,
        preview,
        show_titles_override=bool(config.stack.show_plane_titles),
    )


def render_panel(
    measurements: Sequence[Measurement],
    config: PanelConfig,
    output_path: Optional[str | Path] = None,
    preview: bool = False,
):
    mode = (config.stack.panel_mode or "comparison").lower()
    if mode == "zstack":
        return _render_zstack_panel(measurements, config, output_path, preview)
    return _render_comparison_panel(measurements, config, output_path, preview)



def _sanitize_filename_part(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    value = re.sub(r"_+", "_", value).strip("._-")
    return value or "image"


def _panel_context(measurements: Sequence[Measurement], config: PanelConfig):
    mode = (config.stack.panel_mode or "comparison").lower()
    if mode == "zstack":
        measurement = _zstack_target(measurements, config)
        rows = _enabled_rows([measurement], config)
        if not rows:
            raise ValueError("No enabled channels are available for this measurement.")
        plane_count = max(1, measurement.max_planes())
        resolved_ranges: Dict[str, Tuple[float, float]] = {}
        for channel in rows:
            if channel in DATA_CHANNELS:
                resolved_ranges[channel] = resolve_range(
                    channel, [measurement], config.channels[channel], all_planes=True
                )
        return {
            "mode": "zstack",
            "rows": rows,
            "resolved_ranges": resolved_ranges,
            "measurement": measurement,
            "plane_count": plane_count,
        }

    selected = selected_measurements_for_config(measurements, config)
    if not selected:
        raise ValueError("No measurements are selected.")
    rows = _enabled_rows(selected, config)
    if not rows:
        raise ValueError("No enabled channels are available in the selected measurements.")
    requested_plane = max(0, int(config.stack.comparison_plane_index))
    resolved_ranges: Dict[str, Tuple[float, float]] = {}
    for channel in rows:
        if channel in DATA_CHANNELS:
            resolved_ranges[channel] = resolve_range(
                channel,
                selected,
                config.channels[channel],
                plane_index=requested_plane,
                all_planes=False,
            )
    return {
        "mode": "comparison",
        "rows": rows,
        "resolved_ranges": resolved_ranges,
        "selected": selected,
        "requested_plane": requested_plane,
    }


def _render_individual_tile(
    image: np.ndarray,
    channel: str,
    settings: ChannelSettings,
    resolved_ranges: Dict[str, Tuple[float, float]],
    layout: LayoutSettings,
    output_path: str | Path,
    include_colorbar: bool = False,
) -> None:
    mm_to_in = 1.0 / 25.4
    height_mm = float(layout.row_height_mm)
    aspect = max(0.01, float(image.shape[1]) / float(image.shape[0]))
    image_width_mm = height_mm * aspect
    colorbar_block = 0.0
    right_text_margin_mm = 0.0
    top_text_margin_mm = 0.0
    if include_colorbar and channel in DATA_CHANNELS:
        colorbar_block = layout.colorbar_gap_mm + layout.colorbar_width_mm
        # Numeric tick labels are drawn to the right of the colorbar.
        # Reserve real figure space for them so they are not clipped.
        right_text_margin_mm = max(10.0, float(layout.right_margin_mm))
        # If a colorbar title is used, reserve a little space above it too.
        if settings.colorbar_label:
            top_text_margin_mm = 4.0
    fig_w_mm = image_width_mm + colorbar_block + right_text_margin_mm
    fig_h_mm = height_mm + top_text_margin_mm

    figure = plt.Figure(
        figsize=(fig_w_mm * mm_to_in, fig_h_mm * mm_to_in),
        dpi=layout.dpi,
        facecolor=layout.background,
    )

    image_bottom = 0.0
    image_height_fraction = height_mm / fig_h_mm
    if colorbar_block > 0.0:
        ax = figure.add_axes([0.0, image_bottom, image_width_mm / fig_w_mm, image_height_fraction])
    else:
        ax = figure.add_axes([0.0, image_bottom, image_width_mm / fig_w_mm, image_height_fraction])
    ax.set_axis_off()
    ax.set_facecolor(layout.background)

    if channel == "brightfield":
        ax.imshow(image, interpolation=settings.interpolation, aspect="equal")
    else:
        vmin, vmax = resolved_ranges[channel]
        cmap = _get_colormap(settings, channel)
        ax.imshow(
            image,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            interpolation=settings.interpolation,
            aspect="equal",
        )
    ax.set_xlim(-0.5, image.shape[1] - 0.5)
    ax.set_ylim(image.shape[0] - 0.5, -0.5)

    if colorbar_block > 0.0 and channel in DATA_CHANNELS:
        cax = figure.add_axes(
            [
                (image_width_mm + layout.colorbar_gap_mm) / fig_w_mm,
                image_bottom,
                layout.colorbar_width_mm / fig_w_mm,
                image_height_fraction,
            ]
        )
        vmin, vmax = resolved_ranges[channel]
        scalar = ScalarMappable(norm=Normalize(vmin=vmin, vmax=vmax), cmap=_get_colormap(settings, channel))
        ticks = max(2, int(settings.colorbar_ticks))
        colorbar = figure.colorbar(scalar, cax=cax, ticks=np.linspace(vmin, vmax, ticks))
        colorbar.ax.tick_params(labelsize=max(5.0, layout.font_size_pt * 0.75), length=2)
        colorbar.ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:.4g}"))
        colorbar.outline.set_linewidth(0.5)
        if settings.colorbar_label:
            cax.set_title(
                settings.colorbar_label,
                fontsize=max(5.0, layout.font_size_pt * 0.72),
                pad=2,
            )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {"facecolor": layout.background}
    suffix = output_path.suffix.lower()
    if suffix in {".png", ".tif", ".tiff"}:
        save_kwargs["dpi"] = layout.dpi
    figure.savefig(output_path, **save_kwargs)


def export_individual_images(
    measurements: Sequence[Measurement],
    config: PanelConfig,
    output_dir: str | Path,
    include_colorbars: bool = False,
    image_extension: str = ".png",
) -> int:
    context = _panel_context(measurements, config)
    rows: List[str] = context["rows"]
    resolved_ranges: Dict[str, Tuple[float, float]] = context["resolved_ranges"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = image_extension if image_extension.startswith(".") else f".{image_extension}"
    ext = ext.lower()
    if ext not in {".png", ".tif", ".tiff"}:
        ext = ".png"

    count = 0
    if context["mode"] == "zstack":
        measurement: Measurement = context["measurement"]
        base_label = config.measurement_labels.get(measurement.measurement_id, measurement.label)
        base_name = _sanitize_filename_part(base_label or measurement.label or measurement.prefix)
        plane_count = int(context["plane_count"])
        for plane_index in range(plane_count):
            for channel in rows:
                if not measurement.has_channel(channel):
                    continue
                image = _zstack_plane_image(
                    measurement,
                    channel,
                    config.channels[channel],
                    plane_index,
                    config.stack.brightfield_mode,
                )
                if image is None:
                    continue
                filename = f"{base_name}_Z{plane_index + 1}_{channel}{ext}"
                _render_individual_tile(
                    image,
                    channel,
                    config.channels[channel],
                    resolved_ranges,
                    config.layout,
                    output_dir / filename,
                    include_colorbar=include_colorbars and channel in DATA_CHANNELS,
                )
                count += 1
        return count

    selected: List[Measurement] = context["selected"]
    requested_plane = int(context["requested_plane"])
    for measurement in selected:
        base_label = config.measurement_labels.get(measurement.measurement_id, measurement.label)
        base_name = _sanitize_filename_part(base_label or measurement.label or measurement.prefix)
        plane_suffix = f"_Z{requested_plane + 1}" if measurement.is_zstack() else ""
        for channel in rows:
            if not measurement.has_channel(channel):
                continue
            image = _comparison_plane_image(
                measurement,
                channel,
                config.channels[channel],
                requested_plane,
            )
            if image is None:
                continue
            filename = f"{base_name}{plane_suffix}_{channel}{ext}"
            _render_individual_tile(
                image,
                channel,
                config.channels[channel],
                resolved_ranges,
                config.layout,
                output_dir / filename,
                include_colorbar=include_colorbars and channel in DATA_CHANNELS,
            )
            count += 1
    return count


def save_config(
    path: str | Path,
    config: PanelConfig,
    resolved_ranges: Optional[dict] = None,
) -> None:
    payload = config.to_dict()
    if resolved_ranges is not None:
        payload["resolved_ranges"] = {
            key: [float(value[0]), float(value[1])]
            for key, value in resolved_ranges.items()
        }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_config(path: str | Path) -> PanelConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    config = PanelConfig.from_dict(data)
    defaults = default_channel_settings()
    for channel, settings in defaults.items():
        if channel not in config.channels:
            config.channels[channel] = settings
    return config
