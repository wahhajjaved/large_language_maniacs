import numpy as np

## info
# LAS Orientation
# i : RL
# i-: LR
# j : PA
# j-: AP
# k : IS
# k-: SI
general_info = {"MagneticFieldStrength": 3.0, "ManufacturersModelName": "Philips Ingenia"}
sense_info = {"ParallelAcquisitionTechnique": "SENSE", "ParallelReductionFactorInPlane": 2}

# TR=2sec, 43 slices,  # ascending sliceorder
rs_info = {"SliceEncodingDirection": "k", "SliceTiming": np.arange(0, 2.0, 2. / 43)}


def filter_not_3d_flair(s):
    if "_3d_" in s:
        return False
    else:
        return True


dataset_description_v2 = {"Name": "LHAB longitudinal healthy aging brain study",
                          "BIDSVersion": "1.2.1"
                          }


def get_info_list_v2(do_deface):
    info_list_v2 = [
        # anatomical
        {"bids_name": "T1w", "bids_modality": "anat", "search_str": "t1w_", "deface": do_deface,
         "add_info": {**general_info}
         },
        {"bids_name": "T2w", "bids_modality": "anat", "search_str": "t2w_", "deface": do_deface,
         "add_info": {**general_info}
         },

        # flair
        {"bids_name": "FLAIR", "bids_modality": "anat", "search_str": ["2dflair_", "flair_longtr", "_flair_"],
         "post_glob_filter": filter_not_3d_flair, "acq": "2D", "deface": do_deface, "add_info": {**general_info}
         },
        {"bids_name": "FLAIR", "bids_modality": "anat", "search_str": ["3dflair", "3d_brain_view_flair"], "acq": "3D",
         "deface": do_deface, "add_info": {**general_info}
         },

        # dwi
        {"bids_name": "dwi", "bids_modality": "dwi", "search_str": ["_dti_T", "dti_high"], "only_use_last": True,
         "acq": "ap", "add_info": {**general_info, **sense_info, "PhaseEncodingDirection": "j-"}
         },

        # func
        {"bids_name": "bold", "bids_modality": "func", "search_str": ["_fmri_T", "resting2000"], "task": "rest",
         "physio": True, "add_info": {**general_info, **sense_info, **rs_info, "PhaseEncodingDirection": "j-"}
         },

        # fieldmaps
        {"bids_name": "epi", "bids_modality": "fmap", "search_str": ["_fmri_pa_T", "resting_pa"],
         "acq": "bold", "direction": "PA",
         "add_info": {**general_info, **sense_info, **rs_info, "PhaseEncodingDirection": "j"}
         },
        {"bids_name": "epi", "bids_modality": "fmap", "search_str": ["_dti_pa_T", "dti_nodif_pa"],
         "acq": "dwi",
         "direction": "PA", "add_info": {**general_info, **sense_info, "PhaseEncodingDirection": "j"}
         },
        {"bids_name": "epi", "bids_modality": "fmap", "search_str": ["_dti_ap_T", "dti_nodif_ap"],
         "acq": "dwi",
         "direction": "AP", "add_info": {**general_info, **sense_info, "PhaseEncodingDirection": "j-"}
         }
    ]
    return info_list_v2
