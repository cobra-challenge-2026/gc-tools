"""Convert RTK geometry files XML <-> JSON.

Usage:
    xml -> json:  python geometry <input.xml> <output.json>
    json -> xml:  python geometry <input.json> <output.xml>
"""
import json
import sys
from pathlib import Path
from itk import RTK as rtk

import xmltodict

NUMERIC_KEYS = {
    "SourceToIsocenterDistance",
    "SourceToDetectorDistance",
    "GantryAngle",
    "ProjectionOffsetX",
    "ProjectionOffsetY",
}

def read_geometry(geometry_path:str)->None:
    """
    Read xml RTK geometry file.
    """
    reader = rtk.ThreeDCircularProjectionGeometryXMLFileReader.New()
    reader.SetFilename(geometry_path)
    reader.GenerateOutputInformation()
    return reader.GetGeometry()

def rtk_geometry_from_json(input, from_file=True, verify=False):
    """
    Read json RTK geometry file.
    """
    if from_file:
        with open(input) as f:
            g = json.load(f)["RTKThreeDCircularGeometry"]
    else:
        g = input

    sid_global = g.get("SourceToIsocenterDistance", 0.0)
    sdd_global = g.get("SourceToDetectorDistance", 0.0)
 
    geometry = rtk.ThreeDCircularProjectionGeometry.New()
 
    for p in g["Projections"]:
        geometry.AddProjection(
            p.get("SourceToIsocenterDistance", sid_global),
            p.get("SourceToDetectorDistance", sdd_global),
            p["GantryAngle"],                      
            p.get("ProjectionOffsetX", 0.0),
            p.get("ProjectionOffsetY", 0.0),
            p.get("OutOfPlaneAngle", 0.0),
            p.get("InPlaneAngle", 0.0),
            p.get("SourceOffsetX", 0.0),
            p.get("SourceOffsetY", 0.0),
        )
 
    if g.get("RadiusCylindricalDetector"):
        geometry.SetRadiusCylindricalDetector(g["RadiusCylindricalDetector"])
 
    return geometry

def _postprocess(_path, key, value):
    if key == "Projection":
        return "Projections", value
    if key in NUMERIC_KEYS and value is not None:
        return key, float(value)
    if key == "Matrix" and isinstance(value, str):
        vals = [float(v) for v in value.split()]
        return key, [vals[i * 4:(i + 1) * 4] for i in range(3)]
    return key, value


def _matrix_to_str(rows: list[list[float]]) -> str:
    flat = [v for row in rows for v in row]
    return " ".join(f"{v:.15g}" for v in flat)


def _preprocess_json(data: dict) -> dict:
    """Prepare JSON dict for xmltodict.unparse: rename keys and flatten Matrix."""
    result = {}
    for k, v in data.items():
        xml_key = "Projection" if k == "Projections" else k
        if k == "Matrix" and isinstance(v, list):
            result[xml_key] = _matrix_to_str(v)
        elif isinstance(v, dict):
            result[xml_key] = _preprocess_json(v)
        elif isinstance(v, list):
            result[xml_key] = [
                _preprocess_json(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[xml_key] = v
    return result


def xml_to_json(xml_path: Path) -> dict:
    with open(xml_path) as f:
        return xmltodict.parse(
            f.read(),
            force_list=("Projection",),  # renamed to Projections by postprocessor
            postprocessor=_postprocess,
        )

def json_to_xml(json_path: Path) -> str:
    with open(json_path) as f:
        data = json.load(f)
    prepared = _preprocess_json(data)
    return xmltodict.unparse(prepared, pretty=True, indent="  ")

def rtk_geometry_from_json(input, from_file=True, verify=False):
    """
    Read json RTK geometry file.
    """
    if from_file:
        with open(input) as f:
            g = json.load(f)["RTKThreeDCircularGeometry"]
    else:
        g = input

    sid_global = g.get("SourceToIsocenterDistance", 0.0)
    sdd_global = g.get("SourceToDetectorDistance", 0.0)
 
    geometry = rtk.ThreeDCircularProjectionGeometry.New()
 
    for p in g["Projections"]:
        geometry.AddProjection(
            p.get("SourceToIsocenterDistance", sid_global),
            p.get("SourceToDetectorDistance", sdd_global),
            p["GantryAngle"],                      
            p.get("ProjectionOffsetX", 0.0),
            p.get("ProjectionOffsetY", 0.0),
            p.get("OutOfPlaneAngle", 0.0),
            p.get("InPlaneAngle", 0.0),
            p.get("SourceOffsetX", 0.0),
            p.get("SourceOffsetY", 0.0),
        )
 
    if g.get("RadiusCylindricalDetector"):
        geometry.SetRadiusCylindricalDetector(g["RadiusCylindricalDetector"])
 
    return geometry

def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if src.suffix == ".xml":
        data = xml_to_json(src)
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
    elif src.suffix == ".json":
        xml = json_to_xml(src)
        dst.write_text(xml)
    else:
        print(f"Unknown source extension: {src.suffix}")
        sys.exit(1)


if __name__ == "__main__":
    main()