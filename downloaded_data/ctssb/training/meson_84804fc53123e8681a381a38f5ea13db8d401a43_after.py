# Copyright 2014-2016 The Meson development team

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os, sys
import pickle

from mesonbuild import compilers
from . import backends
from .. import build
from .. import dependencies
from .. import mlog
import xml.etree.ElementTree as ET
import xml.dom.minidom
from ..coredata import MesonException
from ..environment import Environment

class RegenInfo():
    def __init__(self, source_dir, build_dir, depfiles):
        self.source_dir = source_dir
        self.build_dir = build_dir
        self.depfiles = depfiles

class Vs2010Backend(backends.Backend):
    def __init__(self, build):
        super().__init__(build)
        self.project_file_version = '10.0.30319.1'
        # foo.c compiles to foo.obj, not foo.c.obj
        self.source_suffix_in_objs = False

    def generate_custom_generator_commands(self, target, parent_node):
        all_output_files = []
        commands = []
        inputs = []
        outputs = []
        for genlist in target.get_generated_sources():
            if isinstance(genlist, build.CustomTarget):
                all_output_files += [os.path.join(self.get_target_dir(genlist), i) for i in genlist.output]
            else:
                generator = genlist.get_generator()
                exe = generator.get_exe()
                infilelist = genlist.get_infilelist()
                outfilelist = genlist.get_outfilelist()
                if isinstance(exe, build.BuildTarget):
                    exe_file = os.path.join(self.environment.get_build_dir(), self.get_target_filename(exe))
                else:
                    exe_file = exe.get_command()[0]
                base_args = generator.get_arglist()
                for i in range(len(infilelist)):
                    if len(infilelist) == len(outfilelist):
                        sole_output = os.path.join(self.get_target_private_dir(target), outfilelist[i])
                    else:
                        sole_output = ''
                    curfile = infilelist[i]
                    infilename = os.path.join(self.environment.get_source_dir(), curfile)
                    outfiles = genlist.get_outputs_for(curfile)
                    outfiles = [os.path.join(self.get_target_private_dir(target), of) for of in outfiles]
                    all_output_files += outfiles
                    args = [x.replace("@INPUT@", infilename).replace('@OUTPUT@', sole_output)\
                            for x in base_args]
                    args = [x.replace("@SOURCE_DIR@", self.environment.get_source_dir()).replace("@BUILD_DIR@", self.get_target_private_dir(target))
                            for x in args]
                    fullcmd = [exe_file] + args
                    commands.append(' '.join(self.special_quote(fullcmd)))
                    inputs.append(infilename)
                    outputs.extend(outfiles)
        if len(commands) > 0:
            idgroup = ET.SubElement(parent_node, 'ItemDefinitionGroup')
            cbs = ET.SubElement(idgroup, 'CustomBuildStep')
            ET.SubElement(cbs, 'Command').text = '\r\n'.join(commands)
            ET.SubElement(cbs, 'Inputs').text = ";".join(inputs)
            ET.SubElement(cbs, 'Outputs').text = ';'.join(outputs)
            ET.SubElement(cbs, 'Message').text = 'Generating custom sources.'
            pg = ET.SubElement(parent_node, 'PropertyGroup')
            ET.SubElement(pg, 'CustomBuildBeforeTargets').text = 'ClCompile'
        return all_output_files

    def generate(self, interp):
        self.interpreter = interp
        self.platform = 'Win32'
        self.buildtype = self.environment.coredata.get_builtin_option('buildtype')
        sln_filename = os.path.join(self.environment.get_build_dir(), self.build.project_name + '.sln')
        projlist = self.generate_projects()
        self.gen_testproj('RUN_TESTS', os.path.join(self.environment.get_build_dir(), 'RUN_TESTS.vcxproj'))
        self.gen_regenproj('REGEN', os.path.join(self.environment.get_build_dir(), 'REGEN.vcxproj'))
        self.generate_solution(sln_filename, projlist)
        self.generate_regen_info()
        Vs2010Backend.touch_regen_timestamp(self.environment.get_build_dir())

    @staticmethod
    def get_regen_stampfile(build_dir):
        return os.path.join(os.path.join(build_dir, Environment.private_dir), 'regen.stamp')

    @staticmethod
    def touch_regen_timestamp(build_dir):
        open(Vs2010Backend.get_regen_stampfile(build_dir), 'w').close()

    def generate_regen_info(self):
        deps = self.get_regen_filelist()
        regeninfo = RegenInfo(self.environment.get_source_dir(),
                              self.environment.get_build_dir(),
                              deps)
        pickle.dump(regeninfo, open(os.path.join(self.environment.get_scratch_dir(), 'regeninfo.dump'), 'wb'))

    def get_obj_target_deps(self, obj_list):
        result = {}
        for o in obj_list:
            if isinstance(o, build.ExtractedObjects):
                result[o.target.get_id()] = True
        return result.keys()

    def determine_deps(self, p):
        all_deps = {}
        target = self.build.targets[p[0]]
        if isinstance(target, build.CustomTarget):
            for d in target.get_target_dependencies():
                all_deps[d.get_id()] = True
            return all_deps
        if isinstance(target, build.RunTarget):
            for d in [target.command] + target.args:
                if isinstance(d, build.BuildTarget):
                    all_deps[d.get_id()] = True
                return all_deps
        for ldep in target.link_targets:
            all_deps[ldep.get_id()] = True
        for objdep in self.get_obj_target_deps(target.objects):
            all_deps[objdep] = True
        for gendep in target.generated:
            if isinstance(gendep, build.CustomTarget):
                all_deps[gendep.get_id()] = True
            else:
                gen_exe = gendep.generator.get_exe()
                if isinstance(gen_exe, build.Executable):
                    all_deps[gen_exe.get_id()] = True
        return all_deps

    def generate_solution(self, sln_filename, projlist):
        ofile = open(sln_filename, 'w')
        ofile.write('Microsoft Visual Studio Solution File, Format Version 11.00\n')
        ofile.write('# Visual Studio 2010\n')
        prj_templ = prj_line = 'Project("{%s}") = "%s", "%s", "{%s}"\n'
        for p in projlist:
            prj_line = prj_templ % (self.environment.coredata.guid, p[0], p[1], p[2])
            ofile.write(prj_line)
            all_deps = self.determine_deps(p)
            ofile.write('\tProjectSection(ProjectDependencies) = postProject\n')
            regen_guid = self.environment.coredata.regen_guid
            ofile.write('\t\t{%s} = {%s}\n' % (regen_guid, regen_guid))
            for dep in all_deps.keys():
                guid = self.environment.coredata.target_guids[dep]
                ofile.write('\t\t{%s} = {%s}\n' % (guid, guid))
            ofile.write('EndProjectSection\n')
            ofile.write('EndProject\n')
        test_line = prj_templ % (self.environment.coredata.guid,
                                 'RUN_TESTS', 'RUN_TESTS.vcxproj', self.environment.coredata.test_guid)
        ofile.write(test_line)
        ofile.write('EndProject\n')
        regen_line = prj_templ % (self.environment.coredata.guid,
                                 'REGEN', 'REGEN.vcxproj', self.environment.coredata.regen_guid)
        ofile.write(regen_line)
        ofile.write('EndProject\n')
        ofile.write('Global\n')
        ofile.write('\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n')
        ofile.write('\t\t%s|%s = %s|%s\n' % (self.buildtype, self.platform, self.buildtype, self.platform))
        ofile.write('\tEndGlobalSection\n')
        ofile.write('\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n')
        ofile.write('\t\t{%s}.%s|%s.ActiveCfg = %s|%s\n' % 
                    (self.environment.coredata.regen_guid, self.buildtype, self.platform,
                     self.buildtype, self.platform))
        ofile.write('\t\t{%s}.%s|%s.Build.0 = %s|%s\n' % 
                    (self.environment.coredata.regen_guid, self.buildtype, self.platform,
                     self.buildtype, self.platform))
        for p in projlist:
            ofile.write('\t\t{%s}.%s|%s.ActiveCfg = %s|%s\n' % 
                        (p[2], self.buildtype, self.platform,
                         self.buildtype, self.platform))
            if not isinstance(self.build.targets[p[0]], build.RunTarget):
                ofile.write('\t\t{%s}.%s|%s.Build.0 = %s|%s\n' %
                            (p[2], self.buildtype, self.platform,
                             self.buildtype, self.platform))
        ofile.write('\t\t{%s}.%s|%s.ActiveCfg = %s|%s\n' % 
                    (self.environment.coredata.test_guid, self.buildtype, self.platform,
                     self.buildtype, self.platform))
        ofile.write('\tEndGlobalSection\n')
        ofile.write('\tGlobalSection(SolutionProperties) = preSolution\n')
        ofile.write('\t\tHideSolutionNode = FALSE\n')
        ofile.write('\tEndGlobalSection\n')
        ofile.write('EndGlobal\n')

    def generate_projects(self):
        projlist = []
        comp = None
        for l, c in self.environment.coredata.compilers.items():
            if l == 'c' or l == 'cpp':
                comp = c
                break
        if comp is None:
            raise RuntimeError('C and C++ compilers missing.')
        for name, target in self.build.targets.items():
            outdir = os.path.join(self.environment.get_build_dir(), self.get_target_dir(target))
            fname = name + '.vcxproj'
            relname = os.path.join(target.subdir, fname)
            projfile = os.path.join(outdir, fname)
            uuid = self.environment.coredata.target_guids[name]
            self.gen_vcxproj(target, projfile, uuid, comp)
            projlist.append((name, relname, uuid))
        return projlist

    def split_sources(self, srclist):
        sources = []
        headers = []
        objects = []
        languages = []
        for i in srclist:
            if self.environment.is_header(i):
                headers.append(i)
            elif self.environment.is_object(i):
                objects.append(i)
            elif self.environment.is_source(i):
                sources.append(i)
                lang = self.lang_from_source_file(i)
                if lang not in languages:
                    languages.append(lang)
            else:
                # Everything that is not an object or source file is considered a header.
                headers.append(i)
        return (sources, headers, objects, languages)

    def target_to_build_root(self, target):
        if target.subdir == '':
            return ''

        directories = os.path.normpath(target.subdir).split(os.sep)
        return os.sep.join(['..']*len(directories))

    def special_quote(self, arr):
        return ['&quot;%s&quot;' % i for i in arr]

    def create_basic_crap(self, target):
        project_name = target.name
        root = ET.Element('Project', {'DefaultTargets' : "Build",
                                      'ToolsVersion' : '4.0',
                                      'xmlns' : 'http://schemas.microsoft.com/developer/msbuild/2003'})
        confitems = ET.SubElement(root, 'ItemGroup', {'Label' : 'ProjectConfigurations'})
        prjconf = ET.SubElement(confitems, 'ProjectConfiguration',
                                {'Include' : self.buildtype + '|' + self.platform})
        p = ET.SubElement(prjconf, 'Configuration')
        p.text= self.buildtype
        pl = ET.SubElement(prjconf, 'Platform')
        pl.text = self.platform
        globalgroup = ET.SubElement(root, 'PropertyGroup', Label='Globals')
        guidelem = ET.SubElement(globalgroup, 'ProjectGuid')
        guidelem.text = self.environment.coredata.test_guid
        kw = ET.SubElement(globalgroup, 'Keyword')
        kw.text = self.platform + 'Proj'
        p = ET.SubElement(globalgroup, 'Platform')
        p.text= self.platform
        pname= ET.SubElement(globalgroup, 'ProjectName')
        pname.text = project_name
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.Default.props')
        type_config = ET.SubElement(root, 'PropertyGroup', Label='Configuration')
        ET.SubElement(type_config, 'ConfigurationType')
        ET.SubElement(type_config, 'CharacterSet').text = 'MultiByte'
        ET.SubElement(type_config, 'UseOfMfc').text = 'false'
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.props')
        direlem = ET.SubElement(root, 'PropertyGroup')
        fver = ET.SubElement(direlem, '_ProjectFileVersion')
        fver.text = self.project_file_version
        outdir = ET.SubElement(direlem, 'OutDir')
        outdir.text = '.\\'
        intdir = ET.SubElement(direlem, 'IntDir')
        intdir.text = target.get_id() + '\\'
        tname = ET.SubElement(direlem, 'TargetName')
        tname.text = target.name
        return root

    def gen_run_target_vcxproj(self, target, ofname, guid):
        root = self.create_basic_crap(target)
        action = ET.SubElement(root, 'ItemDefinitionGroup')
        customstep = ET.SubElement(action, 'PostBuildEvent')
        cmd_raw = [target.command] + target.args
        cmd = [sys.executable, os.path.join(self.environment.get_script_dir(), 'commandrunner.py'),
               self.environment.get_build_dir(), self.environment.get_source_dir(),
               self.get_target_dir(target)]
        for i in cmd_raw:
            if isinstance(i, build.BuildTarget):
                cmd.append(os.path.join(self.environment.get_build_dir(), self.get_target_filename(i)))
            elif isinstance(i, dependencies.ExternalProgram):
                cmd += i.fullpath
            else:
                cmd.append(i)
        cmd_templ = '''"%s" '''*len(cmd)
        ET.SubElement(customstep, 'Command').text = cmd_templ % tuple(cmd)
        ET.SubElement(customstep, 'Message').text = 'Running custom command.'
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.targets')
        tree = ET.ElementTree(root)
        tree.write(ofname, encoding='utf-8', xml_declaration=True)

    def gen_custom_target_vcxproj(self, target, ofname, guid):
        root = self.create_basic_crap(target)
        action = ET.SubElement(root, 'ItemDefinitionGroup')
        customstep = ET.SubElement(action, 'CustomBuildStep')
        (srcs, ofilenames, cmd) = self.eval_custom_target_command(target, True)
        cmd_templ = '''"%s" '''*len(cmd)
        ET.SubElement(customstep, 'Command').text = cmd_templ % tuple(cmd)
        ET.SubElement(customstep, 'Outputs').text = ';'.join(ofilenames)
        ET.SubElement(customstep, 'Inputs').text = ';'.join(srcs)
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.targets')
        tree = ET.ElementTree(root)
        tree.write(ofname, encoding='utf-8', xml_declaration=True)

    @classmethod
    def lang_from_source_file(cls, src):
        ext = src.split('.')[-1]
        if ext in compilers.c_suffixes:
            return 'c'
        if ext in compilers.cpp_suffixes:
            return 'cpp'
        raise MesonException('Could not guess language from source file %s.' % src)

    def add_pch(self, inc_cl, proj_to_src_dir, pch_sources, source_file):
        if len(pch_sources) <= 1:
            # We only need per file precompiled headers if we have more than 1 language.
            return
        lang = Vs2010Backend.lang_from_source_file(source_file)
        header = os.path.join(proj_to_src_dir, pch_sources[lang][0])
        pch_file = ET.SubElement(inc_cl, 'PrecompiledHeaderFile')
        pch_file.text = header
        pch_include = ET.SubElement(inc_cl, 'ForcedIncludeFiles')
        pch_include.text = header + ';%(ForcedIncludeFiles)'
        pch_out = ET.SubElement(inc_cl, 'PrecompiledHeaderOutputFile')
        pch_out.text = '$(IntDir)$(TargetName)-%s.pch' % lang

    def add_additional_options(self, source_file, parent_node, extra_args, has_additional_options_set):
        if has_additional_options_set:
            # We only need per file options if they were not set per project.
            return
        lang = Vs2010Backend.lang_from_source_file(source_file)
        ET.SubElement(parent_node, "AdditionalOptions").text = ' '.join(extra_args[lang]) + ' %(AdditionalOptions)'

    def gen_vcxproj(self, target, ofname, guid, compiler):
        mlog.debug('Generating vcxproj %s.' % target.name)
        entrypoint = 'WinMainCRTStartup'
        subsystem = 'Windows'
        if isinstance(target, build.Executable):
            conftype = 'Application'
            if not target.gui_app:
                subsystem = 'Console'
                entrypoint = 'mainCRTStartup'
        elif isinstance(target, build.StaticLibrary):
            conftype = 'StaticLibrary'
        elif isinstance(target, build.SharedLibrary):
            conftype = 'DynamicLibrary'
            entrypoint = '_DllMainCrtStartup'
        elif isinstance(target, build.CustomTarget):
            return self.gen_custom_target_vcxproj(target, ofname, guid)
        elif isinstance(target, build.RunTarget):
            return self.gen_run_target_vcxproj(target, ofname, guid)
        else:
            raise MesonException('Unknown target type for %s' % target.get_basename())
        down = self.target_to_build_root(target)
        proj_to_src_root = os.path.join(down, self.build_to_src)
        proj_to_src_dir = os.path.join(proj_to_src_root, target.subdir)
        (sources, headers, objects, languages) = self.split_sources(target.sources)
        buildtype = self.buildtype
        project_name = target.name
        target_name = target.name
        root = ET.Element('Project', {'DefaultTargets' : "Build",
                                      'ToolsVersion' : '4.0',
                                      'xmlns' : 'http://schemas.microsoft.com/developer/msbuild/2003'})
        confitems = ET.SubElement(root, 'ItemGroup', {'Label' : 'ProjectConfigurations'})
        prjconf = ET.SubElement(confitems, 'ProjectConfiguration',
                                {'Include' : self.buildtype + '|' + self.platform})
        p = ET.SubElement(prjconf, 'Configuration')
        p.text= buildtype
        pl = ET.SubElement(prjconf, 'Platform')
        pl.text = self.platform
        globalgroup = ET.SubElement(root, 'PropertyGroup', Label='Globals')
        guidelem = ET.SubElement(globalgroup, 'ProjectGuid')
        guidelem.text = guid
        kw = ET.SubElement(globalgroup, 'Keyword')
        kw.text = self.platform + 'Proj'
        ns = ET.SubElement(globalgroup, 'RootNamespace')
        ns.text = target_name
        p = ET.SubElement(globalgroup, 'Platform')
        p.text= self.platform
        pname= ET.SubElement(globalgroup, 'ProjectName')
        pname.text = project_name
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.Default.props')
        type_config = ET.SubElement(root, 'PropertyGroup', Label='Configuration')
        ET.SubElement(type_config, 'ConfigurationType').text = conftype
        ET.SubElement(type_config, 'CharacterSet').text = 'MultiByte'
        ET.SubElement(type_config, 'WholeProgramOptimization').text = 'false'
        ET.SubElement(type_config, 'UseDebugLibraries').text = 'true'
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.props')
        generated_files = self.generate_custom_generator_commands(target, root)
        (gen_src, gen_hdrs, gen_objs, gen_langs) = self.split_sources(generated_files)
        direlem = ET.SubElement(root, 'PropertyGroup')
        fver = ET.SubElement(direlem, '_ProjectFileVersion')
        fver.text = self.project_file_version
        outdir = ET.SubElement(direlem, 'OutDir')
        outdir.text = '.\\'
        intdir = ET.SubElement(direlem, 'IntDir')
        intdir.text = target.get_id() + '\\'
        tname = ET.SubElement(direlem, 'TargetName')
        tname.text = target_name
        inclinc = ET.SubElement(direlem, 'LinkIncremental')
        inclinc.text = 'true'

        compiles = ET.SubElement(root, 'ItemDefinitionGroup')
        clconf = ET.SubElement(compiles, 'ClCompile')
        opt = ET.SubElement(clconf, 'Optimization')
        opt.text = 'disabled'
        inc_dirs = [proj_to_src_dir, self.get_target_private_dir(target)]
        cur_dir = target.subdir
        if cur_dir == '':
            cur_dir= '.'
        inc_dirs.append(cur_dir)

        extra_args = {'c': [], 'cpp': []}
        for l, args in self.environment.coredata.external_args.items():
            if l in extra_args:
                extra_args[l] += args
        for l, args in self.build.global_args.items():
            if l in extra_args:
                extra_args[l] += args
        for l, args in target.extra_args.items():
            if l in extra_args:
                extra_args[l] += args
        general_args = compiler.get_buildtype_args(self.buildtype).copy()
        # FIXME all the internal flags of VS (optimization etc) are represented
        # by their own XML elements. In theory we should split all flags to those
        # that have an XML element and those that don't and serialise them
        # properly. This is a crapton of work for no real gain, so just dump them
        # here.
        general_args += compiler.get_option_compile_args(self.environment.coredata.compiler_options)
        for d in target.get_external_deps():
            try:
                general_args += d.compile_args
            except AttributeError:
                pass

        languages += gen_langs
        has_language_specific_args = any(l != extra_args['c'] for l in extra_args.values())
        additional_options_set = False
        if not has_language_specific_args or len(languages) == 1:
            if len(languages) == 0:
                extra_args = []
            else:
                extra_args = extra_args[languages[0]]
            extra_args = general_args + extra_args
            if len(extra_args) > 0:
                extra_args.append('%(AdditionalOptions)')
                ET.SubElement(clconf, "AdditionalOptions").text = ' '.join(extra_args)
            additional_options_set = True

        for d in target.include_dirs:
            for i in d.incdirs:
                curdir = os.path.join(d.curdir, i)
                inc_dirs.append(self.relpath(curdir, target.subdir)) # build dir
                inc_dirs.append(os.path.join(proj_to_src_root, curdir)) # src dir
        inc_dirs.append('%(AdditionalIncludeDirectories)')
        ET.SubElement(clconf, 'AdditionalIncludeDirectories').text = ';'.join(inc_dirs)
        preproc = ET.SubElement(clconf, 'PreprocessorDefinitions')
        rebuild = ET.SubElement(clconf, 'MinimalRebuild')
        rebuild.text = 'true'
        rtlib = ET.SubElement(clconf, 'RuntimeLibrary')
        rtlib.text = 'MultiThreadedDebugDLL'
        funclink = ET.SubElement(clconf, 'FunctionLevelLinking')
        funclink.text = 'true'
        pch_node = ET.SubElement(clconf, 'PrecompiledHeader')
        pch_sources = {}
        for lang in ['c', 'cpp']:
            pch = target.get_pch(lang)
            if len(pch) == 0:
                continue
            pch_node.text = 'Use'
            pch_sources[lang] = [pch[0], pch[1], lang]
        if len(pch_sources) == 1:
            # If there is only 1 language with precompiled headers, we can use it for the entire project, which
            # is cleaner than specifying it for each source file.
            pch_source = list(pch_sources.values())[0]
            header = os.path.join(proj_to_src_dir, pch_source[0])
            pch_file = ET.SubElement(clconf, 'PrecompiledHeaderFile')
            pch_file.text = header
            pch_include = ET.SubElement(clconf, 'ForcedIncludeFiles')
            pch_include.text = header + ';%(ForcedIncludeFiles)'
            pch_out = ET.SubElement(clconf, 'PrecompiledHeaderOutputFile')
            pch_out.text = '$(IntDir)$(TargetName)-%s.pch' % pch_source[2]

        warnings = ET.SubElement(clconf, 'WarningLevel')
        warnings.text = 'Level3'
        debinfo = ET.SubElement(clconf, 'DebugInformationFormat')
        debinfo.text = 'EditAndContinue'
        resourcecompile = ET.SubElement(compiles, 'ResourceCompile')
        ET.SubElement(resourcecompile, 'PreprocessorDefinitions')
        link = ET.SubElement(compiles, 'Link')
        # Put all language args here, too.
        extra_link_args = compiler.get_option_link_args(self.environment.coredata.compiler_options)
        extra_link_args += compiler.get_buildtype_linker_args(self.buildtype)
        for l in self.environment.coredata.external_link_args.values():
            for a in l:
                extra_link_args.append(a)
        for l in target.link_args:
            for a in l:
                extra_link_args.append(a)
        if len(extra_link_args) > 0:
            extra_link_args.append('%(AdditionalOptions)')
            ET.SubElement(link, "AdditionalOptions").text = ' '.join(extra_link_args)

        additional_links = []
        for t in target.link_targets:
            lobj = self.build.targets[t.get_id()]
            rel_path = self.relpath(lobj.subdir, target.subdir)
            linkname = os.path.join(rel_path, lobj.get_import_filename())
            additional_links.append(linkname)
        additional_objects = []
        for o in self.flatten_object_list(target, down, include_dir_names=False):
            assert(isinstance(o, str))
            additional_objects.append(o)
        if len(additional_links) > 0:
            additional_links.append('%(AdditionalDependencies)')
            ET.SubElement(link, 'AdditionalDependencies').text = ';'.join(additional_links)
        ofile = ET.SubElement(link, 'OutputFile')
        ofile.text = '$(OutDir)%s' % target.get_filename()
        addlibdir = ET.SubElement(link, 'AdditionalLibraryDirectories')
        addlibdir.text = '%(AdditionalLibraryDirectories)'
        subsys = ET.SubElement(link, 'SubSystem')
        subsys.text = subsystem
        gendeb = ET.SubElement(link, 'GenerateDebugInformation')
        gendeb.text = 'true'
        if isinstance(target, build.SharedLibrary):
            ET.SubElement(link, 'ImportLibrary').text = target.get_import_filename()
        pdb = ET.SubElement(link, 'ProgramDataBaseFileName')
        pdb.text = '$(OutDir}%s.pdb' % target_name
        if isinstance(target, build.Executable):
            ET.SubElement(link, 'EntryPointSymbol').text = entrypoint
        targetmachine = ET.SubElement(link, 'TargetMachine')
        targetmachine.text = 'MachineX86'

        if len(headers) + len(gen_hdrs) > 0:
            inc_hdrs = ET.SubElement(root, 'ItemGroup')
            for h in headers:
                relpath = h.rel_to_builddir(proj_to_src_root)
                ET.SubElement(inc_hdrs, 'CLInclude', Include=relpath)
            for h in gen_hdrs:
                if isinstance(h, str):
                    relpath = h
                else:
                    relpath = h.rel_to_builddir(proj_to_src_root)
                ET.SubElement(inc_hdrs, 'CLInclude', Include = relpath)
        if len(sources) + len(gen_src) + len(pch_sources) > 0:
            inc_src = ET.SubElement(root, 'ItemGroup')
            for s in sources:
                relpath = s.rel_to_builddir(proj_to_src_root)
                inc_cl = ET.SubElement(inc_src, 'CLCompile', Include=relpath)
                self.add_pch(inc_cl, proj_to_src_dir, pch_sources, s)
                self.add_additional_options(s, inc_cl, extra_args, additional_options_set)
            for s in gen_src:
                relpath =  self.relpath(s, target.subdir)
                inc_cl = ET.SubElement(inc_src, 'CLCompile', Include=relpath)
                self.add_pch(inc_cl, proj_to_src_dir, pch_sources, s)
                self.add_additional_options(s, inc_cl, extra_args, additional_options_set)
            for lang in pch_sources:
                header, impl, suffix = pch_sources[lang]
                relpath = os.path.join(proj_to_src_dir, impl)
                inc_cl = ET.SubElement(inc_src, 'CLCompile', Include=relpath)
                pch = ET.SubElement(inc_cl, 'PrecompiledHeader')
                pch.text = 'Create'
                pch_out = ET.SubElement(inc_cl, 'PrecompiledHeaderOutputFile')
                pch_out.text = '$(IntDir)$(TargetName)-%s.pch' % suffix
                pch_file = ET.SubElement(inc_cl, 'PrecompiledHeaderFile')
                # MSBuild searches for the header relative from the implementation, so we have to use
                # just the file name instead of the relative path to the file.
                pch_file.text = os.path.split(header)[1]
                self.add_additional_options(impl, inc_cl, extra_args, additional_options_set)

        if len(objects) + len(additional_objects) > 0:
            # Do not add gen_objs to project file. Those are automatically used by MSBuild, because they are part of
            # the CustomBuildStep Outputs.
            inc_objs = ET.SubElement(root, 'ItemGroup')
            for s in objects:
                relpath = s.rel_to_builddir(proj_to_src_root)
                ET.SubElement(inc_objs, 'Object', Include=relpath)
            for s in additional_objects:
                ET.SubElement(inc_objs, 'Object', Include=s)
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.targets')
        # Reference the regen target.
        ig = ET.SubElement(root, 'ItemGroup')
        pref = ET.SubElement(ig, 'ProjectReference', Include=os.path.join(self.environment.get_build_dir(), 'REGEN.vcxproj'))
        ET.SubElement(pref, 'Project').text = self.environment.coredata.regen_guid
        tree = ET.ElementTree(root)
        tree.write(ofname, encoding='utf-8', xml_declaration=True)
        # ElementTree can not do prettyprinting so do it manually
        doc = xml.dom.minidom.parse(ofname)
        open(ofname, 'w').write(doc.toprettyxml())
        # World of horror! Python insists on not quoting quotes and
        # fixing the escaped &quot; into &amp;quot; whereas MSVS
        # requires quoted but not fixed elements. Enter horrible hack.
        txt = open(ofname, 'r').read()
        open(ofname, 'w').write(txt.replace('&amp;quot;', '&quot;'))

    def gen_regenproj(self, project_name, ofname):
        root = ET.Element('Project', {'DefaultTargets': 'Build',
                                      'ToolsVersion' : '4.0',
                                      'xmlns' : 'http://schemas.microsoft.com/developer/msbuild/2003'})
        confitems = ET.SubElement(root, 'ItemGroup', {'Label' : 'ProjectConfigurations'})
        prjconf = ET.SubElement(confitems, 'ProjectConfiguration', 
                                {'Include' : self.buildtype + '|' + self.platform})
        p = ET.SubElement(prjconf, 'Configuration')
        p.text= self.buildtype
        pl = ET.SubElement(prjconf, 'Platform')
        pl.text = self.platform
        globalgroup = ET.SubElement(root, 'PropertyGroup', Label='Globals')
        guidelem = ET.SubElement(globalgroup, 'ProjectGuid')
        guidelem.text = self.environment.coredata.test_guid
        kw = ET.SubElement(globalgroup, 'Keyword')
        kw.text = self.platform + 'Proj'
        p = ET.SubElement(globalgroup, 'Platform')
        p.text = self.platform
        pname= ET.SubElement(globalgroup, 'ProjectName')
        pname.text = project_name
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.Default.props')
        type_config = ET.SubElement(root, 'PropertyGroup', Label='Configuration')
        ET.SubElement(type_config, 'ConfigurationType').text = "Utility"
        ET.SubElement(type_config, 'CharacterSet').text = 'MultiByte'
        ET.SubElement(type_config, 'UseOfMfc').text = 'false'
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.props')
        direlem = ET.SubElement(root, 'PropertyGroup')
        fver = ET.SubElement(direlem, '_ProjectFileVersion')
        fver.text = self.project_file_version
        outdir = ET.SubElement(direlem, 'OutDir')
        outdir.text = '.\\'
        intdir = ET.SubElement(direlem, 'IntDir')
        intdir.text = 'regen-temp\\'
        tname = ET.SubElement(direlem, 'TargetName')
        tname.text = project_name

        action = ET.SubElement(root, 'ItemDefinitionGroup')
        midl = ET.SubElement(action, 'Midl')
        ET.SubElement(midl, "AdditionalIncludeDirectories").text = '%(AdditionalIncludeDirectories)'
        ET.SubElement(midl, "OutputDirectory").text = '$(IntDir)'
        ET.SubElement(midl, 'HeaderFileName').text = '%(Filename).h'
        ET.SubElement(midl, 'TypeLibraryName').text = '%(Filename).tlb'
        ET.SubElement(midl, 'InterfaceIdentifierFilename').text = '%(Filename)_i.c'
        ET.SubElement(midl, 'ProxyFileName').text = '%(Filename)_p.c'
        regen_command = [sys.executable,
                         self.environment.get_build_command(),
                         '--internal',
                         'regencheck']
        private_dir = self.environment.get_scratch_dir()
        cmd_templ = '''setlocal
"%s" "%s"
if %%errorlevel%% neq 0 goto :cmEnd
:cmEnd
endlocal & call :cmErrorLevel %%errorlevel%% & goto :cmDone
:cmErrorLevel
exit /b %%1
:cmDone
if %%errorlevel%% neq 0 goto :VCEnd'''
        igroup = ET.SubElement(root, 'ItemGroup')
        rulefile = os.path.join(self.environment.get_scratch_dir(), 'regen.rule')
        if not os.path.exists(rulefile):
            with open(rulefile, 'w') as f:
                f.write("# Meson regen file.")
        custombuild = ET.SubElement(igroup, 'CustomBuild', Include=rulefile)
        message = ET.SubElement(custombuild, 'Message')
        message.text = 'Checking whether solution needs to be regenerated.'
        ET.SubElement(custombuild, 'Command').text = cmd_templ % \
            ('" "'.join(regen_command), private_dir)
        ET.SubElement(custombuild, 'Outputs').text = Vs2010Backend.get_regen_stampfile(self.environment.get_build_dir())
        deps = self.get_regen_filelist()
        ET.SubElement(custombuild, 'AdditionalInputs').text = ';'.join(deps)
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.targets')
        ET.SubElement(root, 'ImportGroup', Label='ExtensionTargets')
        tree = ET.ElementTree(root)
        tree.write(ofname, encoding='utf-8', xml_declaration=True)

    def gen_testproj(self, target_name, ofname):
        project_name = target_name
        root = ET.Element('Project', {'DefaultTargets' : "Build",
                                      'ToolsVersion' : '4.0',
                                      'xmlns' : 'http://schemas.microsoft.com/developer/msbuild/2003'})
        confitems = ET.SubElement(root, 'ItemGroup', {'Label' : 'ProjectConfigurations'})
        prjconf = ET.SubElement(confitems, 'ProjectConfiguration',
                                {'Include' : self.buildtype + '|' + self.platform})
        p = ET.SubElement(prjconf, 'Configuration')
        p.text= self.buildtype
        pl = ET.SubElement(prjconf, 'Platform')
        pl.text = self.platform
        globalgroup = ET.SubElement(root, 'PropertyGroup', Label='Globals')
        guidelem = ET.SubElement(globalgroup, 'ProjectGuid')
        guidelem.text = self.environment.coredata.test_guid
        kw = ET.SubElement(globalgroup, 'Keyword')
        kw.text = self.platform + 'Proj'
        p = ET.SubElement(globalgroup, 'Platform')
        p.text= self.platform
        pname= ET.SubElement(globalgroup, 'ProjectName')
        pname.text = project_name
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.Default.props')
        type_config = ET.SubElement(root, 'PropertyGroup', Label='Configuration')
        ET.SubElement(type_config, 'ConfigurationType')
        ET.SubElement(type_config, 'CharacterSet').text = 'MultiByte'
        ET.SubElement(type_config, 'UseOfMfc').text = 'false'
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.props')
        direlem = ET.SubElement(root, 'PropertyGroup')
        fver = ET.SubElement(direlem, '_ProjectFileVersion')
        fver.text = self.project_file_version
        outdir = ET.SubElement(direlem, 'OutDir')
        outdir.text = '.\\'
        intdir = ET.SubElement(direlem, 'IntDir')
        intdir.text = 'test-temp\\'
        tname = ET.SubElement(direlem, 'TargetName')
        tname.text = target_name

        action = ET.SubElement(root, 'ItemDefinitionGroup')
        midl = ET.SubElement(action, 'Midl')
        ET.SubElement(midl, "AdditionalIncludeDirectories").text = '%(AdditionalIncludeDirectories)'
        ET.SubElement(midl, "OutputDirectory").text = '$(IntDir)'
        ET.SubElement(midl, 'HeaderFileName').text = '%(Filename).h'
        ET.SubElement(midl, 'TypeLibraryName').text = '%(Filename).tlb'
        ET.SubElement(midl, 'InterfaceIdentifierFilename').text = '%(Filename)_i.c'
        ET.SubElement(midl, 'ProxyFileName').text = '%(Filename)_p.c'
        postbuild = ET.SubElement(action, 'PostBuildEvent')
        ET.SubElement(postbuild, 'Message')
        test_data = os.path.join(self.environment.get_scratch_dir(), 'meson_test_setup.dat')
        test_command = [sys.executable,
                        self.environment.get_build_command(),
                        '--internal',
                        'test']
        cmd_templ = '''setlocal
"%s" "%s"
if %%errorlevel%% neq 0 goto :cmEnd
:cmEnd
endlocal & call :cmErrorLevel %%errorlevel%% & goto :cmDone
:cmErrorLevel
exit /b %%1
:cmDone
if %%errorlevel%% neq 0 goto :VCEnd'''
        ET.SubElement(postbuild, 'Command').text =\
            cmd_templ % ('" "'.join(test_command), test_data)
        ET.SubElement(root, 'Import', Project='$(VCTargetsPath)\Microsoft.Cpp.targets')
        tree = ET.ElementTree(root)
        tree.write(ofname, encoding='utf-8', xml_declaration=True)
        datafile = open(test_data, 'wb')
        self.serialise_tests()
        datafile.close()
        # ElementTree can not do prettyprinting so do it manually
        #doc = xml.dom.minidom.parse(ofname)
        #open(ofname, 'w').write(doc.toprettyxml())
