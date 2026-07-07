import os
import itk
import yaml
import math
import fnmatch
import logging

import numpy as np
import SimpleITK as sitk
import xml.etree.ElementTree as ET

from tqdm import tqdm
from itk import RTK as rtk

import utils.xim_reader as xim_reader
import utils.geometry as geo
import utils.scatter_corrector as sc

logger = logging.getLogger(__name__)

def correct_i0_elekta(projections: sitk.Image, reconstruction_ini: str) -> sitk.Image:
    """
    Perform I0 correction for elekta projections using ini file parameters.
    """
    ma_scan = float(reconstruction_ini['RECONSTRUCTION']['tubema'])
    ms_scan = float(reconstruction_ini['RECONSTRUCTION']['tubekvlength'])
    kvFilter = reconstruction_ini['RECONSTRUCTION']['kvfilter']
    
    if kvFilter == 'F1':
        ma_air = float(reconstruction_ini['RECONSTRUCTION']['floodimagefilterma'])
        ms_air = float(reconstruction_ini['RECONSTRUCTION']['floodimagefilterms'])
        i0_norm = float(reconstruction_ini['RECONSTRUCTION']['floodimagefilternorm'])
    elif kvFilter == 'F0':
        ma_air = float(reconstruction_ini['RECONSTRUCTION']['floodimageopenma'])
        ms_air = float(reconstruction_ini['RECONSTRUCTION']['floodimageopenms'])
        i0_norm = float(reconstruction_ini['RECONSTRUCTION']['floodimageopennorm'])
    else:
        raise ValueError(f"Unknown KVFilter value: {kvFilter}")
    
    i0 = i0_norm * (ma_scan * ms_scan) / (ma_air * ms_air)
    
    projections = sitk.Cast(projections, sitk.sitkFloat32)
    
    t = sitk.Divide(projections, i0)
    t = sitk.Clamp(t, sitk.sitkFloat32, 1.0/65535.0)
    projections_corrected = -1.0 * sitk.Log(t)
    
    return projections_corrected


def read_air_scans(air_scans_path: str, rotation: str = 'CW', return_sitk = True) -> sitk.Image:
    """
    Read a set of 10 air scans and their header from the specified directory using SimpleITK.
    Assumes air scans are stored as a XIM files.
    """
    try:
        filenames = sorted(fnmatch.filter(os.listdir(air_scans_path), f"Filter*_{rotation}_*.xim"))
        if len(filenames) != 10:
            raise ValueError(f"Expected 10 air scan files in {air_scans_path}, found {len(filenames)}")
    except:
        filenames = sorted(fnmatch.filter(os.listdir(air_scans_path), f"Filter*.xim"))
        if len(filenames) < 10:
            raise ValueError(f"Expected 10 air scan files in {air_scans_path}, found {len(filenames)}")
        
    
    imgs = []
    headers = []
    for f in filenames:
        filepath = os.path.join(air_scans_path, f)
        img, _, meta = xim_reader.read_xim_image(filepath)
        if return_sitk:
            imgs.append(img)
        else:
            imgs.append(sitk.GetArrayFromImage(img))
        headers.append(meta)
    
    return imgs, headers

def get_scan_parameters(xml_path: str):
    """
    Extract scan parameters (mA, ms, kV) from a Varian Scan.xml file.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Remove namespace from tag names
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]  # remove "{namespace}"

    ma = root.find(".//Current").text # type: ignore
    ms = root.find(".//PulseLength").text # type: ignore
    kv = root.find(".//Voltage").text # type: ignore
    
    return float(str(ma)), float(str(ms)), float(str(kv))

def correct_i0_varian(
        projections: sitk.Image, 
        air_scans_dir: str, 
        geometry, 
        scan_xml_path: str,
    ) -> sitk.Image:
    """
    Corrects I0 (air scans/flood field) in Varian CBCT projections using a set of 10 air scans 
    acquired before the scan.
    """
    #Read projections, air scans and gantry angles
    projections_np = sitk.GetArrayFromImage(projections)
    projection_angles = [gantry_angle * 180.0 / np.pi for gantry_angle in geometry.GetGantryAngles()]
    if projection_angles[20] < projection_angles[30]:
        rotation = 'CW'
    else:
        rotation = 'CC'
    logger.info("       Reading air scans...")
    air_imgs, air_header = read_air_scans(air_scans_dir, rotation, return_sitk = False)
    
    air_corr_np = np.zeros_like(projections_np)
    air_scan_angles = [h['GantryRtn'] for h in air_header]
    for i in range(projections_np.shape[0]):
        proj_angle = projection_angles[i]
        #Find index of closest air scan
        closest_idx = np.argmin(np.abs(np.array(air_scan_angles) - proj_angle))
        air_corr_np[i, :, :] = air_imgs[closest_idx][:, :]
    
    # convert back to sitk image
    air_corr = sitk.GetImageFromArray(air_corr_np)
    air_corr.CopyInformation(projections)
    
    #Avoid division by zero
    eps = 1e-6
    air_corr = sitk.Maximum(air_corr, eps)
    
    #scale air scan to acquisition settings
    ma_scan, ms_scan, _  = get_scan_parameters(scan_xml_path)
    ma_air, ms_air = (air_header[0]['KVMilliAmperes'],air_header[0]['KVMilliSeconds'])
    scale_factor = (ma_scan * ms_scan) / (ma_air * ms_air)
    scale_factor = 1
    air_corr = sitk.Multiply(air_corr, scale_factor)
    
    projections = sitk.Cast(projections, sitk.sitkFloat32)  
    t = sitk.Divide(projections, air_corr)
    t = sitk.Clamp(t, sitk.sitkFloat32, 1.0/65535.0)
    projections_corrected = -1.0 * sitk.Log(t)
    return projections_corrected

def correct_scatter_varian(
        projections: sitk.Image, 
        geometry, 
        scattercorxml_path: str,
        airscans_path: str,
        padding: float = 0.1,
        return_scatter: bool = False,
    ) -> sitk.Image:
    """
    Perform scatter correction on Varian CBCT projections using scatter_corrector module.
    """
    
    spacing = projections.GetSpacing()[0:2]
    
    scattercor = sc.VarianScatterCorrection(
        xml_path=scattercorxml_path,
        pixel_pitch_mm=spacing,
        downsample_factor=8
    )
    
    projections_np = sitk.GetArrayFromImage(projections)
    projections_sc_np = np.zeros_like(projections_np)
    scatter_np = np.zeros_like(projections_np)
    air_corr_np = np.zeros_like(projections_np)
    
    projection_angles = [gantry_angle * 180.0 / np.pi for gantry_angle in geometry.GetGantryAngles()]
    if projection_angles[20] < projection_angles[30]:
        rotation = 'CW'
    else:
        rotation = 'CC'
    air_imgs, air_header = read_air_scans(airscans_path, rotation, return_sitk = False)
    air_scan_angles = [h['GantryRtn'] for h in air_header]

    for i in range(projections_np.shape[0]):
        proj_angle = projection_angles[i]
        closest_idx = np.argmin(np.abs(np.array(air_scan_angles) - proj_angle))
        air_corr_np[i, :, :] = air_imgs[closest_idx][:, :]
    
    for i in tqdm(range(projections_np.shape[0])):
        I_raw = projections_np[i,:,:]
        I_air = air_corr_np[i,:,:]
        I_cor_sc, scatter_estimate = scattercor.correct_projection(
            I_raw,
            I_air,
            iterations=8,
            padding=padding
        )
        projections_sc_np[i,:,:] = I_cor_sc
        scatter_np[i,:,:] = scatter_estimate

    projections_sc_sitk = sitk.GetImageFromArray(projections_sc_np)
    projections_sc_sitk.CopyInformation(projections)

    scatter_sitk = sitk.GetImageFromArray(scatter_np)
    scatter_sitk.CopyInformation(projections)
    
    if return_scatter:
        return projections_sc_sitk, scatter_sitk
    else:       
        return projections_sc_sitk

def correct_projections(
    cbct_projections_path,
    reconstruction_ini_path = None, 
    cbct_geometry_path = None,
    scan_xml_path = None,
    scattercorxml_path = None,
    airscans_path = None, 
    vendor = None):
    """
    Apply corrections to projection data based on the vendor and provided parameters.
    """
    cbct_projections_cor = None
    logger.info("       Loading projections...")
    cbct_projections = sitk.ReadImage(cbct_projections_path)
    cbct_projections = sitk.Cast(cbct_projections, sitk.sitkFloat32)
    
    if vendor.lower() == 'elekta':
        logger.info("       Loading reconstruction.yaml...")
        reconstruction_ini = yaml.safe_load(open(reconstruction_ini_path, 'r')) 
        logger.info("       Correcting projections...")
        cbct_projections_cor = correct_i0_elekta(
            cbct_projections, 
            reconstruction_ini
        )
    
    elif vendor.lower() == 'varian':
        logger.info("       Loading geometry.xml...")
        cbct_geometry = geo.read_geometry(cbct_geometry_path)
        # apply no padding for very large flat panels
        if cbct_projections.GetSize()[0] * cbct_projections.GetSpacing()[0] > 850:
            padding_val = 0
            logger.info("       Padding set to 0")
        else:
            padding_val = 0.1
            logger.info("       Padding set to 0.1")
            logger.info("       Correcting projections...")
        cbct_projections_cor = correct_scatter_varian(
            projections = cbct_projections,
            geometry = cbct_geometry,
            scattercorxml_path = scattercorxml_path,
            airscans_path = airscans_path,
            padding = padding_val,
            )
        cbct_projections_cor = correct_i0_varian(
            projections = cbct_projections_cor,
            air_scans_dir = airscans_path,
            geometry = cbct_geometry,
            scan_xml_path= scan_xml_path,
            )
    
    if cbct_projections_cor is None:
        raise ValueError(f"Projection correction failed!")
    return cbct_projections_cor

def log_transform(projections: sitk.Image) -> sitk.Image:
    """
    Apply log-transform to projection data.
    """
    projections = sitk.Cast(projections, sitk.sitkFloat32)
    t = sitk.Divide(projections, 65535.0)
    t = sitk.Clamp(t, sitk.sitkFloat32, 1.0/65535.0)
    projections_log = -1.0 * sitk.Log(t)
    
    return projections_log