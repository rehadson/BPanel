# Brillouin Publication Panel Builder

A local Python desktop application for assembling publication panels from Brillouin microscopy BMicro exports. This app will not analyze your raw microscopy data. For CellSense Brillouin microscopy raw data analysis you need to use BMicro first. 

https://github.com/BrillouinMicroscopy/BMicro

## What it does

- Scans a folder and groups files into Brillouin measurements using the export filename patterns.
- Supports Brightfield, Brillouin shift, Brillouin width/FWHM, and Brillouin intensity.
- Handles missing channels and missing brightfield images.
- Uses measurements as columns and channels as rows.
- Keeps a common row height and preserves each measurement's aspect ratio.
- Uses equal physical gaps between columns and rows.
- Lets you reorder columns and rows.
- Lets you choose a Matplotlib colormap or define a custom comma-separated color palette.
- Lets you set manual shared min/max values, full data min/max, or percentile scaling.
- Applies an editable scale factor and offset to TIFF data only for visualization; source TIFFs are never modified.
- Draws one quantitative colorbar at the right side of each Brillouin row.
- Exports PDF, SVG, PNG, or TIFF.
- Saves a JSON sidecar next to every export for reproducibility.

## Supported filename patterns

The scanner currently recognizes these patterns (case-insensitive):

- `PREFIX_BMrep0_brillouin_shift_f.tiff`
- `PREFIX_brillouin_shift_f.tiff`
- `PREFIX_BMrep0_brillouin_peak_fwhm_f.tiff`
- `PREFIX_BMrep0_brillouin_peak_intensity.tiff`
- `PREFIX_FLrep0_channelbrightfield_BMrep0.png`

For brightfield, the `_BMrepN` suffix is **required**. This is deliberate: the program uses the cropped brightfield image corresponding to the actual Brillouin measurement area. Full-camera exports such as `PREFIX_FLrep0_channelbrightfield.png` and `PREFIX_FLrep0_channelbrightfield_aligned.png` are ignored.

`.tif`, `.tiff`, `.png`, `.jpg`, and `.jpeg` variants are accepted where appropriate.

If a shift file does not contain a BMrep number and there is only one numbered repetition for the same prefix, the program associates it automatically with that repetition.

## Installation

Python 3.10 or newer is recommended.

### Windows PowerShell

```powershell
cd path\to\brillouin_panel_builder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

### macOS / Linux

```bash
cd /path/to/brillouin_panel_builder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Normal workflow

1. Start `app.py`.
2. Click **Browse...** and choose the folder containing your exported microscopy files.
3. The measurement table shows which channels were found for each measurement.
4. Uncheck measurements you do not want in the panel (or use **Use all** / **Use none** to toggle everything at once).
5. Edit column labels if desired, and use **Move up / Move down** to reorder them.
6. Drag the channel names to set row order.
7. In each channel tab, choose whether the row should be included and set its display settings.
8. Click **Update preview**.
9. Click **Export panel...** and choose PDF, SVG, PNG, or TIFF.

Each numbered section (Data folder, Measurements/columns, Panel mode/Z-stacks, Channels/rows, Layout, Scale bar) can be collapsed by clicking its header, which helps when scrolling through a long control panel.

## Z-stack support

Version 1.2 accepts both ordinary 2D quantitative TIFFs and Z-stacks. Typical logical shapes are:

```text
(Y, X)       ordinary 2D Brillouin map
(Z, Y, X)    Brillouin Z-stack
```

The scanner reports each measurement as **2D** or **Z-stack (N)** and shows the detected plane counts for shift, width, and intensity.

There are two panel modes:

- **Comparison - measurements as columns**: this is the original publication-panel layout. For a Z-stack measurement, choose a single focal plane with **Comparison Z plane**. Ordinary 2D measurements are unaffected. If a chosen Z plane does not exist for a particular stack, that cell is left blank instead of substituting another plane.
- **Z-stack - focal planes as columns**: choose one Z-stack measurement and the columns become `Z1`, `Z2`, `Z3`, ... while the rows remain Brightfield, Shift, Width, and Intensity. Color ranges for each quantitative row are calculated/shared across all displayed Z planes.

For Brightfield in Z-stack mode you can either show the cropped BMrep-specific brightfield only in the first Z column, or repeat the same brightfield image in every Z column.

Use **Batch export selected Z-stacks (PDF)...** to create one PDF panel per checked Z-stack measurement. Each PDF also receives its own JSON settings sidecar.

Maximum/mean projections are intentionally not included in this version. Brillouin shift and width are quantitative mechanical observables, so collapsing the Z dimension should be an explicit later choice rather than an automatic default.

## Important data-scaling note

The uploaded example TIFF files store Brillouin shift and FWHM values around 50,000 and 4,000-12,000 respectively, while the example publication panel displays GHz values around 5.0-5.5 and 0.0-1.2. Therefore the default settings use a visualization scale factor of `0.0001` for shift and width.

This is editable in the GUI. Verify the factor against the unit convention used by your acquisition/export software before publication. The program never changes the raw TIFF values.

## Range modes

- **Manual shared range**: best for quantitative comparison between measurements. The same min/max is used in every column for that row.
- **Data min / max**: uses the global min and max across all selected measurements that contain that channel.
- **Percentile**: uses the global percentile limits across selected measurements. This can be useful for intensity maps with extreme outliers.

A single colorbar is drawn for each quantitative row, so all images in that row always use one shared scale. Each row's colorbar can show numeric tick values, or just Min/Max labels (see **Colorbar tick labels** below) — useful for channels like intensity where the absolute numbers are arbitrary.

## Custom colormaps

Leave **Custom colors** blank to use the selected Matplotlib colormap.

To create a custom continuous palette, enter two or more comma-separated colors, for example:

```text
#440154,#21918c,#fde725
```

Matplotlib color names also work, for example:

```text
navy,cyan,yellow
```

## Reproducibility

Every exported panel automatically gets a JSON sidecar, for example:

```text
figure3.pdf
figure3.pdf.json
```

The JSON contains:

- source folder
- selected measurements
- column labels and ordering
- row ordering
- colormaps
- scale factors and offsets
- min/max or percentile settings
- resolved quantitative ranges used for the exported figure
- physical layout values
- raster DPI

You can also save and reload settings manually from the GUI.

## Publication export recommendation

For figures that will later be edited in Illustrator or Inkscape, use **PDF** or **SVG**. Microscopy images remain raster data, while text, colorbar ticks, and labels remain vector graphics.

Use **TIFF** or **PNG** when a journal specifically requests a raster file. Set the output DPI in the Layout section; 300 or 600 DPI are common journal requirements.

## Notes on missing channels

If a selected measurement is missing one channel, that cell remains blank. The rest of the column is preserved, so all rows stay aligned. Enable **Show N/A in missing cells** if you want missing data to be explicitly marked during figure preparation.

If an entire channel is missing from all selected measurements, that row is omitted automatically even if the channel is enabled.


## Preview accuracy (v1.4)

The GUI preview is now generated through the same raster rendering path used for PNG/TIFF export. The complete figure is first rendered at the selected export DPI and is only then uniformly down-scaled for display in the GUI. This means font size, clipping, row/column spacing, colorbars, and image proportions in the preview match the exported raster figure.

Because the preview is an export-faithful raster preview, the old interactive Matplotlib preview toolbar is no longer shown. Use the dedicated Export panel button for final output.

## Scale bars (v1.7.0)

Version 1.7.0 can draw calibrated scale bars directly on panel tiles and on individually exported rendered images. Scale bars are disabled by default.

In **6. Scale bar**, configure:

- whether the scale bar is enabled;
- whether it is applied to all images, brightfield only, or Brillouin maps only;
- scale-bar length in µm;
- Brillouin pixel size in µm/pixel (fallback only, see v1.7.2 below);
- brightfield pixel size in µm/pixel (fallback only, see v1.7.1 below);
- corner position, color, line width, and edge margin;
- whether the numerical length label is shown and its font size.

The scale bar is an overlay only and never modifies the source image data.

## v1.7.1

Fixes
- Brightfield images carry no calibration of their own. The brightfield scale bar is now calibrated automatically from the paired Brillouin measurement's pixel size and field of view (same physical area, different camera resolution), instead of relying on a separate manually-entered value that had no real connection to the true calibration.
- The manual "Brightfield pixel size" field in **6. Scale bar** is kept only as a fallback, used solely for measurements that have no Brillouin channel image at all (e.g. brightfield-only measurements). It is labeled as such in the UI.
- `run_windows.bat` no longer flashes and closes silently on failure: it now keeps the window open and prints the actual Python error when the app fails to start.
- `run_windows.bat` now falls back to the Windows `py` launcher if `python` is not found on PATH, and gives a clear message with a download link if no Python interpreter can be found at all.

New functionality
- Added a per-channel colorbar tick-label style: numeric values, or Min/Max labels only.
- Intensity channel now defaults to Min/Max labels, since intensity values are in arbitrary units. Shift and width default to numeric values.
- Applies to both panel colorbars and standalone colorbars in individual-image export.
- All control sections (Data folder, Measurements/columns, Panel mode/Z-stacks, Channels/rows, Layout, Scale bar) can now be collapsed/expanded by clicking their header, making it faster to reach controls near the bottom of the panel.
- Added "Use all" / "Use none" buttons to the Measurements/columns section, to quickly select or deselect all scanned measurements instead of unchecking them one by one.

Compatibility
- Existing settings files from v1.7.0 remain compatible; missing colorbar tick-style settings default to numeric.
- The `run_windows.bat` change is packaging/launcher only; no effect on rendering, exports, or saved settings files.

## v1.7.2

Fixes
- Scale bars for shift/width/intensity now use the physical pixel calibration embedded in each TIFF's own metadata (the same calibration Fiji/ImageJ reports when you open the file), instead of always relying on the manually entered "Brillouin pixel size" value.
- The manually entered "Brillouin pixel size" field in **6. Scale bar** is kept only as a fallback, used solely for TIFFs that carry no readable calibration (e.g. an export that was never calibrated). It is labeled "(fallback)" in the UI.
- Brightfield scale bars are derived from that same (embedded-or-fallback) calibration and the field of view of the matching measurement's Brillouin image, so they stay correct even across measurements that were acquired with different calibrations.

Compatibility
- Existing settings files remain compatible; the manual pixel-size fields are unchanged in the config format, just reduced to a fallback role.

## v1.7.3

Fixes
- Fixed the top colorbar tick label being cropped in individually exported images (e.g. **Export individual rendered images...** with **Include standalone colorbars** enabled) when that channel had no colorbar title set. Vertical headroom for the top tick label is now always reserved whenever a colorbar is drawn, not only when a title is present.

Compatibility
- Rendering fix only; no effect on the main panel export (which was not affected by this bug) or on saved settings files.
