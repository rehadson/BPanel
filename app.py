from __future__ import annotations

import os
import sys
import traceback
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

# Explicitly select PySide6 before Matplotlib initializes its Qt backend.
os.environ.setdefault("QT_API", "pyside6")
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import matplotlib
matplotlib.use("Agg")
from panel_engine import (
    CHANNEL_ORDER,
    DATA_CHANNELS,
    ChannelSettings,
    LayoutSettings,
    Measurement,
    PanelConfig,
    StackSettings,
    ScaleBarSettings,
    load_config,
    make_default_config,
    render_panel,
    export_individual_images,
    save_config,
    scan_folder,
)


APP_VERSION = "1.7.3"
APP_TITLE = f"Brillouin Publication Panel Builder v{APP_VERSION}"


class CollapsibleSection(QWidget):
    """A titled section whose content can be collapsed/expanded by clicking its
    header. Behaves like a QGroupBox for layout purposes: build the section's
    controls on ``.content_widget`` exactly as you would on a QGroupBox, then
    add the CollapsibleSection instance itself to the parent layout."""

    def __init__(self, title: str, start_expanded: bool = True, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(start_expanded)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow if start_expanded else Qt.RightArrow)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 4px; text-align: left; }"
        )
        self.toggle_button.clicked.connect(self._on_toggled)

        self.content_widget = QFrame()
        self.content_widget.setFrameShape(QFrame.StyledPanel)
        self.content_widget.setVisible(start_expanded)

        outer.addWidget(self.toggle_button)
        outer.addWidget(self.content_widget)

    def _on_toggled(self, checked: bool) -> None:
        self.content_widget.setVisible(checked)
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)


class ChannelEditor(QWidget):
    def __init__(self, channel: str, settings: ChannelSettings, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.is_data = channel in DATA_CHANNELS

        form = QFormLayout(self)
        self.enabled = QCheckBox("Include this row")
        self.label = QLineEdit()
        form.addRow(self.enabled)
        form.addRow("Row label", self.label)

        self.interpolation = QComboBox()
        self.interpolation.addItems(["nearest", "bilinear", "bicubic", "none"])
        form.addRow("Interpolation", self.interpolation)

        self.cmap = None
        self.custom_colors = None
        self.range_mode = None
        self.vmin = None
        self.vmax = None
        self.percentile_low = None
        self.percentile_high = None
        self.scale_factor = None
        self.offset = None
        self.colorbar_label = None
        self.colorbar_ticks = None
        self.colorbar_tick_style = None

        if self.is_data:
            self.cmap = QComboBox()
            self.cmap.setEditable(True)
            names = sorted(matplotlib.colormaps)
            self.cmap.addItems(names)
            self.custom_colors = QLineEdit()
            self.custom_colors.setPlaceholderText("Optional: #440154,#21918c,#fde725")

            self.range_mode = QComboBox()
            self.range_mode.addItem("Manual shared range", "manual")
            self.range_mode.addItem("Data min / max", "data")
            self.range_mode.addItem("Percentile", "percentile")

            self.vmin = QDoubleSpinBox()
            self.vmax = QDoubleSpinBox()
            for spin in (self.vmin, self.vmax):
                spin.setDecimals(6)
                spin.setRange(-1e12, 1e12)
                spin.setSingleStep(0.1)

            self.percentile_low = QDoubleSpinBox()
            self.percentile_high = QDoubleSpinBox()
            for spin in (self.percentile_low, self.percentile_high):
                spin.setDecimals(2)
                spin.setRange(0.0, 100.0)
            self.scale_factor = QDoubleSpinBox()
            self.scale_factor.setDecimals(10)
            self.scale_factor.setRange(-1e12, 1e12)
            self.scale_factor.setSingleStep(0.0001)
            self.offset = QDoubleSpinBox()
            self.offset.setDecimals(6)
            self.offset.setRange(-1e12, 1e12)
            self.colorbar_label = QLineEdit()
            self.colorbar_ticks = QSpinBox()
            self.colorbar_ticks.setRange(2, 20)
            self.colorbar_tick_style = QComboBox()
            self.colorbar_tick_style.addItem("Numeric values", "numeric")
            self.colorbar_tick_style.addItem("Min / Max labels only", "minmax")

            form.addRow("Colormap", self.cmap)
            form.addRow("Custom colors", self.custom_colors)
            form.addRow("Range mode", self.range_mode)
            form.addRow("Minimum", self.vmin)
            form.addRow("Maximum", self.vmax)
            form.addRow("Percentile low", self.percentile_low)
            form.addRow("Percentile high", self.percentile_high)
            form.addRow("Scale factor", self.scale_factor)
            form.addRow("Offset", self.offset)
            form.addRow("Colorbar title", self.colorbar_label)
            form.addRow("Colorbar tick labels", self.colorbar_tick_style)
            form.addRow("Colorbar ticks", self.colorbar_ticks)

            self.range_mode.currentIndexChanged.connect(self._update_range_controls)
            self.colorbar_tick_style.currentIndexChanged.connect(self._update_range_controls)

        self.set_settings(settings)

    def _set_combo_text(self, combo: QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setEditText(text)

    def _update_range_controls(self) -> None:
        if not self.is_data:
            return
        mode = self.range_mode.currentData()
        self.vmin.setEnabled(mode == "manual")
        self.vmax.setEnabled(mode == "manual")
        self.percentile_low.setEnabled(mode == "percentile")
        self.percentile_high.setEnabled(mode == "percentile")
        if self.colorbar_ticks is not None and self.colorbar_tick_style is not None:
            self.colorbar_ticks.setEnabled(self.colorbar_tick_style.currentData() != "minmax")

    def set_settings(self, settings: ChannelSettings) -> None:
        self.enabled.setChecked(settings.enabled)
        self.label.setText(settings.label)
        self._set_combo_text(self.interpolation, settings.interpolation)
        if self.is_data:
            self._set_combo_text(self.cmap, settings.cmap)
            self.custom_colors.setText(settings.custom_colors)
            index = self.range_mode.findData(settings.range_mode)
            self.range_mode.setCurrentIndex(max(0, index))
            self.vmin.setValue(0.0 if settings.vmin is None else settings.vmin)
            self.vmax.setValue(1.0 if settings.vmax is None else settings.vmax)
            self.percentile_low.setValue(settings.percentile_low)
            self.percentile_high.setValue(settings.percentile_high)
            self.scale_factor.setValue(settings.scale_factor)
            self.offset.setValue(settings.offset)
            self.colorbar_label.setText(settings.colorbar_label)
            self.colorbar_ticks.setValue(settings.colorbar_ticks)
            style_index = self.colorbar_tick_style.findData(settings.colorbar_tick_style)
            self.colorbar_tick_style.setCurrentIndex(max(0, style_index))
            self._update_range_controls()

    def settings(self) -> ChannelSettings:
        result = ChannelSettings(
            enabled=self.enabled.isChecked(),
            label=self.label.text().strip(),
            interpolation=self.interpolation.currentText(),
        )
        if self.is_data:
            result.cmap = self.cmap.currentText().strip() or "viridis"
            result.custom_colors = self.custom_colors.text().strip()
            result.range_mode = self.range_mode.currentData()
            result.vmin = self.vmin.value()
            result.vmax = self.vmax.value()
            result.percentile_low = self.percentile_low.value()
            result.percentile_high = self.percentile_high.value()
            result.scale_factor = self.scale_factor.value()
            result.offset = self.offset.value()
            result.colorbar_label = self.colorbar_label.text().strip()
            result.colorbar_ticks = self.colorbar_ticks.value()
            result.colorbar_tick_style = self.colorbar_tick_style.currentData() or "numeric"
        return result


class ExportOptionsDialog(QDialog):
    def __init__(self, base_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export options")
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Panel export base name: {base_name}\n"
            f"Individual images will be saved into: {base_name}_individual"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.export_panel_box = QCheckBox("Export full panel")
        self.export_panel_box.setChecked(True)
        self.export_individual_box = QCheckBox("Export individual rendered images")
        self.export_individual_box.setChecked(False)
        self.include_colorbars_box = QCheckBox("Include standalone colorbars for Brillouin individual images")
        self.include_colorbars_box.setChecked(False)
        self.include_colorbars_box.setEnabled(False)

        self.export_individual_box.toggled.connect(self.include_colorbars_box.setEnabled)

        layout.addWidget(self.export_panel_box)
        layout.addWidget(self.export_individual_box)
        layout.addWidget(self.include_colorbars_box)

        note = QLabel(
            "Individual images use the same rendering settings as the panel (colormap, scaling, interpolation, and DPI)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not (self.export_panel_box.isChecked() or self.export_individual_box.isChecked()):
            QMessageBox.information(self, APP_TITLE, "Select at least one export option.")
            return
        self.accept()

    def options(self):
        return {
            "export_panel": self.export_panel_box.isChecked(),
            "export_individual": self.export_individual_box.isChecked(),
            "include_colorbars": self.include_colorbars_box.isChecked(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)
        self.config = make_default_config()
        self.measurements: List[Measurement] = []
        self.current_figure = None

        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Choose a folder containing Brillouin exports.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")

        open_folder_action = QAction("Open folder...", self)
        open_folder_action.triggered.connect(self.choose_folder)
        file_menu.addAction(open_folder_action)

        load_action = QAction("Load settings...", self)
        load_action.triggered.connect(self.load_settings_dialog)
        file_menu.addAction(load_action)

        save_action = QAction("Save settings...", self)
        save_action.triggered.connect(self.save_settings_dialog)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        export_action = QAction("Export panel...", self)
        export_action.triggered.connect(self.export_panel)
        file_menu.addAction(export_action)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_container = QWidget()
        controls = QVBoxLayout(controls_container)
        controls_scroll.setWidget(controls_container)
        controls_scroll.setMinimumWidth(480)
        controls_scroll.setMaximumWidth(620)
        splitter.addWidget(controls_scroll)

        folder_section = CollapsibleSection("1. Data folder")
        folder_group = folder_section.content_widget
        folder_layout = QVBoxLayout(folder_group)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse_button)
        folder_layout.addLayout(folder_row)
        scan_button = QPushButton("Scan folder")
        scan_button.clicked.connect(self.scan_current_folder)
        folder_layout.addWidget(scan_button)
        self.scan_info = QLabel("No folder scanned.")
        self.scan_info.setWordWrap(True)
        folder_layout.addWidget(self.scan_info)
        controls.addWidget(folder_section)

        measurement_section = CollapsibleSection("2. Measurements / columns")
        measurement_group = measurement_section.content_widget
        measurement_layout = QVBoxLayout(measurement_group)
        self.measurement_table = QTableWidget(0, 7)
        self.measurement_table.setHorizontalHeaderLabels(
            ["Use", "Column label", "Type", "BF", "Shift", "Width", "Intensity"]
        )
        header = self.measurement_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.measurement_table.verticalHeader().setVisible(False)
        self.measurement_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.measurement_table.setSelectionMode(QTableWidget.SingleSelection)
        measurement_layout.addWidget(self.measurement_table)

        use_row = QHBoxLayout()
        use_all_button = QPushButton("Use all")
        use_none_button = QPushButton("Use none")
        use_all_button.clicked.connect(lambda: self._set_all_measurements_used(True))
        use_none_button.clicked.connect(lambda: self._set_all_measurements_used(False))
        use_row.addWidget(use_all_button)
        use_row.addWidget(use_none_button)
        measurement_layout.addLayout(use_row)

        order_row = QHBoxLayout()
        up_button = QPushButton("Move up")
        down_button = QPushButton("Move down")
        up_button.clicked.connect(lambda: self.move_measurement(-1))
        down_button.clicked.connect(lambda: self.move_measurement(1))
        order_row.addWidget(up_button)
        order_row.addWidget(down_button)
        measurement_layout.addLayout(order_row)
        controls.addWidget(measurement_section)

        stack_section = CollapsibleSection("3. Panel mode / Z-stacks")
        stack_group = stack_section.content_widget
        stack_form = QFormLayout(stack_group)
        self.panel_mode = QComboBox()
        self.panel_mode.addItem("Comparison - measurements as columns", "comparison")
        self.panel_mode.addItem("Z-stack - focal planes as columns", "zstack")
        self.panel_mode.currentIndexChanged.connect(self._update_stack_controls_state)

        self.comparison_plane = QSpinBox()
        self.comparison_plane.setRange(1, 1)
        self.comparison_plane.setValue(1)
        self.comparison_plane.setToolTip(
            "For Z-stack measurements in Comparison mode, choose which focal plane is shown. "
            "Ordinary 2D measurements always show their only plane."
        )

        self.zstack_measurement = QComboBox()
        self.zstack_measurement.currentIndexChanged.connect(self._update_stack_controls_state)

        self.brightfield_z_mode = QComboBox()
        self.brightfield_z_mode.addItem("Show in first Z column only", "first")
        self.brightfield_z_mode.addItem("Repeat in every Z column", "repeat")

        self.show_plane_titles = QCheckBox("Show Z1, Z2, ... column titles")
        self.show_plane_titles.setChecked(True)
        self.stack_info = QLabel("No Z-stack detected yet.")
        self.stack_info.setWordWrap(True)

        stack_form.addRow("Panel mode", self.panel_mode)
        stack_form.addRow("Comparison Z plane", self.comparison_plane)
        stack_form.addRow("Z-stack measurement", self.zstack_measurement)
        stack_form.addRow("Brightfield in Z-stack", self.brightfield_z_mode)
        stack_form.addRow(self.show_plane_titles)
        stack_form.addRow(self.stack_info)
        controls.addWidget(stack_section)

        channel_section = CollapsibleSection("4. Channels / rows")
        channel_group = channel_section.content_widget
        channel_layout = QVBoxLayout(channel_group)
        order_hint = QLabel("Drag the row names below to change row order.")
        channel_layout.addWidget(order_hint)
        self.channel_order_list = QListWidget()
        self.channel_order_list.setDragDropMode(QListWidget.InternalMove)
        self.channel_order_list.setMaximumHeight(120)
        for channel in CHANNEL_ORDER:
            item = QListWidgetItem(channel)
            item.setData(Qt.UserRole, channel)
            self.channel_order_list.addItem(item)
        channel_layout.addWidget(self.channel_order_list)

        self.channel_tabs = QTabWidget()
        self.channel_editors: Dict[str, ChannelEditor] = {}
        for channel in CHANNEL_ORDER:
            editor = ChannelEditor(channel, self.config.channels[channel])
            self.channel_editors[channel] = editor
            self.channel_tabs.addTab(editor, channel.capitalize())
        channel_layout.addWidget(self.channel_tabs)
        controls.addWidget(channel_section)

        layout_section = CollapsibleSection("5. Layout")
        layout_group = layout_section.content_widget
        layout_form = QFormLayout(layout_group)
        self.row_height = self._double_spin(10, 100, 36, 1, 1)
        self.hgap = self._double_spin(0, 20, 2, 0.5, 1)
        self.vgap = self._double_spin(0, 20, 2, 0.5, 1)
        self.label_width = self._double_spin(3, 50, 13, 1, 1)
        self.cbar_gap = self._double_spin(0, 20, 3, 0.5, 1)
        self.cbar_width = self._double_spin(1, 15, 3.2, 0.2, 1)
        self.font_size = self._double_spin(5, 30, 8, 0.5, 1)
        self.title_font_size = self._double_spin(5, 30, 8, 0.5, 1)
        self.rotation = self._double_spin(-180, 180, 90, 5, 0)
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setValue(300)
        self.show_titles = QCheckBox("Show column titles")
        self.show_missing = QCheckBox("Show N/A in missing cells")

        layout_form.addRow("Image row height [mm]", self.row_height)
        layout_form.addRow("Horizontal gap [mm]", self.hgap)
        layout_form.addRow("Vertical gap [mm]", self.vgap)
        layout_form.addRow("Left label width [mm]", self.label_width)
        layout_form.addRow("Colorbar gap [mm]", self.cbar_gap)
        layout_form.addRow("Colorbar width [mm]", self.cbar_width)
        layout_form.addRow("Row font [pt]", self.font_size)
        layout_form.addRow("Title font [pt]", self.title_font_size)
        layout_form.addRow("Row label rotation", self.rotation)
        layout_form.addRow("Raster export DPI", self.dpi)
        layout_form.addRow(self.show_titles)
        layout_form.addRow(self.show_missing)
        controls.addWidget(layout_section)

        scale_section = CollapsibleSection("6. Scale bar")
        scale_group = scale_section.content_widget
        scale_form = QFormLayout(scale_group)
        self.scale_enabled = QCheckBox("Add calibrated scale bar")
        self.scale_length = self._double_spin(0.01, 100000, 10.0, 1.0, 2)
        self.scale_brillouin_px = self._double_spin(0.000001, 10000, 0.5, 0.1, 6)
        self.scale_brightfield_px = self._double_spin(0.000001, 10000, 0.5, 0.1, 6)

        self.scale_apply_to = QComboBox()
        self.scale_apply_to.addItem("All images", "all")
        self.scale_apply_to.addItem("Brightfield only", "brightfield")
        self.scale_apply_to.addItem("Brillouin maps only", "brillouin")

        self.scale_position = QComboBox()
        self.scale_position.addItem("Lower right", "lower right")
        self.scale_position.addItem("Lower left", "lower left")
        self.scale_position.addItem("Upper right", "upper right")
        self.scale_position.addItem("Upper left", "upper left")

        self.scale_color = QComboBox()
        self.scale_color.setEditable(True)
        self.scale_color.addItems(["white", "black"])
        self.scale_line_width = self._double_spin(0.1, 20, 3.0, 0.5, 1)
        self.scale_margin = self._double_spin(0, 25, 5.0, 1.0, 1)
        self.scale_show_label = QCheckBox("Show length label")
        self.scale_show_label.setChecked(True)
        self.scale_font_size = self._double_spin(1, 40, 8.0, 0.5, 1)

        scale_note = QLabel(
            "For shift/width/intensity, BPanel first reads the pixel calibration embedded in "
            "each TIFF (the same calibration Fiji/ImageJ shows). The Brillouin pixel size below "
            "is only used as a manual fallback for TIFFs that carry no readable calibration. "
            "Brightfield images have no calibration of their own, so the brightfield scale bar "
            "is automatically derived from the (embedded or fallback) calibration and field of "
            "view of the matching measurement's Brillouin image. The brightfield pixel size "
            "below is only used as a manual fallback for measurements with no Brillouin channel "
            "image at all."
        )
        scale_note.setWordWrap(True)

        scale_form.addRow(self.scale_enabled)
        scale_form.addRow("Apply to", self.scale_apply_to)
        scale_form.addRow("Bar length [µm]", self.scale_length)
        scale_form.addRow("Brillouin pixel size (fallback) [µm/px]", self.scale_brillouin_px)
        scale_form.addRow("Brightfield pixel size (fallback) [µm/px]", self.scale_brightfield_px)
        scale_form.addRow("Position", self.scale_position)
        scale_form.addRow("Color", self.scale_color)
        scale_form.addRow("Line width [pt]", self.scale_line_width)
        scale_form.addRow("Margin [%]", self.scale_margin)
        scale_form.addRow(self.scale_show_label)
        scale_form.addRow("Label font [pt]", self.scale_font_size)
        scale_form.addRow(scale_note)
        controls.addWidget(scale_section)

        button_row = QHBoxLayout()
        preview_button = QPushButton("Update preview")
        preview_button.clicked.connect(self.update_preview)
        export_button = QPushButton("Export panel...")
        export_button.clicked.connect(self.export_panel)
        button_row.addWidget(preview_button)
        button_row.addWidget(export_button)
        controls.addLayout(button_row)

        self.batch_z_button = QPushButton("Batch export selected Z-stacks (PDF)...")
        self.batch_z_button.clicked.connect(self.export_selected_zstacks)
        controls.addWidget(self.batch_z_button)

        settings_row = QHBoxLayout()
        save_button = QPushButton("Save settings")
        load_button = QPushButton("Load settings")
        save_button.clicked.connect(self.save_settings_dialog)
        load_button.clicked.connect(self.load_settings_dialog)
        settings_row.addWidget(save_button)
        settings_row.addWidget(load_button)
        controls.addLayout(settings_row)
        controls.addStretch(1)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(6)

        self.preview_note = QLabel(
            "Preview uses the same raster renderer as PNG export and is uniformly scaled for display."
        )
        self.preview_note.setWordWrap(True)

        self.preview_label = QLabel("Choose a data folder to build a panel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMargin(0)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setWidget(self.preview_label)

        preview_layout.addWidget(self.preview_note)
        preview_layout.addWidget(self.preview_scroll, 1)
        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _double_spin(self, minimum, maximum, value, step, decimals):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        return spin

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _populate_stack_controls(self) -> None:
        current_id = self.config.stack.zstack_measurement_id or self.zstack_measurement.currentData()
        blocker = QSignalBlocker(self.zstack_measurement)
        self.zstack_measurement.clear()
        stack_measurements = [m for m in self.measurements if m.is_zstack()]
        for measurement in stack_measurements:
            self.zstack_measurement.addItem(
                f"{measurement.label} ({measurement.max_planes()} planes)",
                measurement.measurement_id,
            )
        del blocker

        if current_id:
            index = self.zstack_measurement.findData(current_id)
            if index >= 0:
                self.zstack_measurement.setCurrentIndex(index)
        if self.zstack_measurement.count() and self.zstack_measurement.currentIndex() < 0:
            self.zstack_measurement.setCurrentIndex(0)

        max_planes = max((m.max_planes() for m in self.measurements), default=1)
        current_plane = self.comparison_plane.value()
        self.comparison_plane.setRange(1, max(1, max_planes))
        self.comparison_plane.setValue(min(current_plane, max(1, max_planes)))
        self._update_stack_controls_state()

    def _update_stack_controls_state(self) -> None:
        mode = self.panel_mode.currentData() or "comparison"
        has_stacks = self.zstack_measurement.count() > 0
        self.comparison_plane.setEnabled(mode == "comparison" and has_stacks)
        self.zstack_measurement.setEnabled(mode == "zstack" and has_stacks)
        self.brightfield_z_mode.setEnabled(mode == "zstack" and has_stacks)
        self.show_plane_titles.setEnabled(mode == "zstack" and has_stacks)
        self.batch_z_button.setEnabled(has_stacks)

        if not has_stacks:
            self.stack_info.setText("No Z-stack detected. All quantitative TIFFs are 2D.")
            if mode == "zstack":
                self._set_combo_data(self.panel_mode, "comparison")
            return

        measurement_id = self.zstack_measurement.currentData()
        measurement = next(
            (m for m in self.measurements if m.measurement_id == measurement_id),
            None,
        )
        if measurement is None:
            measurement = next((m for m in self.measurements if m.is_zstack()), None)
        if measurement is not None:
            details = []
            for channel in ("shift", "width", "intensity"):
                depth = measurement.plane_count(channel)
                if depth:
                    details.append(f"{channel}: {depth}")
            self.stack_info.setText(
                f"Detected Z-stack: {measurement.max_planes()} planes. "
                + ", ".join(details)
                + ". Color ranges in Z-stack mode are shared across all displayed planes."
            )

    def choose_folder(self) -> None:
        start = self.folder_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Brillouin data folder", start)
        if folder:
            self.folder_edit.setText(folder)
            self.scan_current_folder()

    def scan_current_folder(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.information(self, APP_TITLE, "Choose a folder first.")
            return
        try:
            result = scan_folder(folder)
        except Exception as exc:
            self.show_error("Could not scan folder", exc)
            return

        was_empty = not self.measurements
        self.measurements = result.measurements
        self.config.folder = folder
        self._populate_measurement_table()
        self._populate_stack_controls()

        # If the folder contains a single Z-stack measurement, open directly in Z-stack mode.
        if was_empty and len(self.measurements) == 1 and self.measurements[0].is_zstack():
            self._set_combo_data(self.panel_mode, "zstack")
            self._update_stack_controls_state()

        available_counts = {
            channel: sum(m.has_channel(channel) for m in self.measurements)
            for channel in CHANNEL_ORDER
        }
        stack_count = sum(m.is_zstack() for m in self.measurements)
        text = (
            f"Found {len(self.measurements)} measurement(s); Z-stacks: {stack_count}. "
            + ", ".join(f"{ch}: {count}" for ch, count in available_counts.items())
        )
        if result.warnings:
            text += "\nWarnings: " + " | ".join(result.warnings[:3])
            if len(result.warnings) > 3:
                text += f" | +{len(result.warnings) - 3} more"
        self.scan_info.setText(text)
        self.statusBar().showMessage(text)
        if self.measurements:
            self.update_preview()

    def _populate_measurement_table(self) -> None:
        previous = self._measurement_table_state()
        self.measurement_table.setRowCount(0)

        order_ids = self.config.measurement_order or [m.measurement_id for m in self.measurements]
        by_id = {m.measurement_id: m for m in self.measurements}
        ordered = [by_id[mid] for mid in order_ids if mid in by_id]
        for measurement in self.measurements:
            if measurement not in ordered:
                ordered.append(measurement)

        selected = set(self.config.selected_measurements)
        use_all_if_empty = not selected

        for measurement in ordered:
            row = self.measurement_table.rowCount()
            self.measurement_table.insertRow(row)
            use_item = QTableWidgetItem()
            use_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            was_checked = previous.get(measurement.measurement_id, {}).get("checked")
            checked = was_checked if was_checked is not None else (use_all_if_empty or measurement.measurement_id in selected)
            use_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            use_item.setData(Qt.UserRole, measurement.measurement_id)
            self.measurement_table.setItem(row, 0, use_item)

            default_label = self.config.measurement_labels.get(measurement.measurement_id, measurement.label)
            label_text = previous.get(measurement.measurement_id, {}).get("label", default_label)
            self.measurement_table.setItem(row, 1, QTableWidgetItem(label_text))

            type_text = f"Z-stack ({measurement.max_planes()})" if measurement.is_zstack() else "2D"
            type_item = QTableWidgetItem(type_text)
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            type_item.setTextAlignment(Qt.AlignCenter)
            self.measurement_table.setItem(row, 2, type_item)

            for col, channel in enumerate(CHANNEL_ORDER, start=3):
                if not measurement.has_channel(channel):
                    text = "-"
                elif channel == "brightfield":
                    text = "yes"
                else:
                    planes = measurement.plane_count(channel)
                    text = f"{planes}z" if planes > 1 else "yes"
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignCenter)
                self.measurement_table.setItem(row, col, item)

    def _measurement_table_state(self) -> Dict[str, dict]:
        state = {}
        for row in range(self.measurement_table.rowCount()):
            item = self.measurement_table.item(row, 0)
            label_item = self.measurement_table.item(row, 1)
            if item is None:
                continue
            mid = item.data(Qt.UserRole)
            state[mid] = {
                "checked": item.checkState() == Qt.Checked,
                "label": label_item.text() if label_item else "",
            }
        return state

    def move_measurement(self, direction: int) -> None:
        row = self.measurement_table.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= self.measurement_table.rowCount():
            return
        self._swap_table_rows(row, new_row)
        self.measurement_table.selectRow(new_row)

    def _swap_table_rows(self, row_a: int, row_b: int) -> None:
        self.measurement_table.setUpdatesEnabled(False)
        try:
            items_a = [self.measurement_table.takeItem(row_a, col) for col in range(self.measurement_table.columnCount())]
            items_b = [self.measurement_table.takeItem(row_b, col) for col in range(self.measurement_table.columnCount())]
            for col, item in enumerate(items_a):
                self.measurement_table.setItem(row_b, col, item)
            for col, item in enumerate(items_b):
                self.measurement_table.setItem(row_a, col, item)
        finally:
            self.measurement_table.setUpdatesEnabled(True)

    def _set_all_measurements_used(self, use: bool) -> None:
        state = Qt.Checked if use else Qt.Unchecked
        for row in range(self.measurement_table.rowCount()):
            item = self.measurement_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)

    def _set_preview_pixmap(self, pixmap: QPixmap, export_dpi: int) -> None:
        """Display an export-rendered bitmap after uniform down-scaling.

        Rendering is performed at the same DPI as PNG/TIFF export. Only after the
        complete figure has been rasterized do we scale the whole bitmap for the
        GUI. This preserves the exact relative sizes of images, gaps, labels,
        ticks, and colorbars that will appear in the exported raster figure.
        """
        display_dpi = 100.0
        source_dpi = max(1.0, float(export_dpi))
        scale = min(1.0, display_dpi / source_dpi)
        target_width = max(1, int(round(pixmap.width() * scale)))
        target_height = max(1, int(round(pixmap.height() * scale)))
        if target_width != pixmap.width() or target_height != pixmap.height():
            pixmap = pixmap.scaled(
                target_width,
                target_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setFixedSize(pixmap.size())


    def collect_config(self) -> PanelConfig:
        config = make_default_config(self.folder_edit.text().strip())
        config.measurement_order = []
        config.selected_measurements = []
        config.measurement_labels = {}

        for row in range(self.measurement_table.rowCount()):
            use_item = self.measurement_table.item(row, 0)
            label_item = self.measurement_table.item(row, 1)
            if use_item is None:
                continue
            mid = use_item.data(Qt.UserRole)
            config.measurement_order.append(mid)
            if use_item.checkState() == Qt.Checked:
                config.selected_measurements.append(mid)
            config.measurement_labels[mid] = label_item.text().strip() if label_item else ""

        config.channel_order = []
        for index in range(self.channel_order_list.count()):
            item = self.channel_order_list.item(index)
            config.channel_order.append(item.data(Qt.UserRole))

        config.channels = {
            channel: editor.settings()
            for channel, editor in self.channel_editors.items()
        }

        config.stack = StackSettings(
            panel_mode=self.panel_mode.currentData() or "comparison",
            comparison_plane_index=max(0, self.comparison_plane.value() - 1),
            zstack_measurement_id=self.zstack_measurement.currentData() or "",
            brightfield_mode=self.brightfield_z_mode.currentData() or "first",
            show_plane_titles=self.show_plane_titles.isChecked(),
            plane_title_prefix="Z",
        )

        config.layout = LayoutSettings(
            row_height_mm=self.row_height.value(),
            hgap_mm=self.hgap.value(),
            vgap_mm=self.vgap.value(),
            left_label_width_mm=self.label_width.value(),
            colorbar_gap_mm=self.cbar_gap.value(),
            colorbar_width_mm=self.cbar_width.value(),
            right_margin_mm=14.0,
            top_margin_mm=4.0,
            bottom_margin_mm=4.0,
            title_height_mm=7.0,
            font_size_pt=self.font_size.value(),
            title_font_size_pt=self.title_font_size.value(),
            row_label_rotation=self.rotation.value(),
            dpi=self.dpi.value(),
            show_column_titles=self.show_titles.isChecked(),
            show_missing_text=self.show_missing.isChecked(),
            missing_text="N/A",
            background="white",
        )
        config.scale_bar = ScaleBarSettings(
            enabled=self.scale_enabled.isChecked(),
            length_um=self.scale_length.value(),
            brillouin_pixel_size_um=self.scale_brillouin_px.value(),
            brightfield_pixel_size_um=self.scale_brightfield_px.value(),
            position=self.scale_position.currentData() or "lower right",
            color=self.scale_color.currentText().strip() or "white",
            line_width_pt=self.scale_line_width.value(),
            margin_percent=self.scale_margin.value(),
            show_label=self.scale_show_label.isChecked(),
            font_size_pt=self.scale_font_size.value(),
            apply_to=self.scale_apply_to.currentData() or "all",
        )

        self.config = config
        return config

    def apply_config_to_ui(self, config: PanelConfig) -> None:
        self.config = config
        self.folder_edit.setText(config.folder)

        for channel in CHANNEL_ORDER:
            if channel in config.channels:
                self.channel_editors[channel].set_settings(config.channels[channel])

        while self.channel_order_list.count():
            self.channel_order_list.takeItem(0)
        seen = set()
        for channel in config.channel_order + CHANNEL_ORDER:
            if channel in seen or channel not in CHANNEL_ORDER:
                continue
            item = QListWidgetItem(channel)
            item.setData(Qt.UserRole, channel)
            self.channel_order_list.addItem(item)
            seen.add(channel)

        layout = config.layout
        self.row_height.setValue(layout.row_height_mm)
        self.hgap.setValue(layout.hgap_mm)
        self.vgap.setValue(layout.vgap_mm)
        self.label_width.setValue(layout.left_label_width_mm)
        self.cbar_gap.setValue(layout.colorbar_gap_mm)
        self.cbar_width.setValue(layout.colorbar_width_mm)
        self.font_size.setValue(layout.font_size_pt)
        self.title_font_size.setValue(layout.title_font_size_pt)
        self.rotation.setValue(layout.row_label_rotation)
        self.dpi.setValue(layout.dpi)
        self.show_titles.setChecked(layout.show_column_titles)
        self.show_missing.setChecked(layout.show_missing_text)

        scale = config.scale_bar
        self.scale_enabled.setChecked(scale.enabled)
        self.scale_length.setValue(scale.length_um)
        self.scale_brillouin_px.setValue(scale.brillouin_pixel_size_um)
        self.scale_brightfield_px.setValue(scale.brightfield_pixel_size_um)
        self._set_combo_data(self.scale_apply_to, scale.apply_to)
        self._set_combo_data(self.scale_position, scale.position)
        self.scale_color.setCurrentText(scale.color)
        self.scale_line_width.setValue(scale.line_width_pt)
        self.scale_margin.setValue(scale.margin_percent)
        self.scale_show_label.setChecked(scale.show_label)
        self.scale_font_size.setValue(scale.font_size_pt)

        panel_mode_blocker = QSignalBlocker(self.panel_mode)
        self._set_combo_data(self.panel_mode, config.stack.panel_mode)
        del panel_mode_blocker
        self.comparison_plane.setValue(max(1, config.stack.comparison_plane_index + 1))
        self._set_combo_data(self.brightfield_z_mode, config.stack.brightfield_mode)
        self.show_plane_titles.setChecked(config.stack.show_plane_titles)

        if config.folder and Path(config.folder).is_dir():
            result = scan_folder(config.folder)
            self.measurements = result.measurements
            self._populate_measurement_table()
            self._populate_stack_controls()
            if config.stack.zstack_measurement_id:
                index = self.zstack_measurement.findData(config.stack.zstack_measurement_id)
                if index >= 0:
                    self.zstack_measurement.setCurrentIndex(index)
            stack_count = sum(m.is_zstack() for m in self.measurements)
            self.scan_info.setText(
                f"Found {len(self.measurements)} measurement(s); Z-stacks: {stack_count}."
            )
            self._update_stack_controls_state()
            if self.measurements:
                self.update_preview()
        else:
            self.measurements = []
            self.measurement_table.setRowCount(0)
            self.scan_info.setText("Saved folder is not available. Choose the data folder and scan again.")

    def update_preview(self) -> None:
        if not self.measurements:
            return
        try:
            config = self.collect_config()
            # Render the preview using the exact same DPI/layout path as raster export.
            # We then scale the completed bitmap uniformly for the GUI. This avoids
            # Qt/Matplotlib HiDPI differences changing the apparent font size.
            figure, ranges = render_panel(self.measurements, config, preview=False)
            self.current_figure = figure
            buffer = BytesIO()
            figure.savefig(
                buffer,
                format="png",
                dpi=config.layout.dpi,
                facecolor=config.layout.background,
            )
            pixmap = QPixmap()
            if not pixmap.loadFromData(buffer.getvalue(), "PNG"):
                raise RuntimeError("Could not create the GUI preview image.")
            self._set_preview_pixmap(pixmap, config.layout.dpi)
            range_text = ", ".join(
                f"{key}={value[0]:.4g}..{value[1]:.4g}" for key, value in ranges.items()
            )
            self.statusBar().showMessage("Preview updated" + (f" | {range_text}" if range_text else ""))
        except Exception as exc:
            self.show_error("Could not render preview", exc)

    def export_panel(self) -> None:
        if not self.measurements:
            QMessageBox.information(self, APP_TITLE, "Scan a folder first.")
            return
        filters = (
            "PDF (*.pdf);;SVG (*.svg);;PNG (*.png);;TIFF (*.tif *.tiff)"
        )
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export publication panel",
            str(Path(self.config.folder or Path.home()) / "brillouin_panel.pdf"),
            filters,
        )
        if not path:
            return
        output = Path(path)
        if output.suffix == "":
            if selected_filter.startswith("SVG"):
                output = output.with_suffix(".svg")
            elif selected_filter.startswith("PNG"):
                output = output.with_suffix(".png")
            elif selected_filter.startswith("TIFF"):
                output = output.with_suffix(".tif")
            else:
                output = output.with_suffix(".pdf")

        dialog = ExportOptionsDialog(output.stem, self)
        if dialog.exec() != QDialog.Accepted:
            return
        options = dialog.options()

        try:
            config = self.collect_config()
            ranges = {}
            if options["export_panel"]:
                _figure, ranges = render_panel(self.measurements, config, output_path=output, preview=False)
                save_config(str(output) + ".json", config, ranges)

            individual_count = 0
            if options["export_individual"]:
                individual_dir = output.parent / f"{output.stem}_individual"
                suffix = output.suffix.lower()
                image_ext = suffix if suffix in {".png", ".tif", ".tiff"} else ".png"
                individual_count = export_individual_images(
                    self.measurements,
                    config,
                    individual_dir,
                    include_colorbars=options["include_colorbars"],
                    image_extension=image_ext,
                )

            status_parts = []
            if options["export_panel"]:
                status_parts.append(f"panel: {output.name}")
            if options["export_individual"]:
                status_parts.append(
                    f"{individual_count} individual image(s) in {output.stem}_individual"
                )
            QMessageBox.information(
                self,
                APP_TITLE,
                "Export complete.\n" + "\n".join(status_parts),
            )
        except Exception as exc:
            self.show_error("Could not export panel", exc)

    def export_selected_zstacks(self) -> None:
        if not self.measurements:
            QMessageBox.information(self, APP_TITLE, "Scan a folder first.")
            return
        config = self.collect_config()
        selected_ids = set(config.selected_measurements)
        stacks = [
            m for m in self.measurements
            if m.measurement_id in selected_ids and m.is_zstack()
        ]
        if not stacks:
            QMessageBox.information(
                self,
                APP_TITLE,
                "No checked Z-stack measurements are available for batch export.",
            )
            return

        start = config.folder or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Choose folder for Z-stack PDF panels", start
        )
        if not folder:
            return

        output_dir = Path(folder)
        exported = []
        try:
            for measurement in stacks:
                batch_config = PanelConfig.from_dict(config.to_dict())
                batch_config.stack.panel_mode = "zstack"
                batch_config.stack.zstack_measurement_id = measurement.measurement_id
                safe_name = "".join(
                    ch if ch.isalnum() or ch in "-_." else "_"
                    for ch in measurement.label
                ).strip("_.") or "measurement"
                output = output_dir / f"{safe_name}_zstack_panel.pdf"
                _, ranges = render_panel(
                    self.measurements, batch_config, output_path=output, preview=False
                )
                save_config(output.with_name(output.name + ".json"), batch_config, ranges)
                exported.append(output.name)
        except Exception as exc:
            self.show_error("Could not batch export Z-stacks", exc)
            return

        QMessageBox.information(
            self,
            APP_TITLE,
            f"Exported {len(exported)} Z-stack panel(s) to:\n{output_dir}",
        )
        self.statusBar().showMessage(f"Exported {len(exported)} Z-stack PDF panel(s)")

    def save_settings_dialog(self) -> None:
        config = self.collect_config()
        start = Path(config.folder or Path.home()) / "panel_settings.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save panel settings", str(start), "JSON (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_config(path, config)
            self.statusBar().showMessage(f"Saved settings: {path}")
        except Exception as exc:
            self.show_error("Could not save settings", exc)

    def load_settings_dialog(self) -> None:
        start = self.folder_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Load panel settings", start, "JSON (*.json)"
        )
        if not path:
            return
        try:
            config = load_config(path)
            self.apply_config_to_ui(config)
            self.statusBar().showMessage(f"Loaded settings: {path}")
        except Exception as exc:
            self.show_error("Could not load settings", exc)

    def show_error(self, title: str, exc: Exception) -> None:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Critical)
        message.setWindowTitle(title)
        message.setText(str(exc))
        message.setDetailedText(detail)
        message.exec()


def render_empty_figure():
    from matplotlib.figure import Figure

    figure = Figure(figsize=(8, 6), facecolor="white")
    ax = figure.add_subplot(111)
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        "Choose a data folder to build a panel",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=14,
    )
    return figure


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
