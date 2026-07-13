# COBRA2026 GC Tools

Tools for the **COBRA2026** challenge hosted on grand-challenge.org. This package converts the public
COBRA2026 dataset and generates the input and ground-truth data used on the Grand Challenge (GC) platform.

## Contents

| Path | Purpose |
| --- | --- |
| `generate_gc_data.py` | Main script, batch-converts the release dataset into GC format. |
| `sample_reconstruction.py` | Example FDK reconstruction of a GC-format case into a CT-aligned volume. |
| `utils/projection.py` | Vendor-specific projection corrections (I0/air-scan, scatter, log-transform). |
| `utils/reconstruction.py` | RTK FDK reconstruction helpers (ITK↔SimpleITK conversion, HU conversion). |
| `utils/geometry.py` | RTK geometry conversion between XML and JSON. |
| `utils/scatter_corrector.py` | Varian scatter-correction implementation. |
| `utils/xim_reader.py` | Reader for Varian `.xim` air-scan images. |
| `configs/{F,G}_corrections.yaml` | Per-case calibration paths (air scans + scatter XML) for the Varian centers. |

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

---

### `generate_gc_data.py`

Batch-converts downloaded COBRA2026 cases into GC-platform format.

## Usage

```bash
python gc-tools/generate_gc_data.py \
    --download-dir /path/to/cobra2026_release \
    --output-dir   /path/to/gc_output
```

### Arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `-d`, `--download-dir` | yes | — | Release directory containing the downloaded COBRA2026 data. |
| `-o`, `--output-dir` | yes | — | Directory to write the GC-format data to. |
| `-c`, `--centers` | no | `A B C D F G` | Space-separated centers to process. |

Example — process only the two Varian centers:

```bash
python generate_gc_data.py -d /data/release -o /data/gc -c F G
```

## Expected input layout

The download directory expects the folder structure of the COBRA2026 release:

## Output layout

For every input case the script creates `<output-dir>/<CENTER>/<CASE>/` with:

| File | Source | Processing |
| --- | --- | --- |
| `cbct_projections.mha` | `projections.mha` | Vendor correction (Elekta I0, or Varian scatter + air-scan I0). |
| `cbct_projections_simulated.mha` | `projections_simulated.mha` | Cast to float32 and log-transformed. |
| `cbct_geometry.json` | `geometry.xml` | RTK geometry converted XML → JSON. |
| `cbct_metadata.json` | `metadata.yaml` | Converted YAML → JSON. |
| `cbct_fov.mha` | `fov_cbct_nocouch.mha` | Copied unchanged. |
| `ct.mha` | `ct_def_masked.mha` | Copied unchanged. |
| `cbct_rtk.mha` | `cbct_rtk.mha` | Copied unchanged. |

---

### `sample_reconstruction.py`

Example script that reconstructs a GC-format case into a CT-aligned volume using RTK's
FDK cone-beam filter. It demonstrates the full pipeline in `utils/reconstruction.py`:
read projections/FOV/geometry, run FDK, correct the image orientation to match the CT,
convert to Hounsfield Units, and write the result.

## Usage

```bash
python sample_reconstruction.py \
    --data-dir /project_data_2/cbct/COBRA/data/GC \
    --cases F003 \
    --simulated
```

Run with no arguments to use the defaults below.

### Arguments

| Flag | Example | Description |
| --- | --- | --- |
| `--data-dir` | `/project_data_2/cbct/COBRA/data/GC/COBRA2026_Val/` | Root of the GC-format data (`<DATA_DIR>/<CENTER>/<CASE>/`). |
| `--cases` | `F003` | One or more case IDs to reconstruct. The leading letter selects the center/vendor. |
| `--simulated` | - | Flag; when present, reconstruct `cbct_projections_simulated.mha` instead of the real projections. |

### Per-case processing

For each case the script:

1. Selects the vendor from the case's center letter (`F`/`G` → Varian, else Elekta).
2. Reads `cbct_projections[_simulated].mha`, `cbct_fov.mha`, and `cbct_geometry.json`.
3. For Varian panels wider than 850 mm, crops 128 columns from each side to avoid reconstruction artifacts.
4. Derives the output size/spacing/origin from the FOV mask.
5. Runs FDK reconstruction (GPU), using vendor-specific Hann cut-off frequencies (0.4 for Varian, 0.99 for Elekta).
6. Fixes the image orientation to align with the CT and converts to HU.
7. Writes `recon.mha` (or `recon_sim.mha` when `SIMULATED`) into the case directory.

> **Note:** FDK reconstruction uses the CUDA RTK filters and requires a GPU-enabled RTK/ITK build.

## Standalone geometry conversion

`utils/geometry.py` can also be run directly to convert a single geometry file in
either direction (inferred from the file extension):

```bash
python -m utils.geometry input.xml  output.json
python -m utils.geometry input.json output.xml
```
