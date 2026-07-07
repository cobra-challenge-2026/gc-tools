# COBRA2026 GC Tools

Tools for the **COBRA2026** challenge hosted on grand-challenge.org. This package converts the public
COBRA2026 dataset and generates the input and ground-truth data used on the Grand Challenge (GC) platform.

## Contents

| Path | Purpose |
| --- | --- |
| `generate_gc_data.py` | Main entry point — batch-converts the release dataset into GC format. |
| `utils/projection.py` | Vendor-specific projection corrections (I0/air-scan, scatter, log-transform). |
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
| `ct.mha` | `ct_def_masked.mha` | Copied unchanged (ground truth). |

Existing output directories are reused (`makedirs(..., exist_ok=True)`); files are
overwritten.

## Logging and error handling

- Progress is logged to stderr with per-case markers (`[CENTER i/N] Processing case ...`).
  Level names are colorized when the output is an interactive terminal.
- Each case is processed inside a `try/except`: any exception is logged with a full
  traceback and the case is added to a failure list, then the run continues.
- At the end, a summary lists every `CENTER/CASE` that failed, or reports that all
  centers processed successfully.

## Standalone geometry conversion

`utils/geometry.py` can also be run directly to convert a single geometry file in
either direction (inferred from the file extension):

```bash
python -m utils.geometry input.xml  output.json
python -m utils.geometry input.json output.xml
```
