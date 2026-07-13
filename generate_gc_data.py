import os
import shutil
import argparse
import fnmatch
import yaml
import utils
import SimpleITK as sitk
import logging
import utils.geometry as geo
import utils.projection as pro
import json

class ColorFormatter(logging.Formatter):
    RESET = "\033[0m"
    LEVEL_COLORS = {
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[32m",      # green
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[1;41m",  # bold, red background
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        # Color only the levelname so timestamps/messages stay readable.
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

_handler = logging.StreamHandler()
_fmt = "%(asctime)s %(levelname)-8s %(message)s"
_datefmt = "%Y-%m-%d %H:%M:%S"
# Only colorize when writing to a real terminal (avoids escape codes in log files).
if _handler.stream.isatty():
    _handler.setFormatter(ColorFormatter(_fmt, datefmt=_datefmt))
else:
    _handler.setFormatter(logging.Formatter(_fmt, datefmt=_datefmt))

logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)

# Resolve config files relative to this script so it can be run from any directory.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate GC-platform input and ground truth data for the "
            "COBRA2026 challenge from the public COBRA2026 dataset."
        )
    )
    parser.add_argument(
        "-c", "--centers",
        nargs="+",
        default=['A', 'B', 'C', 'D', 'F', 'G'],
        help="Centers to process (default: A B C D F G).",
    )
    parser.add_argument(
        "-d", "--download-dir",
        required=True,
        help="Release directory to read the downloaded COBRA2026 data from.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        required=True,
        help="Output directory to write the GC-format data to.",
    )
    return parser.parse_args()

def conform_json(data, schema):
    if schema.get("type") == "object":
        data = data if isinstance(data, dict) else {}
        result = {}

        for key, key_schema in schema.get("properties", {}).items():
            if key in data:
                result[key] = conform_json(data[key], key_schema)
            elif key in schema.get("required", []):
                result[key] = None

        return result

    return data

def main(centers, release_dir, output_dir):
    logger.info("Reading release data from %s", release_dir)
    logger.info("Writing GC data to %s", output_dir)
    logger.info("Processing centers: %s", ", ".join(centers))

    failed_cases = []

    with open(os.path.join(SCRIPT_DIR, "configs", "cbct_metadata_schema.json")) as f:
        metadata_schema = json.load(f)

    for center in centers:
        CASES = os.listdir(os.path.join(release_dir, center))
        if center in ['F', 'G']:
            vendor = "varian"
            with open(os.path.join(SCRIPT_DIR, "configs", f"{center}_corrections.yaml"), 'r') as f:
                corrections = yaml.safe_load(f)
        else:
            vendor = "elekta"
        CASES = sorted(CASES)
        logger.info("Center %s (%s): found %d case(s): %s", center, vendor, len(CASES), CASES)

        for case_idx, case in enumerate(CASES, start=1):
            logger.info("----------------------------")
            logger.info("[%s %d/%d] Processing case %s", center, case_idx, len(CASES), case)
            try:
                case_dir = os.path.join(release_dir, center, case)
                gc_dir = os.path.join(output_dir, center, case)
                if vendor.lower() == "elekta":
                    reconstruction_ini = os.path.join(case_dir, "reconstruction.yaml")
                if vendor.lower() == "varian":
                    scanxml = os.path.join(case_dir, "Scan.xml")
                    scattercorxml = os.path.join(case_dir, corrections[case]["data"]["scattercorxml"])
                    airscans_dir = os.path.join(case_dir, corrections[case]["data"]["airscans"])
                # Create the GC directory if it doesn't exist
                os.makedirs(gc_dir, exist_ok=True)

                # Define the file paths for the input and ground truth data
                cbct_projections_path = os.path.join(case_dir, "projections.mha")
                cbct_projections_simulated_path = os.path.join(case_dir, "projections_simulated.mha")
                cbct_geometry_path = os.path.join(case_dir, "geometry.xml")
                cbct_metadata_path = os.path.join(case_dir, "metadata.yaml")
                cbct_fov_path = os.path.join(case_dir, "fov_cbct_nocouch.mha")
                ct_path = os.path.join(case_dir, "ct_def_masked.mha")
                cbct_path = os.path.join(case_dir, "cbct_rtk.mha")

                # Define the file paths for the output data in the GC format
                gc_cbct_projections_path = os.path.join(gc_dir, "cbct_projections.mha")
                gc_cbct_projections_simulated_path = os.path.join(gc_dir, "cbct_projections_simulated.mha")
                gc_cbct_geometry_path = os.path.join(gc_dir, "cbct_geometry.json")
                gc_cbct_metadata_path = os.path.join(gc_dir, "cbct_metadata.json")
                gc_cbct_fov_path = os.path.join(gc_dir, "cbct_fov.mha")
                gc_ct_path = os.path.join(gc_dir, "ct.mha")
                gc_cbct_path = os.path.join(gc_dir, "cbct.mha")

                ### Apply corrections to projection data and save the corrected projections to output dir
                logger.info("  Correcting projections (%s) -> %s", vendor, gc_cbct_projections_path)
                if vendor.lower() == "varian":
                    cbct_projections_cor = pro.correct_projections(
                        cbct_projections_path = cbct_projections_path,
                        cbct_geometry_path = cbct_geometry_path,
                        vendor = vendor,
                        scan_xml_path = scanxml,
                        scattercorxml_path = scattercorxml,
                        airscans_path = airscans_dir,
                    )
                elif vendor.lower() == "elekta":
                    cbct_projections_cor = pro.correct_projections(
                        cbct_projections_path = cbct_projections_path,
                        reconstruction_ini_path = reconstruction_ini,
                        vendor = vendor,
                    )
                sitk.WriteImage(cbct_projections_cor, gc_cbct_projections_path, useCompression=True)

                # Log-transform the simulated projections and save to output dir
                logger.info("  Log-transforming simulated projections -> %s", gc_cbct_projections_simulated_path)
                cbct_projections_simulated = sitk.ReadImage(cbct_projections_simulated_path)
                cbct_projections_simulated = sitk.Cast(cbct_projections_simulated, sitk.sitkFloat32)
                cbct_projections_simulated_log = pro.log_transform(cbct_projections_simulated)
                sitk.WriteImage(cbct_projections_simulated_log, gc_cbct_projections_simulated_path, useCompression=True)

                ### convert geometry from xml to json
                logger.info("  Converting geometry xml -> %s", gc_cbct_geometry_path)
                geometry_json = geo.xml_to_json(xml_path=cbct_geometry_path)
                with open(gc_cbct_geometry_path, "w") as f:
                    json.dump(geometry_json, f, indent=2)

                ### convert metadata from yaml to json and make sure it conforms to the GC metadata schema
                logger.info("  Converting metadata yaml -> %s", gc_cbct_metadata_path)
                with open(cbct_metadata_path, 'r') as f:
                    metadata_yaml = yaml.safe_load(f)
                metadata_json = conform_json(metadata_yaml, metadata_schema)
                with open(gc_cbct_metadata_path, "w") as f:
                    json.dump(metadata_json, f, indent=2)
                
                ### copy fov, ct and cbct to output dir
                logger.info("  Copying fov, ct and cbct to %s", gc_dir)
                shutil.copy(cbct_fov_path, gc_cbct_fov_path)
                shutil.copy(ct_path, gc_ct_path)
                shutil.copy(cbct_path, gc_cbct_path)

                logger.info("[%s %d/%d] Done: %s", center, case_idx, len(CASES), case)
            except Exception:
                failed_cases.append((center, case))
                logger.exception("[%s %d/%d] FAILED: %s", center, case_idx, len(CASES), case)
                continue

    if failed_cases:
        logger.warning("Completed with %d failed case(s):", len(failed_cases))
        for center, case in failed_cases:
            logger.warning("  %s/%s", center, case)
    else:
        logger.info("All centers processed successfully.")


if __name__ == "__main__":
    args = parse_args()
    main(centers=args.centers, release_dir=args.download_dir, output_dir=args.output_dir)










