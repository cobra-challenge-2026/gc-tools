# This script generates input and ground truth data that is 
# conform with the GC platform and is used for the COBRA2026 
# challenge

# This includes generating the following file from the public COBRA2026 dataset:
# cbct_projections.mha
# cbct_projections_simulated.mha
# cbct_geometry.json
# cbct_metadata.json
# cbct_fov.mha (excluding the couch/table behind the patient)
# ct.mha

### IMPORTANT ###:
# - For all centers flood field correction (I0/air_scan) is already applied to the projection data
# - For centers F and G (Varian) scatter correction is also applied
# - All projection data is log transformed so that the values in the projection data represent 
# line integrals of attenuation coefficients.

import os
import shutil
import argparse
