# -*- coding: utf-8 -*-

__author__ = "Johannes Köster"

import re
import os
import sys
import signal
import json
from collections import OrderedDict
from itertools import filterfalse, chain
from functools import partial
from operator import attrgetter

from snakemake.logging import logger, format_resources, format_resource_names
from snakemake.rules import Rule, Ruleorder
from snakemake.exceptions import RuleException, CreateRuleException, \
    UnknownRuleException, NoRulesException, print_exception, WorkflowError
from snakemake.shell import shell
from snakemake.dag import DAG
from snakemake.scheduler import JobScheduler
from snakemake.parser import parse
import snakemake.io
from snakemake.io import protected, temp, temporary, expand, dynamic, glob_wildcards, flag, not_iterable, touch
from snakemake.persistence import Persistence


class Workflow:
    def __init__(
        self, snakefile=None, snakemakepath=None,
        jobscript=None, overwrite_shellcmd=None,
        overwrite_config=dict()):
        """
        Create the controller.
        """
        self._rules = OrderedDict()
        self.first_rule = None
        self._workdir = None
        self._ruleorder = Ruleorder()
        self._localrules = set()
        self.linemaps = dict()
        self.rule_count = 0
        self.basedir = os.path.dirname(snakefile)
        self.snakefile = os.path.abspath(snakefile)
        self.snakemakepath = snakemakepath
        self.included = []
        self.jobscript = jobscript
        self.persistence = None
        self.global_resources = None
        self.globals = globals()
        self._subworkflows = dict()
        self.overwrite_shellcmd = overwrite_shellcmd
        self.overwrite_config = overwrite_config

        global config
        config = dict()
        config.update(self.overwrite_config)

    @property
    def subworkflows(self):
        return self._subworkflows.values()

    @property
    def rules(self):
        return self._rules.values()

    @property
    def concrete_files(self):
        return (file for rule in self.rules for file in chain(rule.input, rule.output) if not callable(file) and not file.contains_wildcard())

    def check(self):
        for clause in self._ruleorder:
            for rulename in clause:
                if not self.is_rule(rulename):
                    raise UnknownRuleException(
                        rulename, prefix = "Error in ruleorder definition.")

    def add_rule(self, name=None, lineno=None, snakefile=None):
        """
        Add a rule.
        """
        if name is None:
            name = str(len(self._rules) + 1)
        if self.is_rule(name):
            raise CreateRuleException(
                "The name {} is already used by another rule".format(name))
        rule = Rule(name, self, lineno=lineno, snakefile=snakefile)
        self._rules[rule.name] = rule
        self.rule_count += 1
        if not self.first_rule:
            self.first_rule = rule.name
        return name

    def is_rule(self, name):
        """
        Return True if name is the name of a rule.

        Arguments
        name -- a name
        """
        return name in self._rules

    def get_rule(self, name):
        """
        Get rule by name.

        Arguments
        name -- the name of the rule
        """
        if not self._rules:
            raise NoRulesException()
        if not name in self._rules:
            raise UnknownRuleException(name)
        return self._rules[name]

    def list_rules(self, only_targets=False):
        rules = self.rules
        if only_targets:
            rules = filterfalse(Rule.has_wildcards, rules)
        for rule in rules:
            logger.rule_info(name=rule.name, docstring=rule.docstring)

    def list_resources(self):
        for resource in set(resource for rule in self.rules for resource in rule.resources):
            if resource not in "_cores _nodes".split():
                logger.info(resource)

    def is_local(self, rule):
        return rule.name in self._localrules

    def execute(
        self, targets=None, dryrun=False,  touch=False, cores=1, nodes=1,
        forcetargets=False, forceall=False, forcerun=None,
        prioritytargets=None, quiet=False, keepgoing=False,
        printshellcmds=False, printreason=False, printdag=False,
        cluster=None, jobname=None, immediate_submit=False, ignore_ambiguity=False,
        workdir=None, printrulegraph=False, printd3dag=False, drmaa=None,
        stats=None, force_incomplete=False, ignore_incomplete=False,
        list_version_changes=False, list_code_changes=False,
        list_input_changes=False, list_params_changes=False,
        summary=False, detailed_summary= False, latency_wait=3,
        benchmark_repeats=3,
        wait_for_files=None, nolock=False, unlock=False,
        resources=None, notemp=False, nodeps=False,
        cleanup_metadata=None, subsnakemake=None, updated_files=None,
        keep_target_files=False,
        allowed_rules=None, greedyness=1.0):

        self.global_resources = dict() if cluster or resources is None else resources
        self.global_resources["_cores"] = cores
        self.global_resources["_nodes"] = nodes

        def rules(items):
            return map(self._rules.__getitem__, filter(self.is_rule, items))

        if keep_target_files:
            def files(items):
                return filterfalse(self.is_rule, items)
        else:
            def files(items):
                return map(os.path.relpath, filterfalse(self.is_rule, items))

        if workdir is None:
            workdir = os.getcwd() if self._workdir is None else self._workdir
        os.chdir(workdir)

        if not targets:
            targets = [self.first_rule] if self.first_rule is not None else list()
        if prioritytargets is None:
            prioritytargets = list()
        if forcerun is None:
            forcerun = list()

        priorityrules = set(rules(prioritytargets))
        priorityfiles = set(files(prioritytargets))
        forcerules = set(rules(forcerun))
        forcefiles = set(files(forcerun))
        targetrules = set(chain(
            rules(targets), filterfalse(Rule.has_wildcards, priorityrules),
            filterfalse(Rule.has_wildcards, forcerules)))
        targetfiles = set(chain(files(targets), priorityfiles, forcefiles))
        if forcetargets:
            forcefiles.update(targetfiles)
            forcerules.update(targetrules)
        
        rules = self.rules
        if allowed_rules:
            rules = [rule for rule in rules if rule.name in set(allowed_rules)]
            
        if wait_for_files is not None:
            try:
                snakemake.io.wait_for_files(wait_for_files, latency_wait=latency_wait)
            except IOError as e:
                logger.error(str(e))
                return False

        dag = DAG(
            self, rules, dryrun=dryrun, targetfiles=targetfiles,
            targetrules=targetrules,
            forceall=forceall, forcefiles=forcefiles,
            forcerules=forcerules, priorityfiles=priorityfiles,
            priorityrules=priorityrules, ignore_ambiguity=ignore_ambiguity,
            force_incomplete=force_incomplete,
            ignore_incomplete=ignore_incomplete or printdag or printrulegraph, notemp=notemp)

        self.persistence = Persistence(nolock=nolock, dag=dag, warn_only=dryrun or printrulegraph or printdag or summary or list_version_changes or list_code_changes or list_input_changes or list_params_changes)

        if cleanup_metadata:
            for f in cleanup_metadata:
                self.persistence.cleanup_metadata(f)
            return True

        dag.init()
        dag.check_dynamic()

        if unlock:
            try:
                self.persistence.cleanup_locks()
                logger.info("Unlocking working directory.")
                return True
            except IOError:
                logger.error("Error: Unlocking the directory {} failed. Maybe "
                "you don't have the permissions?")
                return False
        try:
            self.persistence.lock()
        except IOError:
            logger.error("Error: Directory cannot be locked. Please make "
                "sure that no other Snakemake process is trying to create "
                "the same files in the following directory:\n{}\n"
                "If you are sure that no other "
                "instances of snakemake are running on this directory, "
                "the remaining lock was likely caused by a kill signal or "
                "a power loss. It can be removed with "
                "the --unlock argument.".format(os.getcwd()))
            return False

        if self.subworkflows and not printdag and not printrulegraph:
            # backup globals
            globals_backup = dict(self.globals)
            # execute subworkflows
            for subworkflow in self.subworkflows:
                subworkflow_targets = subworkflow.targets(dag)
                updated = list()
                if subworkflow_targets:
                    logger.info("Executing subworkflow {}.".format(subworkflow.name))
                    if not subsnakemake(subworkflow.snakefile, workdir=subworkflow.workdir, targets=subworkflow_targets, updated_files=updated):
                        return False
                    dag.updated_subworkflow_files.update(subworkflow.target(f) for f in updated)
                else:
                    logger.info("Subworkflow {}: Nothing to be done.".format(subworkflow.name))
            if self.subworkflows:
                logger.info("Executing main workflow.")
            # rescue globals
            self.globals.update(globals_backup)

        dag.check_incomplete()
        dag.postprocess()

        if nodeps:
            missing_input = [f for job in dag.targetjobs for f in job.input if dag.needrun(job) and not os.path.exists(f)]
            if missing_input:
                logger.error("Dependency resolution disabled (--nodeps) "
                    "but missing input " 
                    "files detected. If this happens on a cluster, please make sure "
                    "that you handle the dependencies yourself or turn of "
                    "--immediate-submit. Missing input files:\n{}".format(
                        "\n".join(missing_input)))
                return False

        updated_files.extend(f for job in dag.needrun_jobs for f in job.output)

        if printd3dag:
            dag.d3dag()
            return True
        elif printdag:
            print(dag)
            return True
        elif printrulegraph:
            print(dag.rule_dot())
            return True
        elif summary:
            print("\n".join(dag.summary(detailed=False)))
            return True
        elif detailed_summary:
            print("\n".join(dag.summary(detailed=True)))
            return True
        elif list_version_changes:
            items = list(chain(
                *map(self.persistence.version_changed, dag.jobs)))
            if items:
                print(*items, sep="\n")
            return True
        elif list_code_changes:
            items = list(chain(
                *map(self.persistence.code_changed, dag.jobs)))
            if items:
                print(*items, sep="\n")
            return True
        elif list_input_changes:
            items = list(chain(
                *map(self.persistence.input_changed, dag.jobs)))
            if items:
                print(*items, sep="\n")
            return True
        elif list_params_changes:
            items = list(chain(
                *map(self.persistence.params_changed, dag.jobs)))
            if items:
                print(*items, sep="\n")
            return True

        scheduler = JobScheduler(
            self, dag, cores, dryrun=dryrun, touch=touch, cluster=cluster,
            jobname=jobname, immediate_submit=immediate_submit,
            quiet=quiet, keepgoing=keepgoing, drmaa=drmaa,
            printreason=printreason, printshellcmds=printshellcmds,
            latency_wait=latency_wait, benchmark_repeats=benchmark_repeats,
            greedyness=greedyness
        )

        if not dryrun and not quiet:
            if len(dag):
                if cluster:
                    logger.resources_info("Provided cluster nodes: {}".format(nodes))
                else:
                    logger.resources_info("Provided cores: {}".format(cores))
                provided_resources = format_resources(resources)
                if provided_resources:
                    logger.resources_info("Provided resources: " + provided_resources)
                ignored_resources = format_resource_names(set(
                    resource
                    for job in dag.needrun_jobs
                    for resource in job.resources_dict
                    if resource not in resources))
                if ignored_resources:
                    logger.resources_info("Ignored resources: " + ignored_resources)
                logger.run_info("\n".join(dag.stats()))
            else:
                logger.info("Nothing to be done.")
        if dryrun and not len(dag):
            logger.info("Nothing to be done.")

        success = scheduler.schedule()

        if success:
            if dryrun:
                if not quiet and len(dag):
                    logger.run_info("\n".join(dag.stats()))
            elif stats:
                scheduler.stats.to_json(stats)
        else:
            return False
        return True

    def include(self, snakefile, workdir=None, overwrite_first_rule=False,
        print_compilation=False, overwrite_shellcmd=None):
        """
        Include a snakefile.
        """
        if snakefile in self.included:
            logger.warning("Multiple include of {} ignored".format(snakefile))
            return
        self.included.append(snakefile)

        global workflow
        global rules

        workflow = self
        rules = Rules()

        first_rule = self.first_rule
        if workdir:
            os.chdir(workdir)
        code, linemap = parse(snakefile, overwrite_shellcmd=self.overwrite_shellcmd)

        if print_compilation:
            print(code)

        # insert the current directory into sys.path
        # this allows to import modules from the workflow directory
        sys.path.insert(0, os.path.dirname(os.path.abspath(snakefile)))

        self.linemaps[snakefile] = linemap
        exec(compile(code, snakefile, "exec"), self.globals)
        if not overwrite_first_rule:
            self.first_rule = first_rule

    def workdir(self, workdir):
        if self._workdir is None:
            if not os.path.exists(workdir):
                os.makedirs(workdir)
            self._workdir = workdir

    def configfile(self, jsonpath):
        """ Update the global config with the given dictionary. """
        global config
        try:
            with open(jsonpath) as f:
                c = json.load(f)
        except FileNotFoundError:
            raise WorkflowError("Config file {} not found.".format(jsonpath))
        if not isinstance(c, dict):
            raise WorkflowError("Workflow config must be given as JSON with keys at top level.")
        for key, val in c.items():
            if key not in self.overwrite_config:
                config[key] = val

    def ruleorder(self, *rulenames):
        self._ruleorder.add(*rulenames)


    def subworkflow(self, name, snakefile=None, workdir=None):
        sw = Subworkflow(self, name, snakefile, workdir)
        self._subworkflows[name] = sw
        self.globals[name] = sw.target

    def localrules(self, *rulenames):
        self._localrules.update(rulenames)

    def rule(self, name=None, lineno=None, snakefile=None):
        name = self.add_rule(name, lineno, snakefile)
        rule = self.get_rule(name)

        def decorate(ruleinfo):
            if ruleinfo.input:
                rule.set_input(*ruleinfo.input[0], **ruleinfo.input[1])
            if ruleinfo.output:
                rule.set_output(*ruleinfo.output[0], **ruleinfo.output[1])
            if ruleinfo.params:
                rule.set_params(*ruleinfo.params[0], **ruleinfo.params[1])
            if ruleinfo.threads:
                if not isinstance(ruleinfo.threads, int):
                    raise RuleException("Threads value has to be an integer.",
                        rule=rule)
                rule.resources["_cores"] = ruleinfo.threads
            if ruleinfo.resources:
                args, resources = ruleinfo.resources
                if args:
                    raise RuleException("Resources have to be named.")
                if not all(map(lambda r: isinstance(r, int), resources.values())):
                    raise RuleException("Resources values have to be integers.", rule=rule)
                rule.resources.update(resources)
            if ruleinfo.priority:
                if (not isinstance(ruleinfo.priority, int)
                    and not isinstance(ruleinfo.priority, float)):
                    raise RuleException("Priority values have to be numeric.",
                        rule=rule)
                rule.priority = ruleinfo.priority
            if ruleinfo.version:
                rule.version = ruleinfo.version
            if ruleinfo.log:
                rule.log = ruleinfo.log
            if ruleinfo.message:
                rule.message = ruleinfo.message
            if ruleinfo.benchmark:
                rule.benchmark = ruleinfo.benchmark
            rule.norun = ruleinfo.norun
            rule.docstring = ruleinfo.docstring
            rule.run_func = ruleinfo.func
            rule.shellcmd = ruleinfo.shellcmd
            ruleinfo.func.__name__ = "__{}".format(name)
            self.globals[ruleinfo.func.__name__] = ruleinfo.func
            setattr(rules, name, rule)
            return ruleinfo.func
        return decorate

    def docstring(self, string):
        def decorate(ruleinfo):
            ruleinfo.docstring = string
            return ruleinfo
        return decorate

    def input(self, *paths, **kwpaths):
        def decorate(ruleinfo):
            ruleinfo.input = (paths, kwpaths)
            return ruleinfo
        return decorate

    def output(self, *paths, **kwpaths):
        def decorate(ruleinfo):
            ruleinfo.output = (paths, kwpaths)
            return ruleinfo
        return decorate

    def params(self, *params, **kwparams):
        def decorate(ruleinfo):
            ruleinfo.params = (params, kwparams)
            return ruleinfo
        return decorate

    def message(self, message):
        def decorate(ruleinfo):
            ruleinfo.message = message
            return ruleinfo
        return decorate

    def benchmark(self, benchmark):
        def decorate(ruleinfo):
            ruleinfo.benchmark = benchmark
            return ruleinfo
        return decorate

    def threads(self, threads):
        def decorate(ruleinfo):
            ruleinfo.threads = threads
            return ruleinfo
        return decorate

    def resources(self, *args, **resources):
        def decorate(ruleinfo):
            ruleinfo.resources = (args, resources)
            return ruleinfo
        return decorate

    def priority(self, priority):
        def decorate(ruleinfo):
            ruleinfo.priority = priority
            return ruleinfo
        return decorate

    def version(self, version):
        def decorate(ruleinfo):
            ruleinfo.version = version
            return ruleinfo
        return decorate

    def log(self, log):
        def decorate(ruleinfo):
            ruleinfo.log = log
            return ruleinfo
        return decorate

    def shellcmd(self, cmd):
        def decorate(ruleinfo):
            ruleinfo.shellcmd = cmd
            return ruleinfo
        return decorate

    def norun(self):
        def decorate(ruleinfo):
            ruleinfo.norun = True
            return ruleinfo
        return decorate

    def run(self, func):
        return RuleInfo(func)

    @staticmethod
    def _empty_decorator(f):
        return f


class RuleInfo:

    def __init__(self, func):
        self.func = func
        self.shellcmd = None
        self.norun = False
        self.input = None
        self.output = None
        self.params = None
        self.message = None
        self.benchmark = None
        self.threads = None
        self.resources = None
        self.priority = None
        self.version = None
        self.log = None
        self.docstring = None


class Subworkflow:

    def __init__(self, workflow, name, snakefile, workdir):
        self.workflow = workflow
        self.name = name
        self._snakefile = snakefile
        self._workdir = workdir

    @property
    def snakefile(self):
        if self._snakefile is None:
            return os.path.abspath(os.path.join(self.workdir, "Snakefile"))
        if not os.path.isabs(self._snakefile):
            return os.path.abspath(os.path.join(self.workflow.basedir, self._snakefile))
        return self._snakefile

    @property
    def workdir(self):
        workdir = "." if self._workdir is None else self._workdir
        if not os.path.isabs(workdir):
            return os.path.abspath(os.path.join(self.workflow.basedir, workdir))
        return workdir

    def target(self, paths):
        if not_iterable(paths):
            return flag(os.path.join(self.workdir, paths), "subworkflow", self)
        return [self.target(path) for path in paths]

    def targets(self, dag):
        return [f for job in dag.jobs for f in job.subworkflow_input if job.subworkflow_input[f] is self]


class Rules:
    """ A namespace for rules so that they can be accessed via dot notation. """
    pass
