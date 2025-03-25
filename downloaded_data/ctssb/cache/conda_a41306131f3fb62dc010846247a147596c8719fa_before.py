import logging

from difflib import get_close_matches

from config import DEFAULT_NUMPY_SPEC, DEFAULT_PYTHON_SPEC
from constraints import AllOf, AnyOf, Channel, Requires, Satisfies
from package import channel_select, find_inconsistent_packages, newest_packages, sort_packages_by_name
from package_plan import PackagePlan
from package_spec import make_package_spec, find_inconsistent_specs

__all__ = [
    'create_create_plan',
    'create_deactivate_plan',
    'create_update_plan',
    'create_download_plan'
]

log = logging.getLogger(__name__)

def create_create_plan(prefix, conda, spec_strings):
    '''
    This functions creates a package plan for activating packages in a new
    Anaconda environment, including all of their required dependencies. The
    desired packages are specified as constraints.

    Parameters
    ----------
    prefix : str
        directory to create new Anaconda environment in
    conda : :py:class:`anaconda <conda.anaconda.anaconda>` object
    spec_strings : iterable of str
        package specification strings for packages to install in new Anaconda environment

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for creating new Anaconda environment

    Raises
    ------
    RuntimeError
        if the environment cannot be created

    '''
    plan = PackagePlan()

    idx = conda.index

    specs = set()

    py_spec = None
    np_spec = None

    for spec_string in spec_strings:

        spec = make_package_spec(spec_string)

        if spec.name == 'python':
            if spec.version: py_spec = spec
            continue

        if spec.name == 'numpy':
            if spec.version: np_spec = spec
            continue

        _check_unknown_spec(idx, spec)

        specs.add(spec)

    # this is handle the case where a user asks for just python and/or numpy and nothing else
    if len(specs) == 0:
        if py_spec: specs.add(py_spec)
        if np_spec: specs.add(np_spec)

    # abort if specifications are already incondsistent at this point
    inconsistent = find_inconsistent_specs(specs)
    if inconsistent:
        raise RuntimeError(
            'cannot create environment, the following requirements are inconsistent: %s' % str(inconsistent)
        )

    log.debug("initial package specifications: %s\n" % specs)

    # find packages compatible with the initial specifications
    pkgs = idx.find_compatible_packages(specs)
    log.debug("initial packages: %s\n" % pkgs)

    # find the associated dependencies
    deps = idx.get_deps(pkgs)
    log.debug("initial dependencies: %s\n" % deps)

    # add constraints for default python and numpy specifications if needed
    constraints = []

    dep_names = [dep.name for dep in deps]

    if py_spec:
        constraints.append(_default_constraint(py_spec))
    elif 'python' in dep_names:
        constraints.append(_default_constraint(make_package_spec(DEFAULT_PYTHON_SPEC)))

    if np_spec:
        constraints.append(_default_constraint(np_spec))
    elif 'numpy' in dep_names:
        constraints.append(_default_constraint(make_package_spec(DEFAULT_NUMPY_SPEC)))

    env_constraints = AllOf(*constraints)
    log.debug("computed environment constraints: %s\n" % env_constraints)

    # now we need to recompute the compatible packages using the computed environment constraints
    pkgs = idx.find_compatible_packages(specs)
    pkgs = idx.find_matches(env_constraints, pkgs)
    pkgs = channel_select(pkgs, conda.channel_urls)
    pkgs = newest_packages(pkgs)
    log.debug("updated packages: %s\n" % pkgs)

    # check to see if this is a meta-package situation (and handle it if so)
    all_pkgs = _handle_meta_create(conda, pkgs)

    if not all_pkgs:
        # find the associated dependencies
        deps = idx.get_deps(pkgs)
        deps = idx.find_matches(env_constraints, deps)
        deps = channel_select(deps, conda.channel_urls)
        deps = newest_packages(deps)
        log.debug("updated dependencies: %s\n" % deps)

        all_pkgs = newest_packages(pkgs | deps)
        log.debug("all packages: %s\n" % all_pkgs)

        # make sure all user supplied specs were satisfied
        for spec in specs:
            if not idx.find_matches(Satisfies(spec), all_pkgs):
                raise RuntimeError("could not find package for package specification '%s' compatible with other requirements" % spec)

    # don't install conda into non-default environments
    all_pkgs = [pkg for pkg in all_pkgs if pkg.name != 'conda']

    track_features = set()
    for pkg in all_pkgs:
        track_features |= pkg.track_features
    log.debug("track_features: %s\n" % track_features)

    features = {}
    for pkg in all_pkgs:
        for feature in track_features:
            if feature not in features:
                features[feature] = set()
            features[feature].add(pkg)
    log.debug("features: %s\n" % features)

    all_pkgs = _replace_with_features(conda, all_pkgs, features, env_constraints)

    # download any packages that are not available
    for pkg in all_pkgs:
        if pkg not in conda.available_packages:
            plan.downloads.add(pkg)

    plan.activations = all_pkgs

    return plan


def create_install_plan(env, spec_strings):
    '''
    This functions creates a package plan for activating packages in an
    existing Anaconda environment, including removing existing versions and
    also activating all required dependencies. The desired packages are
    specified as package names, package filenames, or make_package_spec strings.

    Parameters
    ----------
    env : :py:class:`Environment <conda.environment.Environment>` object
        Anaconda environment to install packages into
    spec_strings : iterable of str
        string package specifications of packages to install in Anaconda environment

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for installing packages in an existing Anaconda environment

    Raises
    ------
    RuntimeError
        if the install cannot be performed

    '''
    plan = PackagePlan()

    idx = env.conda.index

    specs = set()

    py_spec = None
    np_spec = None

    for spec_string in spec_strings:

        spec = make_package_spec(spec_string)

        active = env.find_linked_package(spec.name)

        if spec.name == 'python':
            if active:
                raise RuntimeError('changing python versions in an existing Anaconda environment is not supported (create a new environment)')
            if spec.version: py_spec = spec
            continue
        if spec.name == 'numpy':
            if active:
                raise RuntimeError('changing numpy versions in an existing Anaconda environment is not supported (create a new environment)')
            if spec.version: np_spec = spec
            continue

        if not spec.version and active:
            raise RuntimeError("package '%s' version %s is already installed. Supply a new version to install (e.g., '%s=x.y.z'), or see 'conda update -h' for help on updating" % (spec.name, str(active.version), spec.name))

        _check_unknown_spec(idx, spec)

        specs.add(spec)

    # abort if specifications are already inconsistent at this point
    inconsistent = find_inconsistent_specs(specs)
    if inconsistent:
        raise RuntimeError(
            'cannot create environment, the following requirements are inconsistent: %s' % str(inconsistent)
        )

    log.debug("initial package specifications: %s\n" % specs)

    # find packages compatible with the initial specifications
    pkgs = idx.find_compatible_packages(specs)
    pkgs = idx.find_matches(env.requirements, pkgs)
    pkgs = newest_packages(pkgs)
    log.debug("initial packages: %s\n" % pkgs)

    features = env.features
    for pkg in pkgs:
        for feature in pkg.track_features:
            if feature not in features:
                features[feature] = set()
            features[feature].add(pkg)
    log.debug("features: %s\n" % features)

    # check to see if this is a meta-package situation (and handle it if so)
    all_pkgs = _handle_meta_install(env.conda, pkgs)

    if not all_pkgs:
        # find the associated dependencies
        deps = idx.get_deps(pkgs)
        deps = idx.find_matches(env.requirements, deps)
        log.debug("initial dependencies: %s\n" % deps)

        # add default python and numpy requirements if needed
        constraints = [env.requirements]
        dep_names = [dep.name for dep in deps]

        if py_spec:
            constraints.append(_default_constraint(py_spec))
        elif 'python' in dep_names and not env.find_linked_package('python'):
            constraints.append(_default_constraint(make_package_spec(DEFAULT_PYTHON_SPEC)))

        if np_spec:
            constraints.append(_default_constraint(np_spec))
        elif 'numpy' in dep_names and not env.find_linked_package('numpy'):
            constraints.append(_default_constraint(make_package_spec(DEFAULT_NUMPY_SPEC)))

        env_constraints = AllOf(*constraints)
        log.debug("computed environment constraints: %s\n" % env_constraints)

        # now we need to recompute the compatible packages using the updated package specifications
        pkgs = idx.find_compatible_packages(specs)
        pkgs = idx.find_matches(env_constraints, pkgs)
        pkgs = channel_select(pkgs, env.conda.channel_urls)
        pkgs = newest_packages(pkgs)
        log.debug("updated packages: %s\n" % pkgs)

        # find the associated dependencies
        deps = idx.get_deps(pkgs)
        deps = idx.find_matches(env_constraints, deps)
        deps = channel_select(deps, env.conda.channel_urls)
        deps = newest_packages(deps)
        log.debug("updated dependencies: %s\n" % deps)

        all_pkgs = pkgs | deps
        all_pkgs = channel_select(all_pkgs, env.conda.channel_urls)
        all_pkgs = newest_packages(all_pkgs)
        log.debug("all packages: %s\n" % all_pkgs)

        # make sure all user supplied specs were satisfied
        for spec in specs:
            if not idx.find_matches(Satisfies(spec), all_pkgs):
                if idx.find_matches(Satisfies(spec)):
                    raise RuntimeError("could not find package for package specification '%s' compatible with other requirements" % spec)
                else:
                    raise RuntimeError("could not find package for package specification '%s'" % spec)

    all_pkgs = _replace_with_features(env.conda, all_pkgs, features, env_constraints)

    # download any packages that are not available
    for pkg in all_pkgs:

        # don't install conda into non-default environments
        if pkg.name == 'conda' and env != env.conda.root_environment:
            continue

        # download any currently unavailable packages
        if pkg not in env.conda.available_packages:
            plan.downloads.add(pkg)

        # see if the package is already active
        active = env.find_linked_package(pkg.name)
        # need to compare canonical names since ce/pro packages might compare equal
        if active and pkg.canonical_name != active.canonical_name:
            plan.deactivations.add(active)

        if pkg not in env.linked:
            plan.activations.add(pkg)

    return plan


def create_remove_plan(env, pkg_names, follow_deps=True):
    '''
    This function creates a package plan for removing the specified packages
    in the given Anaconda environment prefix.

    Parameters
    ----------
    env : :py:class:`Environment <conda.environment.Environment>` object
        Anaconda environment to remove packages from
    pkg_names : iterable of str
        package names of packages to remove

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for removing packages in an existing Anaconda environment

    Raises
    ------
    RuntimeError
        if the removals cannot be performed

    '''
    plan = PackagePlan()

    idx = env.conda.index

    for pkg_name in pkg_names:

        spec = make_package_spec(pkg_name)
        if spec.version or spec.build:
            raise RuntimeError("'%s' looks like a package specification, 'remove' only accepts package names" % pkg_name)

        if pkg_name.endswith('.tar.bz2'):
            raise RuntimeError("'%s' looks like a package filename, 'remove' only accepts package names" % pkg_name)

        pkg = env.find_linked_package(pkg_name)
        if not pkg: continue

        for basereq in ['python', 'pyyaml', 'yaml', 'conda']:
            if pkg.name == basereq and env == env.conda.root_environment:
                raise RuntimeError("Base package '%s' may not be removed from the root environment: %s" % (basereq, env.conda.root_environment.prefix))

        plan.deactivations.add(pkg)

    # find a requirement for this package that we can use to lookup reverse deps
    reqs = idx.find_compatible_requirements(plan.deactivations)

    # add or warn about broken reverse dependencies
    rdeps = idx.get_reverse_deps(reqs) & env.linked
    if follow_deps:
        plan.deactivations |= rdeps
    else:
        plan.broken = rdeps

    track_features = env.features
    for pkg in plan.deactivations:
        if pkg.track_features:
            for feature in pkg.track_features:
                if feature in track_features:
                    track_features[feature] -= set([pkg])
    for feature, pkgs in dict(track_features).items():
        if len(pkgs) == 0:
            del track_features[feature]

    to_add, to_remove = _replace_without_features(env, plan.deactivations, track_features, AllOf(env.requirements))

    print to_add
    print to_remove

    plan.deactivations |= to_remove

     # download any packages that are not available
    for pkg in to_add:

        # download any currently unavailable packages
        if pkg not in env.conda.available_packages:
            plan.downloads.add(pkg)

        plan.activations.add(pkg)

    return plan


def create_update_plan(env, pkg_names):
    '''
    This function creates a package plan for updating specified packages to
    the latest version in the given Anaconda environment prefix. Only versions
    compatible with the existing environment are considered.

    Parameters
    ----------
    env : :py:class:`Environment <conda.environment.Environment>` object
        Anaconda environment to update packages in
    pkg_names : iterable of str
        package names of packages to update

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for updating packages in an existing Anaconda environment

    Raises
    ------
    RuntimeError
        if the update cannot be performed

    '''

    plan = PackagePlan()

    idx = env.conda.index

    pkgs = set()
    for pkg_name in pkg_names:
        pkg = env.find_linked_package(pkg_name)
        if not pkg:
            if pkg_name in env.conda.index.package_names:
                raise RuntimeError("package '%s' is not installed, cannot update (see conda install -h)" % pkg_name)
            else:
                raise RuntimeError("unknown package '%s', cannot update" % pkg_name)
        pkgs.add(pkg)

    # find any initial packages that have newer versions
    updates = set()
    skipped = set()
    for pkg in sort_packages_by_name(pkgs):
        initial_candidates = idx.lookup_from_name(pkg.name)
        for channel in env.conda.channel_urls:
            candidates = idx.find_matches(Channel(channel), initial_candidates)
            if not candidates: continue
            candidates = idx.find_matches(env.requirements, candidates)
            if not candidates: continue
            initial_newest = max(candidates)
            candidates = set([initial_newest])
            if not pkg.is_meta:
                rdeps = idx.get_reverse_deps(set([pkg])) & env.linked
                if rdeps:
                    candidates &= idx.get_deps(rdeps)
            if not candidates:
                skipped.add((pkg, initial_newest, tuple(rdeps)))
                break
            newest = max(candidates)
            log.debug("%s > %s == %s" % (newest.canonical_name, pkg.canonical_name, newest>pkg))
            if newest > pkg:
                updates.add(newest)
            break

    log.debug('initial updates: %s' %  updates)

    if len(skipped) > 0:
        for skip in skipped:
            if len(skip[2]) == 1:
                rdeps = "%s depends on" % skip[2]
            else:
                rdeps = "{" + ", ".join(str(p) for p in skip[2]) + "} depend on"
            print "skipped:", skip[1], "is available, but", rdeps, skip[0]

    if len(updates) == 0: return plan  # nothing to do

    all_pkgs = _handle_meta_update(env.conda, updates)

    if not all_pkgs:
        # get all the dependencies of the updates
        all_deps = idx.get_deps(updates)
        log.debug('update dependencies: %s' %  all_deps)

        # find newest packages compatible with these requirements
        all_pkgs = all_deps | updates
        all_pkgs = idx.find_matches(env.requirements, all_pkgs)
        all_pkgs = channel_select(all_pkgs, env.conda.channel_urls)
        all_pkgs = newest_packages(all_pkgs)

    all_pkgs = _replace_with_features(env.conda, all_pkgs, env.features, env.requirements)

    # check for any inconsistent requirements the set of packages
    inconsistent = find_inconsistent_packages(all_pkgs)
    if inconsistent:
        raise RuntimeError('cannot update, the following packages are inconsistent: %s'
            % ', '.join('%s-%s' % (pkg.name, pkg.version.vstring) for pkg in inconsistent)
        )

    # download any activations that are not already available
    for pkg in all_pkgs:

        # don't install conda into non-default environments
        if pkg.name == 'conda' and env != env.conda.root_environment:
            continue

        active = env.find_linked_package(pkg.name)
        if not active:
            if pkg not in env.conda.available_packages:
                plan.downloads.add(pkg)
            plan.activations.add(pkg)
        elif pkg > active:
            if pkg not in env.conda.available_packages:
                plan.downloads.add(pkg)
            plan.activations.add(pkg)
            plan.deactivations.add(active)

    return plan


def create_activate_plan(env, canonical_names):
    '''
    This function creates a package plan for activating the specified packages
    in the given Anaconda environment prefix.

    Parameters
    ----------
    env : :py:class:`Environment <conda.environment.Environment>` object
        Anaconda environment to activate packages in
    canonical_names : iterable of str
        canonical names of packages to activate

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for activating packages in an existing Anaconda environment

    Raises
    ------
    RuntimeError
        if the activations cannot be performed

    '''
    plan = PackagePlan()

    idx = env.conda.index

    for canonical_name in canonical_names:

        try:
            pkg = idx.lookup_from_canonical_name(canonical_name)
        except:
            spec = make_package_spec(canonical_name)
            if idx.lookup_from_name(spec.name):
                if spec.build:
                    raise RuntimeError("cannot activate unknown build '%s' of package '%s'" % (canonical_name, spec.name))
                if spec.version:
                    raise RuntimeError("'%s' looks like a package specification, --activate requires full canonical names" % canonical_name)
                else:
                    raise RuntimeError("'%s' looks like a package name, --activate requires full canonical names" % canonical_name)
            else:
                raise RuntimeError("cannot activate unknown package '%s'" % canonical_name)

        if pkg in env.linked:
            raise RuntimeError("package '%s' is already activated in environment: %s" % (canonical_name, env.prefix))

        if pkg.name == 'conda' and env != env.conda.root_environment:
            raise RuntimeError("'conda' package may only be activated in the root environament: %s" % env.conda.root_environment.prefix)

        plan.activations.add(pkg)

        # add or warn about missing dependencies
        deps = idx.find_compatible_packages(idx.get_deps(plan.activations))
        deps = idx.find_matches(env.requirements, deps)
        for dep in deps:
            if dep not in env.linked:
                plan.missing.add(dep)

    return plan


def create_deactivate_plan(env, canonical_names):
    '''
    This function creates a package plan for deactivating the specified packages
    in the given Anaconda environment prefix.

    Parameters
    ----------
    env : :py:class:`Environment <conda.environment.Environment>` object
        Anaconda environment to deactivate packages in
    canonical_names : iterable of str
        canonical names of packages to deactivate

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for deactivating packages in an existing Anaconda environment

    Raises
    ------
    RuntimeError
        if the deactivations cannot be performed

    '''
    plan = PackagePlan()

    idx = env.conda.index

    for canonical_name in canonical_names:

        try:
            pkg = idx.lookup_from_canonical_name(canonical_name)
        except:
            spec = make_package_spec(canonical_name)
            if idx.lookup_from_name(spec.name):
                if spec.build:
                    raise RuntimeError("cannot deactivate unknown build '%s' of package '%s'" % (canonical_name, spec.name))
                if spec.version:
                    raise RuntimeError("'%s' looks like a package specification, --deactivate requires full canonical names" % canonical_name)
                else:
                    raise RuntimeError("'%s' looks like a package name, --dactivate requires full canonical names" % canonical_name)
            else:
                raise RuntimeError("cannot deactivate unknown package '%s'" % canonical_name)

        # if package is not already activated, there is nothing to do
        if pkg not in env.linked:
            raise RuntimeError("package '%s' is not activated in environment: %s" % (canonical_name, env.prefix))

        if pkg.name == 'conda' and env == env.conda.root_environment:
            raise RuntimeError("'conda' package may not be deactivated from the root environment: %s" % env.conda.root_environment.prefix)

        plan.deactivations.add(pkg)

    # find a requirement for this package that we can use to lookup reverse deps
    reqs = idx.find_compatible_requirements(plan.deactivations)

    # warn about broken reverse dependencies
    for rdep in idx.get_reverse_deps(reqs):
        if rdep in env.linked:
           plan.broken.add(rdep)

    return plan


def create_download_plan(conda, canonical_names, force):
    '''
    This function creates a package plan for downloading the specified
    packages from remote Anaconda package channels. By default,
    packages already available are ignored, but this can be overridden
    with the force argument.

    Parameters
    ----------
    conda : :py:class:`anaconda <conda.anaconda.anaconda>` object
        Anaconda installation to download packages into
    canonical_names : iterable of str
        canonical names of packages to download
    force : bool
        whether to force download even if package is already locally available

    Returns
    -------
    plan: :py:class:`PackagePlan <conda.package_plan.PackagePlan>`
        package plan for downloading packages into :ref:`local availability <locally_available>`.

    Raises
    ------
    RuntimeError
        if the downloads cannot be performed

    '''
    plan = PackagePlan()

    idx = conda.index

    for canonical_name in canonical_names:

        try:
            pkg = idx.lookup_from_canonical_name(canonical_name)
        except:
            raise RuntimeError("cannot download unknown package '%s'" % canonical_name)

        if force or pkg not in conda.available_packages:
            plan.downloads.add(pkg)

    return plan


def _replace_with_features(conda, all_pkgs, track_features, env_constraints):
    idx = conda.index

    results = all_pkgs

    all_pkgs_dict = {}
    for pkg in all_pkgs:
        all_pkgs_dict[pkg.name] = [pkg]

    for pkg in all_pkgs:
        for feature in pkg.features:
            if feature not in track_features:
                results.remove(pkg)
                spec = make_package_spec("%s %s" % (pkg.name, pkg.version.vstring))
                rpkgs = idx.find_compatible_packages(set([spec]))
                rpkgs = [pkg for pkg in rpkgs if feature not in pkg.features]
                rpkgs = idx.find_matches(env_constraints, rpkgs)
                rpkgs = channel_select(rpkgs, conda.channel_urls)
                rpkg = newest_packages(rpkgs)
                results.add(rpkg.pop())

    for feature, fpkgs in track_features.items():
        for name in fpkgs:
            if name in all_pkgs_dict:
                pkg = all_pkgs_dict[name]
                if feature in pkg.features: continue
                results.remove(pkg)
                spec = make_package_spec("%s %s" % (pkg.name, pkg.version.vstring))
                rpkgs = idx.find_compatible_packages(set([specs]))
                rpkgs = [pkg for pkg in rpkgs if feature in pkg.features]
                rpkgs = idx.find_matches(env_constraints, rpkgs)
                rpkgs = channel_select(rpkgs, conda.channel_urls)
                rpkg = newest_packages(rpkgs)
                results.add(rpkg.pop())

    return results

def _replace_without_features(env, removals, track_features, env_constraints):
    idx = env.conda.index

    to_add = set()
    to_remove = set()

    for pkg in removals:

        deps = idx.get_deps([pkg]) & env.linked
        for dep in deps:
            for feature in dep.features:

                if feature not in track_features:
                    to_remove.add(dep)
                    rdeps = idx.get_reverse_deps([dep]) & env.linked
                    if not rdeps:
                        to_remove.add(dep)
                        continue
                    spec = make_package_spec("%s %s" % (dep.name, dep.version.vstring))
                    rpkgs = idx.find_compatible_packages(set([spec]))
                    rpkgs = [pkg for pkg in rpkgs if feature not in pkg.features]
                    rpkgs = idx.find_matches(env_constraints, rpkgs)
                    rpkgs = channel_select(rpkgs, env.conda.channel_urls)
                    rpkg = newest_packages(rpkgs)
                    to_add.add(rpkg.pop())

    return to_add, to_remove


def _check_unknown_spec(idx, spec):

    if spec.name not in idx.package_names:
        message = "unknown package name '%s'" % spec.name
        close = get_close_matches(spec.name, idx.package_names)
        if close:
            message += '\n\nDid you mean one of these?\n'
            for s in close:
                message += '    %s' % s
            message += "\n"
        raise RuntimeError(message)





def _handle_meta_create(conda, pkgs):
    metas = set([pkg for pkg in pkgs if pkg.is_meta])

    if len(metas) == 0:
        return set()

    if len(metas) == 1 and len(pkgs) > 1:
        raise RuntimeError("create operation does not support mixing meta-packages and standard packages")

    if len(metas) > 1:
        raise RuntimeError("create operation only supports one meta-package at a time, was given: %s" % metas)

    pkg = pkgs.pop()
    pkgs.add(pkg)

    for spec in pkg.requires:
        canonical_name = "%s-%s-%s" % (spec.name, spec.version.vstring, spec.build)
        pkgs.add(conda.index.lookup_from_canonical_name(canonical_name))

    return pkgs


def _handle_meta_install(conda, pkgs):
    metas = set([pkg for pkg in pkgs if pkg.is_meta])

    if len(metas) == 0:
        return set()

    if len(metas) == 1 and len(pkgs) > 1:
        raise RuntimeError("install operation does not support mixing meta-packages and standard packages")

    if len(metas) > 1:
        raise RuntimeError("install operation only supports one meta-package at a time, was given: %s" % metas)

    pkg = pkgs.pop()
    pkgs.add(pkg)

    for spec in pkg.requires:
        canonical_name = "%s-%s-%s" % (spec.name, spec.version.vstring, spec.build)
        pkgs.add(conda.index.lookup_from_canonical_name(canonical_name))

    return pkgs


def _handle_meta_update(conda, pkgs):
    metas = set([pkg for pkg in pkgs if pkg.is_meta])

    if len(metas) == 0:
        return set()

    if len(metas) == 1 and len(pkgs) > 1:
        raise RuntimeError("update operation does not support mixing meta-packages and standard packages")

    if len(metas) > 1:
        raise RuntimeError("update operation only supports one meta-package at a time, was given: %s" % metas)

    pkg = pkgs.pop()
    pkgs.add(pkg)

    for spec in pkg.requires:
        canonical_name = "%s-%s-%s" % (spec.name, spec.version.vstring, spec.build)
        pkgs.add(conda.index.lookup_from_canonical_name(canonical_name))

    return pkgs


def _default_constraint(spec):
    if len(spec.name,spec.version.version) == 1:
        req = make_package_spec('%s %s' % spec.name,spec.version.version[0])
    else:
        req = make_package_spec('%s %s.%s' % (spec.name,spec.version.version[0], spec.version.version[1]))
    sat = make_package_spec('%s %s %s' % (spec.name, spec.version.vstring, spec.build))
    return AnyOf(Requires(req), Satisfies(sat))
