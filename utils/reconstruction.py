import itk
import math
import logging

import SimpleITK as sitk
import numpy as np

from itk import RTK as rtk

logger = logging.getLogger(__name__)

def itk_to_sitk(itk_image):
    array = itk.array_from_image(itk_image)
    
    sitk_image = sitk.GetImageFromArray(array)
    sitk_image.SetSpacing(list(itk_image.GetSpacing()))
    start_index = itk_image.GetBufferedRegion().GetIndex()
    new_origin = itk_image.TransformIndexToPhysicalPoint(start_index)
    
    sitk_image.SetOrigin(list(new_origin))
    itk_direction = itk_image.GetDirection()
    itk_dims = itk_image.GetImageDimension()
    flat_direction = []
    for i in range(itk_dims):
        for j in range(itk_dims):
            flat_direction.append(itk_direction.GetVnlMatrix().get(i, j))
            
    sitk_image.SetDirection(flat_direction)
    
    return sitk_image

def sitk_to_itk(sitk_image):
    arr = sitk.GetArrayFromImage(sitk_image)
    itk_image = itk.image_view_from_array(arr)

    dimension = sitk_image.GetDimension()

    itk_image.SetOrigin(sitk_image.GetOrigin())
    itk_image.SetSpacing(sitk_image.GetSpacing())

    sitk_direction = sitk_image.GetDirection()
    direction_np = np.array(sitk_direction, dtype=float).reshape((dimension, dimension))

    itk_image.SetDirection(direction_np)

    return itk_image

def fdk(
        projections: sitk.Image, 
        geometry, 
        gpu: bool = True, 
        size = None, 
        origin = None, 
        spacing = None,
        padding = 0.2,
        hann: float = 1,
        hannY: float = 1,
        ) -> sitk.Image:
    """
    Perform FDK reconstruction using rtk FDKConeBeamReconstructionFilter
    """
    projections = sitk_to_itk(projections)
    
    CPUImageType = itk.Image[itk.F, 3]
    if gpu:
        GPUImageType = itk.CudaImage[itk.F, 3]
        ConstantImageSourceType = rtk.ConstantImageSource[GPUImageType]
    else:
        ConstantImageSourceType = rtk.ConstantImageSource[CPUImageType]
    constantImageSource = ConstantImageSourceType.New()
    
    if spacing is None:
        output_spacing = [1,1,1]
    else:
        output_spacing = spacing
    
    sid = geometry.GetSourceToIsocenterDistances()[0]
    sdd = geometry.GetSourceToDetectorDistances()[0]
    mag = sdd / sid
    
    proj_offset_x = geometry.GetProjectionOffsetsX()[0]
   
    proj_size = projections.GetLargestPossibleRegion().GetSize()
    proj_spacing = projections.GetSpacing()
    
    det_width_mm = proj_size[0] * proj_spacing[0]
    det_height_mm = proj_size[1] * proj_spacing[1]
    
    dist_from_center_to_edge = abs(proj_offset_x) + (det_width_mm / 2.0)
    fov_radius_iso = dist_from_center_to_edge / mag
    fov_diameter_iso = fov_radius_iso * 2.0
    fov_height_iso = det_height_mm / mag

    if size is None:
        output_size = itk.Size[3]()
        output_size[0] = math.ceil(fov_diameter_iso / output_spacing[0])
        output_size[2] = math.ceil(fov_diameter_iso / output_spacing[2])
        output_size[1] = math.ceil(fov_height_iso   / output_spacing[1])
    else:
        output_size = size
    
    if origin is None:
        output_origin = itk.Point[itk.F, 3]()
        output_origin[0] = -0.5 * (output_size[0] - 1) * output_spacing[0]
        output_origin[1] = -0.5 * (output_size[1] - 1) * output_spacing[1]
        output_origin[2] = -0.5 * (output_size[2] - 1) * output_spacing[2]
    else:
        output_origin = origin
         
    constantImageSource.SetOrigin(output_origin)
    constantImageSource.SetSpacing(output_spacing)
    constantImageSource.SetSize(output_size)
    constantImageSource.SetConstant(0.0)

    if gpu:
        projections_input = GPUImageType.New()
        projections_input.SetPixelContainer(projections.GetPixelContainer())
        projections_input.CopyInformation(projections)
        projections_input.SetBufferedRegion(projections.GetBufferedRegion())
        projections_input.SetRequestedRegion(projections.GetRequestedRegion())
        FDKGPUType = rtk.CudaFDKConeBeamReconstructionFilter
        feldkamp = FDKGPUType.New()
    else:
        projections_input = projections
        FDKCPUType = rtk.FDKConeBeamReconstructionFilter[CPUImageType]
        feldkamp = FDKCPUType.New()

    if gpu:
        ddf = rtk.CudaDisplacedDetectorImageFilter.New()
        ddf.SetInput(projections_input)
        pssf = rtk.CudaParkerShortScanImageFilter.New()
    else:
        ddf = rtk.DisplacedDetectorForOffsetFieldOfViewImageFilter[
            CPUImageType
        ].New()
        ddf.SetInput(projections_input)
        pssf = rtk.ParkerShortScanImageFilter[CPUImageType].New()

    # Displaced detector weighting
    ddf.SetGeometry(geometry)
    ddf.SetDisable(False)

    # Short scan image filter
    pssf.SetInput(ddf.GetOutput())
    pssf.SetGeometry(geometry)
    pssf.InPlaceOff()
    pssf.SetAngularGapThreshold(20 * 3.14159265359 / 180.0)
    
    feldkamp.SetInput(0, constantImageSource.GetOutput())
    feldkamp.SetInput(1, pssf.GetOutput())
    feldkamp.SetGeometry(geometry)
    feldkamp.GetRampFilter().SetTruncationCorrection(padding)
    feldkamp.GetRampFilter().SetHannCutFrequency(hann)
    feldkamp.GetRampFilter().SetHannCutFrequencyY(hannY)
    feldkamp.Update()

    if gpu:
        recon_gpu = feldkamp.GetOutput()
        recon_cpu = CPUImageType.New()
        recon_cpu.SetPixelContainer(recon_gpu.GetPixelContainer())
        recon_cpu.CopyInformation(recon_gpu)
        recon_cpu.SetBufferedRegion(recon_gpu.GetBufferedRegion())
        recon_cpu.SetRequestedRegion(recon_gpu.GetRequestedRegion())
    else:
        recon_cpu = feldkamp.GetOutput()
        
    recon = itk_to_sitk(recon_cpu)
    
    return recon

def fix_image_properties(img: sitk.Image, order = (1, 2, 0), flip=()) -> sitk.Image:
    """
    This function ensures the RTK reconstructed image is in a similar configuration as the .SCAN file loaded with xdrt
    """
    img_np = sitk.GetArrayFromImage(img)
    img_np = np.transpose(img_np, order)
    img_np = np.flip(img_np, axis=flip)
    
    new_img = sitk.GetImageFromArray(img_np)
    
    # order indexes numpy (z,y,x) axes; origin/spacing are (x,y,z), so axis i maps to index 2-i
    old_origin = img.GetOrigin()
    new_origin = (old_origin[2 - order[2]], old_origin[2 - order[1]], old_origin[2 - order[0]])

    old_spacing = img.GetSpacing()
    new_spacing = (old_spacing[2 - order[2]], old_spacing[2 - order[1]], old_spacing[2 - order[0]])
    
    new_img.SetOrigin(new_origin)
    new_img.SetSpacing(new_spacing)
    
    return new_img

def get_image_properties_for_recon(img: sitk.Image) -> tuple:
    """
    This function returns the size, spacing, and origin of an image for use in FDK reconstruction adhering to the RTK convention
    """
    size = [img.GetSize()[0], img.GetSize()[2], img.GetSize()[1]]
    spacing = [img.GetSpacing()[0], img.GetSpacing()[2], img.GetSpacing()[1]]
    origin = [img.GetOrigin()[0], img.GetOrigin()[2], img.GetOrigin()[1]]
    
    return size, spacing, origin

def rtk_to_HU(img: sitk.Image) -> sitk.Image:
    """
    Converts RTK reconstructed image to approximate Hounsfield Units (HU)
    CBCT_HU =  CBCT_μ * 2^16 - 1024
    """
    img = img*(2**16)-1024
    return img