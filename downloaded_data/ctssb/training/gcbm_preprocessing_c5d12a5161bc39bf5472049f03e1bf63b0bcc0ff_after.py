from loghelper import *
import os, sys, argparse, shutil, zipfile
from future.builtins import input
from preprocess_tools import postgis_manage
from configuration.pathregistry import PathRegistry
from configuration.subregionconfig import SubRegionConfig
def main():

    create_script_log(sys.argv[0])
    try:
        parser = argparse.ArgumentParser(description="sets up external data in working directory for subsequent processes")
        parser.add_argument("--pathRegistry", help="path to file registry data")
        parser.add_argument("--subRegionConfig", help="path to sub region data")
        parser.add_argument("--subRegionNames", help="optional comma delimited "+
                            "string of sub region names (as defined in "+
                            "subRegionConfig) to process, if unspecified all "+
                            "regions will be processed")
        parser.add_argument("--spatial", action="store_true", dest="spatial", help="copy spatial files to the working dir")
        parser.add_argument("--future", action="store_true", dest="future", help="copys future projection files to the working dir")
        parser.add_argument("--aspatial", action="store_true", dest="aspatial", help="copy aspatial files to the working dir")
        parser.add_argument("--tools", action="store_true", dest="tools", help="copy tools to the working dir")
        parser.add_argument("--postgis", action="store_true", dest="postgis", help="set up postgis credentials/url")
        parser.add_argument("--cleanup", action="store_true", dest="cleanup", help="clean up any existing files working dir, and databases first")
        parser.set_defaults(spatial=False)
        parser.set_defaults(future=False)
        parser.set_defaults(aspatial=False)
        parser.set_defaults(tools=False)
        parser.set_defaults(postgis=False)
        args = parser.parse_args()

        pathRegistry = PathRegistry(os.path.abspath( args.pathRegistry))
        subRegionConfig = SubRegionConfig(
            os.path.abspath(args.subRegionConfig),
            args.subRegionNames.split(',') if args.subRegionNames else None)

        if not args.spatial \
           and not args.aspatial \
           and not args.tools \
           and not args.future \
           and not args.postgis:
            logging.error("nothing to do")

        if args.postgis:
            logging.info("postgis setup")
            post_gis_variables = [{"name": "PGHOST", "default": "localhost"},
                                  {"name": "PGPORT", "default": "5432" }, 
                                  {"name": "PGUSER",  "default": "postgres"}, 
                                  {"name": "PGPASSWORD", "default": None}]
            print("PostGIS connection variables:")
            pg_var_result = {}
            for pg_var in post_gis_variables:
                input_string = "{v} (push enter for '{d}') : " \
                     .format(v=pg_var["name"], d=pg_var["default"]) \
                     if pg_var["default"] is not None else \
                     "{v} : ".format(v = pg_var["name"])
                result = input(input_string)
                result = pg_var["default"] if len(result) == 0 and pg_var["default"] else result

                pg_var_result[pg_var["name"]] = result
            pg_var_result["PGDATABASE"] = "postgres"

            connectionVarsPath = pathRegistry.GetPath("PostGIS_Connection_Vars")
            if not os.path.exists(os.path.dirname(connectionVarsPath)):
                os.makedirs(os.path.dirname(connectionVarsPath))
            postgis_manage.save_connection_variables(connectionVarsPath, **pg_var_result)
            result = input("test connection? (y/n):")
            if result.lower() in ["yes", "y"]:
                with postgis_manage.connect(**postgis_manage.get_connection_variables(connectionVarsPath)) as conn:
                    if conn.closed:
                        raise RuntimeError("database connection error")
                    logging.info("db connected sucessfully")
                    input("any key to continue")
            if args.cleanup:
                for r in subRegionConfig.GetRegions():
                    logging.info("dropping working db for {}".format(r["Name"]))
                    region_path = r["PathName"]
                    region_postgis_var_path = pathRegistry.GetPath(
                        "PostGIS_Region_Connection_Vars",
                        region_path=region_path)
                    if os.path.exists(region_postgis_var_path):
                        postgis_manage.drop_working_db(
                                pathRegistry.GetPath("PostGIS_Connection_Vars"),
                                region_postgis_var_path)
                        os.remove(region_postgis_var_path)

        if args.aspatial:
            src = pathRegistry.GetPath("Source_External_Aspatial_Dir")
            dst = pathRegistry.GetPath("External_Aspatial_Dir")

            if args.cleanup and os.path.exists(dst):
                logging.info("removing dir {}".format(dst))
                shutil.rmtree(dst)
            logging.info("copying external aspatial data to local working directory")
            logging.info("source: {}".format(src))
            logging.info("destination: {}".format(dst))
            shutil.copytree(src=src, dst=dst)

        if args.tools:
            toolPathPairs = [("Source_GCBM_Dir", "Local_GCBM_Dir"),
                             ("Source_Recliner2GCBM-x64_Dir", "Local_Recliner2GCBM-x64_Dir"),
                             ("Source_Recliner2GCBM-x86_Dir", "Local_Recliner2GCBM-x86_Dir"),
                             ("Source_lostgis_dir", "Local_lostgis_dir")]
            for pair in toolPathPairs:
                src = pathRegistry.GetPath(pair[0])
                dst = pathRegistry.GetPath(pair[1])

                if args.cleanup and os.path.exists(dst):
                    logging.info("removing dir {}".format(dst))
                    shutil.rmtree(dst)
                logging.info("copying external tool from {} to {}".format(pair[0],pair[1]))
                logging.info("source: {}".format(src))
                logging.info("destination: {}".format(dst))
                shutil.copytree(src=src,dst=dst)

        if args.future:
            for region in subRegionConfig.GetRegions():
                for sha_scenario in region["SHAScenarios"]:
                    subdir = os.path.join(*sha_scenario["SubDir"])
                    src = pathRegistry.GetPath("Source_External_Future_Dir",
                                           sha_future_scenario=subdir)
                    dst = pathRegistry.GetPath("Future_Dist_Input_Dir",
                                            region_path=region["PathName"],
                                            sha_future_scenario=sha_scenario["Name"])

                    if args.cleanup and os.path.exists(dst):
                        logging.info("removing dir {}".format(dst))
                        shutil.rmtree(dst)
                    logging.info("copying sha scenario from {} to {}".format(src,dst))
                    logging.info("source: {}".format(src))
                    logging.info("destination: {}".format(dst))
                    shutil.copytree(src=src, dst=dst)


        if args.spatial:
            src = pathRegistry.GetPath("Source_External_Spatial_Dir")
            dst = pathRegistry.GetPath("External_Spatial_Dir")

            if args.cleanup and os.path.exists(dst):
                logging.info("removing dir {}".format(dst))
                shutil.rmtree(dst)

            logging.info("copying external spatial data to local working directory")
            logging.info("source: {}".format(src))
            logging.info("destination: {}".format(dst))
            shutil.copytree(src=src, dst=dst)



    except Exception as ex:
        logging.exception("error")
        sys.exit(1)

    logging.info("all setup tasks finished")

if __name__ == "__main__":
    main()
