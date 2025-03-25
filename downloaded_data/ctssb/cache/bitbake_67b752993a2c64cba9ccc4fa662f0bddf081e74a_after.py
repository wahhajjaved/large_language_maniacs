#
# BitBake ToasterUI Implementation
#
# Copyright (C) 2013        Intel Corporation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import datetime
import sys
import bb
import re
import subprocess


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "toaster.toastermain.settings")

import toaster.toastermain.settings as toaster_django_settings
from toaster.orm.models import Build, Task, Recipe, Layer_Version, Layer, Target, LogMessage
from toaster.orm.models import Variable, VariableHistory
from toaster.orm.models import Target_Package, Build_Package, Build_File
from toaster.orm.models import Task_Dependency, Build_Package_Dependency
from toaster.orm.models import Target_Package_Dependency, Recipe_Dependency
from bb.msg import BBLogFormatter as format

class ORMWrapper(object):
    """ This class creates the dictionaries needed to store information in the database
        following the format defined by the Django models. It is also used to save this
        information in the database.
    """

    def __init__(self):
        pass


    def create_build_object(self, build_info):

        build = Build.objects.create(
                                    machine=build_info['machine'],
                                    image_fstypes=build_info['image_fstypes'],
                                    distro=build_info['distro'],
                                    distro_version=build_info['distro_version'],
                                    started_on=build_info['started_on'],
                                    completed_on=build_info['completed_on'],
                                    cooker_log_path=build_info['cooker_log_path'],
                                    build_name=build_info['build_name'],
                                    bitbake_version=build_info['bitbake_version'])

        return build

    def create_target_objects(self, target_info):
        targets = []
        for tgt_name in target_info['targets']:
            tgt_object = Target.objects.create( build = target_info['build'],
                                    target = tgt_name,
                                    is_image = False,
                                    file_name = "",
                                    file_size = 0);
            targets.append(tgt_object)
        return targets

    def update_build_object(self, build, errors, warnings, taskfailures):

        outcome = Build.SUCCEEDED
        if errors or taskfailures:
            outcome = Build.FAILED

        build.completed_on = datetime.datetime.now()
        build.errors_no = errors
        build.warnings_no = warnings
        build.outcome = outcome
        build.save()


    def get_update_task_object(self, task_information):
        task_object, created = Task.objects.get_or_create(
                                build=task_information['build'],
                                recipe=task_information['recipe'],
                                task_name=task_information['task_name'],
                                )

        for v in vars(task_object):
            if v in task_information.keys():
                vars(task_object)[v] = task_information[v]
        # if we got covered by a setscene task, we're SSTATE
        if task_object.outcome == Task.OUTCOME_COVERED and 1 == Task.objects.filter(task_executed=True, build = task_object.build, recipe = task_object.recipe, task_name=task_object.task_name+"_setscene").count():
            task_object.outcome = Task.OUTCOME_SSTATE
            outcome_task_setscene = Task.objects.get(task_executed=True, build = task_object.build,
                                    recipe = task_object.recipe, task_name=task_object.task_name+"_setscene").outcome
            if outcome_task_setscene == Task.OUTCOME_SUCCESS:
                task_object.sstate_result = Task.SSTATE_RESTORED
            elif outcome_task_setscene == Task.OUTCOME_FAILED:
                task_object.sstate_result = Task.SSTATE_FAILED

        # mark down duration if we have a start time
        if 'start_time' in task_information.keys():
            duration = datetime.datetime.now() - task_information['start_time']
            task_object.elapsed_time = duration.total_seconds()

        task_object.save()
        return task_object


    def get_update_recipe_object(self, recipe_information):

        recipe_object, created = Recipe.objects.get_or_create(
                                         layer_version=recipe_information['layer_version'],
                                         file_path=recipe_information['file_path'])

        for v in vars(recipe_object):
            if v in recipe_information.keys():
                vars(recipe_object)[v] = recipe_information[v]

        recipe_object.save()

        return recipe_object

    def get_layer_version_object(self, layer_version_information):

        layer_version_object = Layer_Version.objects.get_or_create(
                                    layer = layer_version_information['layer'],
                                    branch = layer_version_information['branch'],
                                    commit = layer_version_information['commit'],
                                    priority = layer_version_information['priority']
                                    )

        layer_version_object[0].save()

        return layer_version_object[0]

    def get_update_layer_object(self, layer_information):

        layer_object = Layer.objects.get_or_create(
                                name=layer_information['name'],
                                local_path=layer_information['local_path'],
                                layer_index_url=layer_information['layer_index_url'])
        layer_object[0].save()

        return layer_object[0]


    def save_target_package_information(self, target_obj, packagedict, bldpkgs, recipes):
        for p in packagedict:
            packagedict[p]['object'] = Target_Package.objects.create( target = target_obj,
                                        name = p,
                                        size = packagedict[p]['size'])
            if p in bldpkgs:
                packagedict[p]['object'].version = bldpkgs[p]['version']
                packagedict[p]['object'].recipe =  recipes[bldpkgs[p]['pn']]
                packagedict[p]['object'].save()

        for p in packagedict:
            for (px,deptype) in packagedict[p]['depends']:
                Target_Package_Dependency.objects.create( package = packagedict[p]['object'],
                                        depends_on = packagedict[px]['object'],
                                        dep_type = deptype);


    def create_logmessage(self, log_information):
        log_object = LogMessage.objects.create(
                        build = log_information['build'],
                        level = log_information['level'],
                        message = log_information['message'])

        for v in vars(log_object):
            if v in log_information.keys():
                vars(log_object)[v] = log_information[v]

        return log_object.save()


    def save_build_package_information(self, build_obj, package_info, recipes):
        # create and save the object
        bp_object = Build_Package.objects.create( build = build_obj,
                                       recipe = recipes[package_info['PN']],
                                       name = package_info['PKG'],
                                       version = package_info['PKGV'],
                                       revision = package_info['PKGR'],
                                       summary = package_info['SUMMARY'],
                                       description = package_info['DESCRIPTION'],
                                       size = int(package_info['PKGSIZE']) * 1024,
                                       section = package_info['SECTION'],
                                       license = package_info['LICENSE'],
                                       )
        # save any attached file information
        for path in package_info['FILES_INFO']:
                fo = Build_File.objects.create( bpackage = bp_object,
                                        path = path,
                                        size = package_info['FILES_INFO'][path] )

        # save soft dependency information
        if 'RDEPENDS' in package_info and package_info['RDEPENDS']:
            for p in bb.utils.explode_deps(package_info['RDEPENDS']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RDEPENDS)
        if 'RPROVIDES' in package_info and package_info['RPROVIDES']:
            for p in bb.utils.explode_deps(package_info['RPROVIDES']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RPROVIDES)
        if 'RRECOMMENDS' in package_info and package_info['RRECOMMENDS']:
            for p in bb.utils.explode_deps(package_info['RRECOMMENDS']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RRECOMMENDS)
        if 'RSUGGESTS' in package_info and package_info['RSUGGESTS']:
            for p in bb.utils.explode_deps(package_info['RSUGGESTS']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RSUGGESTS)
        if 'RREPLACES' in package_info and package_info['RREPLACES']:
            for p in bb.utils.explode_deps(package_info['RREPLACES']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RREPLACES)
        if 'RCONFLICTS' in package_info and package_info['RCONFLICTS']:
            for p in bb.utils.explode_deps(package_info['RCONFLICTS']):
                Build_Package_Dependency.objects.get_or_create( package = bp_object,
                    depends_on = p, dep_type = Build_Package_Dependency.TYPE_RCONFLICTS)

        return bp_object

    def save_build_variables(self, build_obj, vardump):
        for k in vardump:
            if not bool(vardump[k]['func']):
                value = vardump[k]['v'];
                if value is None:
                    value = ''
                desc = vardump[k]['doc'];
                if desc is None:
                    var_words = [word for word in k.split('_')]
                    root_var = "_".join([word for word in var_words if word.isupper()])
                    if root_var and root_var != k and root_var in vardump:
                        desc = vardump[root_var]['doc']
                if desc is None:
                    desc = ''
                variable_obj = Variable.objects.create( build = build_obj,
                    variable_name = k,
                    variable_value = value,
                    description = desc)
                for vh in vardump[k]['history']:
                    VariableHistory.objects.create( variable = variable_obj,
                            file_name = vh['file'],
                            line_number = vh['line'],
                            operation = vh['op'])

class BuildInfoHelper(object):
    """ This class gathers the build information from the server and sends it
        towards the ORM wrapper for storing in the database
        It is instantiated once per build
        Keeps in memory all data that needs matching before writing it to the database
    """

    def __init__(self, server, has_build_history = False):
        self._configure_django()
        self.internal_state = {}
        self.task_order = 0
        self.server = server
        self.orm_wrapper = ORMWrapper()
        self.has_build_history = has_build_history
        self.tmp_dir = self.server.runCommand(["getVariable", "TMPDIR"])[0]

    def _configure_django(self):
        # Add toaster to sys path for importing modules
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'toaster'))

    ###################
    ## methods to convert event/external info into objects that the ORM layer uses

    def _get_layer_dict(self, layer_path):

        layer_info = {}
        layer_name = layer_path.split('/')[-1]
        layer_url = 'http://layers.openembedded.org/layerindex/layer/{layer}/'
        layer_url_name = self._get_url_map_name(layer_name)

        layer_info['name'] = layer_name
        layer_info['local_path'] = layer_path
        layer_info['layer_index_url'] = layer_url.format(layer=layer_url_name)

        return layer_info

    def _get_url_map_name(self, layer_name):
        """ Some layers have a different name on openembedded.org site,
            this method returns the correct name to use in the URL
        """

        url_name = layer_name
        url_mapping = {'meta': 'openembedded-core'}

        for key in url_mapping.keys():
            if key == layer_name:
                url_name = url_mapping[key]

        return url_name

    def _get_layer_information(self):

        layer_info = {}

        return layer_info

    def _get_layer_version_information(self, layer_object):

        layer_version_info = {}
        layer_version_info['build'] = self.internal_state['build']
        layer_version_info['layer'] = layer_object
        layer_version_info['branch'] = self._get_git_branch(layer_object.local_path)
        layer_version_info['commit'] = self._get_git_revision(layer_object.local_path)
        layer_version_info['priority'] = 0

        return layer_version_info


    def _get_git_branch(self, layer_path):
        branch = subprocess.Popen("git symbolic-ref HEAD 2>/dev/null ", cwd=layer_path, shell=True, stdout=subprocess.PIPE).communicate()[0]
        branch = branch.replace('refs/heads/', '').rstrip()
        return branch

    def _get_git_revision(self, layer_path):
        revision = subprocess.Popen("git rev-parse HEAD 2>/dev/null ", cwd=layer_path, shell=True, stdout=subprocess.PIPE).communicate()[0].rstrip()
        return revision


    def _get_build_information(self):
        build_info = {}
        # Generate an identifier for each new build

        build_info['machine'] = self.server.runCommand(["getVariable", "MACHINE"])[0]
        build_info['distro'] = self.server.runCommand(["getVariable", "DISTRO"])[0]
        build_info['distro_version'] = self.server.runCommand(["getVariable", "DISTRO_VERSION"])[0]
        build_info['started_on'] = datetime.datetime.now()
        build_info['completed_on'] = datetime.datetime.now()
        build_info['image_fstypes'] = self._remove_redundant(self.server.runCommand(["getVariable", "IMAGE_FSTYPES"])[0] or "")
        build_info['cooker_log_path'] = self.server.runCommand(["getVariable", "BB_CONSOLELOG"])[0]
        build_info['build_name'] = self.server.runCommand(["getVariable", "BUILDNAME"])[0]
        build_info['bitbake_version'] = self.server.runCommand(["getVariable", "BB_VERSION"])[0]

        return build_info

    def _get_task_information(self, event, recipe):


        task_information = {}
        task_information['build'] = self.internal_state['build']
        task_information['outcome'] = Task.OUTCOME_NA
        task_information['recipe'] = recipe
        task_information['task_name'] = event.taskname
        try:
            # some tasks don't come with a hash. and that's ok
            task_information['sstate_checksum'] = event.taskhash
        except AttributeError:
            pass
        return task_information

    def _get_layer_version_for_path(self, path):
        def _slkey(layer_version):
            return len(layer_version.layer.local_path)

        # Heuristics: we always match recipe to the deepest layer path that
        # we can match to the recipe file path
        for bl in sorted(self.internal_state['layer_versions'], reverse=True, key=_slkey):
            if (path.startswith(bl.layer.local_path)):
                return bl

        #TODO: if we get here, we didn't read layers correctly
        assert False
        return None

    def _get_recipe_information_from_build_event(self, event):

        layer_version_obj = self._get_layer_version_for_path(re.split(':', event.taskfile)[-1])

        recipe_info = {}
        recipe_info['layer_version'] = layer_version_obj
        recipe_info['file_path'] = re.split(':', event.taskfile)[-1]

        return recipe_info

    def _get_task_build_stats(self, task_object):
        bs_path = self._get_path_information(task_object)
        for bp in bs_path:  # TODO: split for each target
            task_build_stats = self._get_build_stats_from_file(bp, task_object.task_name)

        return task_build_stats

    def _get_path_information(self, task_object):
        build_stats_format = "{tmpdir}/buildstats/{target}-{machine}/{buildname}/{package}/"
        build_stats_path = []

        for t in self.internal_state['targets']:
            target = t.target
            machine = self.internal_state['build'].machine
            buildname = self.internal_state['build'].build_name
            pe, pv = task_object.recipe.version.split(":",1)
            if len(pe) > 0:
                package = task_object.recipe.name + "-" + pe + "_" + pv
            else:
                package = task_object.recipe.name + "-" + pv

            build_stats_path.append(build_stats_format.format(tmpdir=self.tmp_dir, target=target,
                                                     machine=machine, buildname=buildname,
                                                     package=package))

        return build_stats_path

    def _get_build_stats_from_file(self, bs_path, task_name):

        task_bs_filename = str(bs_path) + str(task_name)
        task_bs = open(task_bs_filename, 'r')

        cpu_usage = 0
        disk_io = 0
        startio = ''
        endio = ''

        for line in task_bs.readlines():
            if line.startswith('CPU usage: '):
                cpu_usage = line[11:]
            elif line.startswith('EndTimeIO: '):
                endio = line[11:]
            elif line.startswith('StartTimeIO: '):
                startio = line[13:]

        task_bs.close()

        if startio and endio:
            disk_io = int(endio.strip('\n ')) - int(startio.strip('\n '))

        if cpu_usage:
            cpu_usage = float(cpu_usage.strip('% \n'))

        task_build_stats = {'cpu_usage': cpu_usage, 'disk_io': disk_io}

        return task_build_stats

    def _remove_redundant(self, string):
        ret = []
        for i in string.split():
            if i not in ret:
                ret.append(i)
        return " ".join(ret)


    ################################
    ## external available methods to store information

    def store_layer_info(self):
        layers = self.server.runCommand(["getVariable", "BBLAYERS"])[0].strip().split(" ")
        self.internal_state['layers'] = []
        for layer_path in { l for l in layers if len(l) }:
            layer_information = self._get_layer_dict(layer_path)
            self.internal_state['layers'].append(self.orm_wrapper.get_update_layer_object(layer_information))

    def store_started_build(self, event):

        build_information = self._get_build_information()

        build_obj = self.orm_wrapper.create_build_object(build_information)
        self.internal_state['build'] = build_obj

        # create target information
        target_information = {}
        target_information['targets'] = event.getPkgs()
        target_information['build'] = build_obj

        self.internal_state['targets'] = self.orm_wrapper.create_target_objects(target_information)

        # Load layer information for the build
        self.internal_state['layer_versions'] = []
        for layer_object in self.internal_state['layers']:
            layer_version_information = self._get_layer_version_information(layer_object)
            self.internal_state['layer_versions'].append(self.orm_wrapper.get_layer_version_object(layer_version_information))

        del self.internal_state['layers']
        # Save build configuration
        self.orm_wrapper.save_build_variables(build_obj, self.server.runCommand(["getAllKeysWithFlags", ["doc", "func"]])[0])


    def update_build_information(self, event, errors, warnings, taskfailures):
        if 'build' in self.internal_state:
            self.orm_wrapper.update_build_object(self.internal_state['build'], errors, warnings, taskfailures)

    def store_started_task(self, event):
        identifier = event.taskfile + event.taskname

        recipe_information = self._get_recipe_information_from_build_event(event)
        recipe = self.orm_wrapper.get_update_recipe_object(recipe_information)

        task_information = self._get_task_information(event, recipe)
        task_information['outcome'] = Task.OUTCOME_NA

        if isinstance(event, bb.runqueue.runQueueTaskSkipped):
            task_information['task_executed'] = False
            if event.reason == "covered":
                task_information['outcome'] = Task.OUTCOME_COVERED
            if event.reason == "existing":
                task_information['outcome'] = Task.OUTCOME_EXISTING
        else:
            task_information['task_executed'] = True
            if 'noexec' in vars(event) and event.noexec == True:
                task_information['script_type'] = Task.CODING_NOEXEC

        self.task_order += 1
        task_information['order'] = self.task_order
        task_obj = self.orm_wrapper.get_update_task_object(task_information)

        self.internal_state[identifier] = {'start_time': datetime.datetime.now()}

    def update_and_store_task(self, event):
        identifier = event.taskfile + event.taskname
        recipe_information = self._get_recipe_information_from_build_event(event)
        recipe = self.orm_wrapper.get_update_recipe_object(recipe_information)
        task_information = self._get_task_information(event,recipe)
        try:
            task_information['start_time'] = self.internal_state[identifier]['start_time']
        except:
            pass

        if 'logfile' in vars(event):
            task_information['logfile'] = event.logfile

        if '_message' in vars(event):
            task_information['message'] = event._message

        if 'taskflags' in vars(event):
            # with TaskStarted, we get even more information
            if 'python' in event.taskflags.keys() and event.taskflags['python'] == '1':
                task_information['script_type'] = Task.CODING_PYTHON
            else:
                task_information['script_type'] = Task.CODING_SHELL

        if isinstance(event, (bb.runqueue.runQueueTaskCompleted, bb.runqueue.sceneQueueTaskCompleted)):
            task_information['outcome'] = Task.OUTCOME_SUCCESS
            task_build_stats = self._get_task_build_stats(self.orm_wrapper.get_update_task_object(task_information))
            task_information['cpu_usage'] = task_build_stats['cpu_usage']
            task_information['disk_io'] = task_build_stats['disk_io']
            del self.internal_state[identifier]

        if isinstance(event, (bb.runqueue.runQueueTaskFailed, bb.runqueue.sceneQueueTaskFailed)):
            task_information['outcome'] = Task.OUTCOME_FAILED
            del self.internal_state[identifier]

        self.orm_wrapper.get_update_task_object(task_information)


    def read_target_package_dep_data(self, event):
        # for all targets
        for target in self.internal_state['targets']:
            # verify that we have something to read
            if not target.is_image or not self.has_build_history:
                print "not collecting package info ", target.is_image, self.has_build_history
                break

            # TODO this is a temporary replication of the code in buildhistory.bbclass
            # This MUST be changed to query the actual BUILD_DIR_IMAGE in the target context when
            # the capability will be implemented in Bitbake

            MACHINE_ARCH, error = self.server.runCommand(['getVariable', 'MACHINE_ARCH'])
            TCLIBC, error = self.server.runCommand(['getVariable', 'TCLIBC'])
            BUILDHISTORY_DIR, error = self.server.runCommand(['getVariable', 'BUILDHISTORY_DIR'])
            BUILDHISTORY_DIR_IMAGE = "%s/images/%s/%s/%s" % (BUILDHISTORY_DIR, MACHINE_ARCH, TCLIBC, target.target)

            self.internal_state['packages'] = {}

            with open("%s/installed-package-sizes.txt" % BUILDHISTORY_DIR_IMAGE, "r") as fin:
                for line in fin:
                    line = line.rstrip(";")
                    psize, px = line.split("\t")
                    punit, pname = px.split(" ")
                    self.internal_state['packages'][pname.strip()] = {'size':int(psize)*1024, 'depends' : []}

            with open("%s/depends.dot" % BUILDHISTORY_DIR_IMAGE, "r") as fin:
                p = re.compile(r' -> ')
                dot = re.compile(r'.*style=dotted')
                for line in fin:
                    line = line.rstrip(';')
                    linesplit = p.split(line)
                    if len(linesplit) == 2:
                        pname = linesplit[0].rstrip('"').strip('"')
                        dependsname = linesplit[1].split(" ")[0].strip().strip(";").strip('"').rstrip('"')
                        deptype = Target_Package_Dependency.TYPE_DEPENDS
                        if dot.match(line):
                            deptype = Target_Package_Dependency.TYPE_RECOMMENDS
                        if not pname in self.internal_state['packages']:
                            self.internal_state['packages'][pname] = {'size': 0, 'depends' : []}
                        if not dependsname in self.internal_state['packages']:
                            self.internal_state['packages'][dependsname] = {'size': 0, 'depends' : []}
                        self.internal_state['packages'][pname]['depends'].append((dependsname, deptype))

            self.orm_wrapper.save_target_package_information(target,
                        self.internal_state['packages'],
                        self.internal_state['bldpkgs'], self.internal_state['recipes'])


    def store_dependency_information(self, event):
        # save layer version priorities
        if 'layer-priorities' in event._depgraph.keys():
            for lv in event._depgraph['layer-priorities']:
                (name, path, regexp, priority) = lv
                layer_version_obj = self._get_layer_version_for_path(path[1:]) # paths start with a ^
                assert layer_version_obj is not None
                layer_version_obj.priority = priority
                layer_version_obj.save()

        # save build time package information
        self.internal_state['bldpkgs'] = {}
        for pkg  in event._depgraph['packages']:
            self.internal_state['bldpkgs'][pkg] = event._depgraph['packages'][pkg]

        # save recipe information
        self.internal_state['recipes'] = {}
        for pn in event._depgraph['pn']:

            file_name = re.split(':', event._depgraph['pn'][pn]['filename'])[-1]
            layer_version_obj = self._get_layer_version_for_path(re.split(':', file_name)[-1])

            assert layer_version_obj is not None

            recipe_info = {}
            recipe_info['name'] = pn
            recipe_info['version'] = event._depgraph['pn'][pn]['version']
            recipe_info['layer_version'] = layer_version_obj
            recipe_info['summary'] = event._depgraph['pn'][pn]['summary']
            recipe_info['license'] = event._depgraph['pn'][pn]['license']
            recipe_info['description'] = event._depgraph['pn'][pn]['description']
            recipe_info['section'] = event._depgraph['pn'][pn]['section']
            recipe_info['licensing_info'] = 'Not Available'
            recipe_info['homepage'] = event._depgraph['pn'][pn]['homepage']
            recipe_info['bugtracker'] = event._depgraph['pn'][pn]['bugtracker']
            recipe_info['file_path'] = file_name
            recipe = self.orm_wrapper.get_update_recipe_object(recipe_info)
            if 'inherits' in event._depgraph['pn'][pn].keys():
                recipe.is_image = True in map(lambda x: x.endswith('image.bbclass'), event._depgraph['pn'][pn]['inherits'])
            else:
                recipe.is_image = False
            if recipe.is_image:
                for t in self.internal_state['targets']:
                    if pn == t.target:
                        t.is_image = True
                        t.save()
            self.internal_state['recipes'][pn] = recipe

        # save recipe dependency
        # buildtime
        for recipe in event._depgraph['depends']:
            try:
                target = self.internal_state['recipes'][recipe]
                for dep in event._depgraph['depends'][recipe]:
                    dependency = self.internal_state['recipes'][dep]
                    Recipe_Dependency.objects.get_or_create( recipe = target,
                            depends_on = dependency, dep_type = Recipe_Dependency.TYPE_DEPENDS)
            except KeyError:    # we'll not get recipes for key w/ values listed in ASSUME_PROVIDED
                pass

        # runtime
        for recipe in event._depgraph['rdepends-pn']:
            try:
                target = self.internal_state['recipes'][recipe]
                for dep in event._depgraph['rdepends-pn'][recipe]:
                    dependency = self.internal_state['recipes'][dep]
                    Recipe_Dependency.objects.get_or_create( recipe = target,
                            depends_on = dependency, dep_type = Recipe_Dependency.TYPE_RDEPENDS)

            except KeyError:    # we'll not get recipes for key w/ values listed in ASSUME_PROVIDED
                pass

        # save all task information
        def _save_a_task(taskdesc):
            spec = re.split(r'\.', taskdesc);
            pn = ".".join(spec[0:-1])
            taskname = spec[-1]
            e = event
            e.taskname = pn
            recipe = self.internal_state['recipes'][pn]
            task_info = self._get_task_information(e, recipe)
            task_info['task_name'] = taskname
            task_obj = self.orm_wrapper.get_update_task_object(task_info)
            return task_obj

        for taskdesc in event._depgraph['tdepends']:
            target = _save_a_task(taskdesc)
            for taskdesc1 in event._depgraph['tdepends'][taskdesc]:
                dep = _save_a_task(taskdesc1)
                Task_Dependency.objects.get_or_create( task = target, depends_on = dep )

    def store_build_package_information(self, event):
        package_info = event.data
        self.orm_wrapper.save_build_package_information(self.internal_state['build'],
                            package_info,
                            self.internal_state['recipes'],
                            )

    def _store_log_information(self, level, text):
        log_information = {}
        log_information['build'] = self.internal_state['build']
        log_information['level'] = level
        log_information['message'] = text
        self.orm_wrapper.create_logmessage(log_information)

    def store_log_info(self, text):
        self._store_log_information(LogMessage.INFO, text)

    def store_log_warn(self, text):
        self._store_log_information(LogMessage.WARNING, text)

    def store_log_error(self, text):
        self._store_log_information(LogMessage.ERROR, text)

    def store_log_event(self, event):
        # look up license files info from insane.bbclass
        m = re.match("([^:]*): md5 checksum matched for ([^;]*)", event.msg)
        if m:
            (pn, fn) = m.groups()
            self.internal_state['recipes'][pn].licensing_info = fn
            self.internal_state['recipes'][pn].save()

        if event.levelno < format.WARNING:
            return
        if not 'build' in self.internal_state:
            return
        log_information = {}
        log_information['build'] = self.internal_state['build']
        if event.levelno >= format.ERROR:
            log_information['level'] = LogMessage.ERROR
        elif event.levelno == format.WARNING:
            log_information['level'] = LogMessage.WARNING
        log_information['message'] = event.msg
        log_information['pathname'] = event.pathname
        log_information['lineno'] = event.lineno
        self.orm_wrapper.create_logmessage(log_information)

