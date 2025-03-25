import os, time, sys, shutil, signal, hashlib, argparse, shutil
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), ".."))
import build_support as bs

triggered_builds_str = []
jen = None

def abort_builds(ignore, _):
    for an_invoke_str in triggered_builds_str:
        jen.abort(bs.ProjectInvoke(from_string=an_invoke_str))
    raise bs.BuildAborted()


def main():
    signal.signal(signal.SIGINT, abort_builds)
    signal.signal(signal.SIGABRT, abort_builds)
    signal.signal(signal.SIGTERM, abort_builds)

    # reuse the options from the gasket
    o = bs.Options([sys.argv[0]])
    description="builds a component on jenkins"
    parser= argparse.ArgumentParser(description=description, 
                                    parents=[o._parser], 
                                    conflict_handler="resolve")
    parser.add_argument('--project', dest='project', type=str, default="",
                        help='Project to build. Default project is specified '\
                        'for the branch in build_specification.xml')

    parser.add_argument('--branch', type=str, default="mesa_master",
                        help="Branch specification to build.  "\
                        "See build_specification.xml/branches")


    args = parser.parse_args()
    projects = []
    if args.project:
        projects = args.project.split(",")
    branch = args.branch

    # some build_local params are not handled by the Options, which is
    # used by other modules.  This code strips out incompatible args
    o = bs.Options(["bogus"])
    vdict = vars(args)
    del vdict["project"]
    del vdict["branch"]
    o.__dict__.update(vdict)
    sys.argv = ["bogus"] + o.to_string().split()

    bspec = bs.BuildSpecification()
    bspec.checkout(branch)
    revspec = bs.RevisionSpecification()
    hashstr = hashlib.md5(str(revspec)).hexdigest()

    # create a result_path that is unique for this set of builds
    spec_xml = bs.ProjectMap().build_spec()
    results_dir = spec_xml.find("build_master").attrib["results_dir"]
    result_path = "/".join([results_dir, branch, hashstr])
    o.result_path = result_path
    pm = bs.ProjectMap()
    if not projects:
        branchspec = bspec.branch_specification(branch)
        projects = [branchspec.project]

    # use a global, so signal handler can abort builds when scheduler
    # is interrupted
    global jen

    jen = bs.Jenkins(result_path=result_path,
                     revspec=revspec)


    depGraph = bs.DependencyGraph(projects, o)

    ready_for_build = depGraph.ready_builds()
    assert(ready_for_build)

    completed_builds = []
    failure_builds = []

    success = True

    out_test_dir = pm.output_dir()
    if os.path.exists(out_test_dir):
        bs.rmtree(out_test_dir)
    os.makedirs(out_test_dir)

    # to collate all logs in the scheduler
    out_log_dir = pm.output_dir()
    if os.path.exists(out_log_dir):
        bs.rmtree(out_log_dir)
    os.makedirs(out_log_dir)

    # use a global, so signal handler can abort builds when scheduler
    # is interrupted
    global triggered_builds_str
    while success:
        jen.print_builds()
        builds_in_round = 0
        for an_invoke in ready_for_build:
            status = an_invoke.get_info("status", block=False)

            if status == "success" or status == "unstable":
                # don't rebuild if we have a good build, or just
                # because some tests failure
                completed_builds.append(an_invoke)
                depGraph.build_complete(an_invoke)
                builds_in_round += 1
                print "Already built: " + an_invoke.to_short_string()
                #collate_tests(an_invoke, out_test_dir)
                continue

            proj_build_dir = pm.project_build_dir(an_invoke.project)
            script = proj_build_dir + "/build.py"
            if not os.path.exists(script):
                depGraph.build_complete(an_invoke)
                continue

            try:
                print "Starting: " + an_invoke.to_short_string()
                jen.build(an_invoke)
                an_invoke.set_info("trigger_time", time.time())
                triggered_builds_str.append(str(an_invoke))
            except(bs.BuildInProgress) as e:
                print e
                success = False
                break

        if not success:
            break

        finished = None
        try:
            finished = jen.wait_for_build()
            if finished:
                builds_in_round += 1
        except(bs.BuildFailure) as failure:
            failure.invoke.set_info("status", "failure")
            url = failure.url
            job_name = url.split("/")[-3]
            build_number = url.split("/")[-2]
            build_directory = "/var/lib/jenkins/jobs/" \
                              "{0}/builds/{1}".format(job_name.lower(), 
                                                      build_number)
            if os.path.exists(build_directory):
                log_file = os.path.join(build_directory, "log")
                shutil.copy(log_file, out_log_dir)

            # abort the builds, but let daily/release builds continue
            # as far as possible
            if o.type == "percheckin" or o.type == "developer":
                time.sleep(6)  # quiet period
                for an_invoke_str in triggered_builds_str:
                    print "Aborting: " + an_invoke_str
                    pi = bs.ProjectInvoke(from_string=an_invoke_str)
                    jen.abort(pi)
                    failure_builds.append(pi)
                #CleanServer(o).clean()
                bs.write_summary(pm.source_root(), 
                                 failure_builds + completed_builds, 
                                 jen, 
                                 failure=True)
                raise

            # else for release/daily builds, continue waiting for the
            # rest of the builds.
            print "Build failure: " + failure.url
            print "Build failure: " + str(failure.invoke)
            failure_builds.append(failure.invoke)
            builds_in_round += 1

        if finished:
            finished.invoke.set_info("status", finished.status)
            print "Build finished: " + finished.url
            print "Build finished: " + finished.invoke.to_short_string()

            completed_builds.append(finished.invoke)
            depGraph.build_complete(finished.invoke)
            #collate_tests(finished.invoke, out_test_dir)

        elif not builds_in_round:
            # nothing was built, and there was no failure => the last
            # project is built

            #stub_test_results(out_test_dir, o.hardware)
            # CleanServer(o).clean()
            bs.write_summary(pm.source_root(), 
                             failure_builds + completed_builds, 
                             jen)
            if failure_builds:
                raise bs.BuildFailure(failure_builds[0], "")
            return
            
        ready_for_build = depGraph.ready_builds()

        # filter out builds that have already been triggered
        ready_for_build = [j for j in ready_for_build 
                           if str(j) not in triggered_builds_str]

    src_test_dir = result_path + "/test"
    for a_file in os.listdir(src_test_dir):
        if "xml" in a_file:
            shutil.copyfile(src_test_dir + "/" + a_file, 
                            out_test_dir + "/" + a_file)

if __name__=="__main__":
    try:
        main()
    except SystemExit:
        # Uncomment to determine which version of argparse is throwing
        # us under the bus.

        #  Word of Wisdom: Don't call sys.exit
        #import traceback
        #for x in traceback.format_exception(*sys.exc_info()):
        #    print x
        raise
