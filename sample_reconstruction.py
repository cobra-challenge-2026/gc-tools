import SimpleITK as sitk
import os
import utils.geometry as geo
import utils.reconstruction as recon

DATA_DIR = "/project_data_2/cbct/COBRA/data/GC"
CASES = ["F003"]
SIMULATED = False

for case in CASES:
    print(f"Reconstructing case: {case} ({'simulated' if SIMULATED else 'real'})")
    #file paths for the selected case
    center = case[0]
    case_dir = os.path.join(DATA_DIR,center,case)
    if SIMULATED:
        cbct_projections_path = os.path.join(case_dir, "cbct_projections_simulated.mha")
    else:
        cbct_projections_path = os.path.join(case_dir, "cbct_projections.mha")
    cbct_fov_path = os.path.join(case_dir, "cbct_fov.mha")
    cbct_geometry_json_path = os.path.join(case_dir, "cbct_geometry.json")
    
    if center in ['F', 'G']:
        vendor = "varian"
    else:
        vendor = "elekta"

    # read files
    projections = sitk.ReadImage(cbct_projections_path)
    fov = sitk.ReadImage(cbct_fov_path)
    geometry = geo.rtk_geometry_from_json(cbct_geometry_json_path)
    
    # for Varian images with very large flat panels, crop the projections to avoid reconstruction artifacts
    # if vendor.lower() == "varian" and projections.GetSize()[0] * projections.GetSpacing()[0] > 850:
    #     projections = projections[128:-128,:,:]
    
    # infer image properties for reconstruction from FOV mask
    size, spacing, origin = recon.get_image_properties_for_recon(fov)
    
    # Run FDK reconstruction
    reconstructed = recon.fdk(
        projections = projections,
        geometry = geometry,
        gpu = True,
        size = size,
        origin = origin,
        spacing = spacing,
        padding = 0.2,
        hann = 0.4 if vendor.lower() == "varian" else 0.99,
        hannY = 0.4 if vendor.lower() == "varian" else 0.99,
    )
    
    # Fix image properties to allign with CT properties, convert to HU and apply FOV mask
    if vendor.lower() == "varian":
        reconstructed = recon.fix_image_properties(reconstructed, order=(1,0,2), flip=(0,1))
    if vendor.lower() == "elekta":  
        reconstructed = recon.fix_image_properties(reconstructed, order = (1,2,0), flip = (0,))
    #reconstructed = sitk.Multiply(reconstructed, sitk.Cast(fov, sitk.sitkFloat32))
    reconstructed = recon.rtk_to_HU(reconstructed) 
    
    # Save output file
    output_path = os.path.join(case_dir, "recon_sim.mha") if SIMULATED else os.path.join(case_dir, "recon.mha")
    sitk.WriteImage(reconstructed, output_path, useCompression=True)