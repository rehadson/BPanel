# Brillouin Publication Panel Builder v1.6

A local Python desktop application for assembling publication panels from BMicro Brillouin microscopy exports. This does not include original BMicro software and it does not analyse your Brillouin data. For BMicro go https://github.com/BrillouinMicroscopy/BMicro.

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
4. Uncheck measurements you do not want in the panel.
5. Edit column labels if desired, and use **Move up / Move down** to reorder them.
6. Drag the channel names to set row order.
7. In each channel tab, choose whether the row should be included and set its display settings.
8. Click **Update preview**.
9. Click **Export panel...** and choose PDF, SVG, PNG, or TIFF.


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

A single colorbar is drawn for each quantitative row, so all images in that row always use one shared scale.

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

## Changes in v1.5:
- Added optional export of individual rendered images from the current panel.
- Added export options dialog with support for:
  - full panel only
  - individual images only
  - full panel + individual images
- Individual images are rendered with the same visual settings as the panel:
  - colormap
  - min/max range or percentile scaling
  - scale factor and offset
  - interpolation
  - raster DPI
- Added optional standalone colorbars for exported Brillouin individual images.
- In comparison mode, exported individual images follow the selected comparison Z plane for stack datasets.
- In Z-stack mode, exported individual images include all displayed planes using names like sample_Z1_shift.png.
- Individual exports are written into a companion folder named <panel_stem>_individual.

Brillouin Publication Panel Builder v1.6

## Changes in v1.6:
- Fixed standalone individual-image colorbars so numeric tick labels are no longer clipped off the right edge.
- Standalone exports now reserve explicit right-side space for colorbar values.
- If a standalone colorbar title is enabled, a small top margin is also reserved so the title is not clipped.
- All v1.5 individual-export behavior is retained.

