#!/usr/bin/env python

import os
import glob
import subprocess
import filecmp
import logging
import config_launcher
import time
import calendar
import met_util as util
from config_wrapper import ConfigWrapper

# TODO: move test results to separate file for readability

def get_param_list(param_a, param_b):
    metplus_home = "/d1/mccabe/METplus"
    a_conf = metplus_home+"/internal_tests/use_cases/system.a.conf"
    b_conf = metplus_home+"/internal_tests/use_cases/system.b.conf"
    params_a = param_a.split(",")
    params_b = param_b.split(",")
    params_a = params_a + [a_conf]
    params_b = params_b + [b_conf]
    return params_a, params_b


def get_params(param_a, param_b):
    params_a, params_b = get_param_list(param_a, param_b)

    logger = logging.getLogger('master_metplus')    

    # read A confs
    (parm, infiles, moreopt) = config_launcher.parse_launch_args(params_a,
                                                                 None, None,
                                                                 logger)
    p = ConfigWrapper(config_launcher.launch(infiles, moreopt), None)

    # read B confs     
    (parm, infiles, moreopt) = config_launcher.parse_launch_args(params_b,
                                                                 None, None,
                                                                 logger)
    p_b = ConfigWrapper(config_launcher.launch(infiles, moreopt), None)
    return p, p_b


def run_test_use_case(param_a, param_b, run_a, run_b):
    params_a, params_b = get_param_list(param_a, param_b)
    p, p_b = get_params(param_a, param_b)
    # run A
    if run_a:
        cmd = os.path.join(p.getdir("METPLUS_BASE"),"ush","master_metplus.py")
        for parm in params_a:
            cmd += " -c "+parm
        print("CMD A:"+cmd)
        process = subprocess.Popen(cmd, shell=True)
        process.wait()

    # run B
    if run_b:
        cmd = os.path.join(p_b.getdir("METPLUS_BASE"),"ush","master_metplus.py")
        for parm in params_b:
            cmd += " -c "+parm
        print("CMD B:"+cmd)
        process = subprocess.Popen(cmd, shell=True)
        process.wait()

def compare_results(param_a, param_b):
    p, p_b = get_params(param_a, param_b)
    a_dir = p.getdir('OUTPUT_BASE')
    b_dir = p_b.getdir('OUTPUT_BASE')

    print("****************************")
    print("* TEST RESULTS             *")
    print("****************************")
    print(param_a+" vs")
    print(param_b)
    good = True

    processes = util.getlist(p.getstr('config', 'PROCESS_LIST'))
    # TODO: Not all apps that use_init will write dirs on init, could be valid
    use_init = util.is_loop_by_init(p)
    if use_init:
        time_format = p.getstr('config', 'INIT_TIME_FMT')
        start_t = p.getstr('config', 'INIT_BEG')
        end_t = p.getstr('config', 'INIT_END')
        time_interval = p.getint('config', 'INIT_INCREMENT')
    else:
        time_format = p.getstr('config', 'VALID_TIME_FMT')
        start_t = p.getstr('config', 'VALID_BEG')
        end_t = p.getstr('config', 'VALID_END')
        time_interval = p.getint('config', 'VALID_INCREMENT')
        
    loop_time = calendar.timegm(time.strptime(start_t, time_format))
    end_time = calendar.timegm(time.strptime(end_t, time_format))
    while loop_time <= end_time:
        run_time = time.strftime("%Y%m%d%H%M", time.gmtime(loop_time))
        print("Checking "+run_time)
        for process in processes:
            print("Checking output from "+process)
            if process == "GridStat":
                # out_subdir = "uswrp/met_out/QPF/200508070000/grid_stat"
                out_a = p.getdir("GRID_STAT_OUTPUT_DIR")
                out_b = p_b.getdir("GRID_STAT_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/grid_stat/*"
                files_a = glob.glob(glob_string.format(out_a, run_time))
                files_b = glob.glob(glob_string.format(out_b, run_time))
            elif process == "Mode":
                # out_subdir = "uswrp/met_out/QPF/200508070000/grid_stat"
                out_a = p.getdir("MODE_OUTPUT_DIR")
                out_b = p_b.getdir("MODE_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/mode/*"
                files_a = glob.glob(glob_string.format(out_a, run_time))
                files_b = glob.glob(glob_string.format(out_b, run_time))
            elif process == "PcpCombine":
                out_o_a = ""
                out_a = ""
                if p.getbool('config', 'OBS_PCP_COMBINE_RUN', False):
                    out_o_a = p.getdir("OBS_PCP_COMBINE_OUTPUT_DIR")
                    out_o_b = p_b.getdir("OBS_PCP_COMBINE_OUTPUT_DIR")
                    glob_string = "{:s}/{:s}/*"
                    files_o_a = glob.glob(glob_string.format(out_o_a, run_time[0:8]))
                    files_o_b = glob.glob(glob_string.format(out_o_b, run_time[0:8]))
                if p.getbool('config', 'FCST_PCP_COMBINE_RUN', False):
                    out_a = p.getdir("FCST_PCP_COMBINE_OUTPUT_DIR")
                    out_b = p_b.getdir("FCST_PCP_COMBINE_OUTPUT_DIR")
                    glob_string = "{:s}/{:s}/*"
                    files_a = glob.glob(glob_string.format(out_a, run_time[0:8]))
                    files_b = glob.glob(glob_string.format(out_b, run_time[0:8]))
                # if both fcst and obs are set, run obs here then fcst will run
                # at the end of the if blocks
                if out_o_a != "" and out_a != "" and not compare_output_files(files_o_a, files_o_b, a_dir, b_dir):
                    good = False
                # if only obs ran, set variables so that it runs at end of if blocks
                elif out_o_a != "":
                    files_a = files_o_a
                    files_b = files_o_b
            elif process == "RegridDataPlane":
                out_a = p.getdir("OBS_REGRID_DATA_PLANE_OUTPUT_DIR")
                out_b = p_b.getdir("OBS_REGRID_DATA_PLANE_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/*"
                files_a = glob.glob(glob_string.format(out_a, run_time[0:8]))
                files_b = glob.glob(glob_string.format(out_b, run_time[0:8]))
            elif process == "TcPairs":
                out_a = p.getdir("TC_PAIRS_DIR")
                out_b = p_b.getdir("TC_PAIRS_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/*"
                files_a = glob.glob(glob_string.format(out_a, run_time[0:8]))
                files_b = glob.glob(glob_string.format(out_b, run_time[0:8]))
            elif process == "ExtractTiles":
                # TODO FIX DIR
                out_a = p.getdir("EXTRACT_OUT_DIR")
                out_b = p_b.getdir("EXTRACT_TILES_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/*/*"
                date_dir = run_time[0:8]+"_"+run_time[8:10]
                files_a = glob.glob(glob_string.format(out_a, date_dir))
                files_b = glob.glob(glob_string.format(out_b, date_dir))
            elif process == "SeriesByInit": # TODO FIX DIR
                out_a = p.getdir("SERIES_INIT_FILTERED_OUT_DIR")
                out_b = p_b.getdir("SERIES_BY_INIT_FILTERED_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/*/*"
                date_dir = run_time[0:8]+"_"+run_time[8:10]
                files_a = glob.glob(glob_string.format(out_a, date_dir))
                files_b = glob.glob(glob_string.format(out_b, date_dir))
            elif process == "SeriesByLead": # TODO FIX DIR
                out_a = p.getdir("SERIES_LEAD_FILTERED_OUT_DIR")
                out_b = p_b.getdir("SERIES_BY_LEAD_FILTERED_OUTPUT_DIR")
                glob_string = "{:s}/{:s}/*/*"
                date_dir = run_time[0:8]+"_"+run_time[8:10]
                files_a = glob.glob(glob_string.format(out_a, date_dir))
                files_b = glob.glob(glob_string.format(out_b, date_dir))
            else:
                print("PROCESS:"+process+" is not valid")
                continue

            if not compare_output_files(files_a, files_b, a_dir, b_dir):
                good = False

        loop_time += time_interval

    if good:
        print("Success")
    else:
        print("ERROR: Some differences")
    return good

def compare_output_files(files_a, files_b, a_dir, b_dir):
    good = True
    if len(files_a) == 0 and len(files_b) == 0:
        print("WARNING: No files in either directory")
        return True
    if len(files_a) == len(files_b):
        print("Equal number of output files: "+str(len(files_a)))
    else:
        print("ERROR: A output "+str(len(files_a))+" files, B output "+str(len(files_b))+" files")
        good = False

    for afile in files_a:
        bfile = afile.replace(a_dir, b_dir)
        # check if file exists in A and B
        if not os.path.exists(bfile):
            print("ERROR: "+os.path.basename(afile)+" missing in B")
            print(bfile)
            good = False
            continue

        # check if files are equivalent
        # TODO: Improve this, a file path difference in the file could
        #  report a difference when the data is the same
        # for netCDF:
        # ncdump infile1 infile2 outfile can be used then check how many outfile points are non-zero
#        if not filecmp.cmp(afile, bfile):
#            print("ERROR: Differences between "+afile+" and "+bfile)
#            good = False
    return good

def main():
    run_a = False
    run_b = False

    metplus_home = "/d1/mccabe/METplus"
    use_case_dir = os.path.join(metplus_home,"parm/use_cases")
    param_files = [
                    use_case_dir+"/qpf/examples/ruc-vs-s2grib.conf" ,
                    use_case_dir+"/qpf/examples/phpt-vs-s4grib.conf" ,
                    use_case_dir+"/qpf/examples/phpt-vs-mrms-qpe.conf" ,
#                    use_case_dir+"/qpf/examples/hrefmean-vs-qpe-gempak.conf" ,
                    use_case_dir+"/qpf/examples/hrefmean-vs-mrms-qpe.conf" ,
                    use_case_dir+"/qpf/examples/nationalblend-vs-mrms-qpe.conf" ,
#                    use_case_dir+"/feature_relative/feature_relative.conf",
#                    use_case_dir+"/feature_relative/feature_relative.conf,"+use_case_dir+"/feature_relative/examples/series_by_init_12-14_to_12-16.conf" ,
#                    use_case_dir+"/feature_relative/feature_relative.conf,"+use_case_dir+"/feature_relative/examples/series_by_lead_all_fhrs.conf" ,
#                    use_case_dir+"/feature_relative/feature_relative.conf,"+use_case_dir+"/feature_relative/examples/series_by_lead_by_fhr_grouping.conf" ,
                    use_case_dir+"/grid_to_grid/examples/anom.conf" ,
                    use_case_dir+"/grid_to_grid/examples/anom_height.conf",
                    use_case_dir+"/grid_to_grid/examples/sfc.conf" ,
                    use_case_dir+"/grid_to_grid/examples/precip.conf",
                    use_case_dir+"/grid_to_grid/examples/precip_continuous.conf" ,
                    use_case_dir+"/mode/examples/hrefmean-vs-mrms-qpe.conf",
                    use_case_dir+"/mode/examples/phpt-vs-qpe.conf",
                    use_case_dir+"/ensemble/examples/hrrr_ensemble_sfc.conf" #,
#                   use_case_dir+"/grid_to_obs/grid_to_obs.conf,"+use_case_dir+"/grid_to_obs/examples/conus_surface.conf",
#                   use_case_dir+"/grid_to_obs/grid_to_obs.conf,"+use_case_dir+"/grid_to_obs/examples/upper_air.conf"
                  ]

    all_good = True
    print("Starting test script")
    for param_file in param_files:
        param_a = param_file.replace(metplus_home,"/d1/mccabe/METplus.a")
        param_b = param_file.replace(metplus_home,"/d1/mccabe/METplus.b")
        run_test_use_case(param_a, param_b, run_a, run_b)

    for param_file in param_files:
        param_a = param_file.replace(metplus_home,"/d1/mccabe/METplus.a")
        param_b = param_file.replace(metplus_home,"/d1/mccabe/METplus.b")
        if not compare_results(param_a, param_b):
            all_good = False

    if all_good:
        print("ALL TESTS PASSED")
    else:
        print("ERROR: Some tests failed")

    

    
if __name__ == "__main__":
    main()
