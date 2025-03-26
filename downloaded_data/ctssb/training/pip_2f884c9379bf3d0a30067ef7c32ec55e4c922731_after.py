"""
Tests for the resolver
"""

import os
import re

import pytest
import yaml

from tests.lib import DATA_DIR, create_basic_wheel_for_package, path_to_url

_conflict_finder_pat = re.compile(
    # Conflicting Requirements: \
    # A 1.0.0 requires B == 2.0.0, C 1.0.0 requires B == 1.0.0.
    r"""
        (?P<package>[\w\-_]+?)
        [ ]
        (?P<version>\S+?)
        [ ]requires[ ]
        (?P<selector>.+?)
        (?=,|\.$)
    """,
    re.X
)


def generate_yaml_tests(directory):
    """
    Generate yaml test cases from the yaml files in the given directory
    """
    for yml_file in directory.glob("*.yml"):
        data = yaml.safe_load(yml_file.read_text())
        assert "cases" in data, "A fixture needs cases to be used in testing"

        # Strip the parts of the directory to only get a name without
        # extension and resolver directory
        base_name = str(yml_file)[len(str(directory)) + 1:-4]

        base = data.get("base", {})
        cases = data["cases"]

        for resolver in 'old', 'new':
            for i, case_template in enumerate(cases):
                case = base.copy()
                case.update(case_template)

                case[":name:"] = base_name
                if len(cases) > 1:
                    case[":name:"] += "-" + str(i)
                case[":name:"] += "*" + resolver
                case[":resolver:"] = resolver

                skip = case.pop("skip", False)
                assert skip in [False, True, 'old', 'new']
                if skip is True or skip == resolver:
                    case = pytest.param(case, marks=pytest.mark.xfail)

                yield case


def id_func(param):
    """
    Give a nice parameter name to the generated function parameters
    """
    if isinstance(param, dict) and ":name:" in param:
        return param[":name:"]

    retval = str(param)
    if len(retval) > 25:
        retval = retval[:20] + "..." + retval[-2:]
    return retval


def convert_to_dict(string):

    def stripping_split(my_str, splitwith, count=None):
        if count is None:
            return [x.strip() for x in my_str.strip().split(splitwith)]
        else:
            return [x.strip() for x in my_str.strip().split(splitwith, count)]

    parts = stripping_split(string, ";")

    retval = {}
    retval["depends"] = []
    retval["extras"] = {}

    retval["name"], retval["version"] = stripping_split(parts[0], " ")

    for part in parts[1:]:
        verb, args_str = stripping_split(part, " ", 1)
        assert verb in ["depends"], "Unknown verb {!r}".format(verb)

        retval[verb] = stripping_split(args_str, ",")

    return retval


def handle_request(script, action, requirement, options, new_resolver=False):
    if action == 'install':
        args = ['install']
        if new_resolver:
            args.append("--unstable-feature=resolver")
        args.extend(["--no-index", "--find-links",
                     path_to_url(script.scratch_path)])
    elif action == 'uninstall':
        args = ['uninstall', '--yes']
    else:
        raise "Did not excpet action: {!r}".format(action)

    if isinstance(requirement, str):
        args.append(requirement)
    elif isinstance(requirement, list):
        args.extend(requirement)
    else:
        raise "requirement neither str nor list {!r}".format(requirement)

    args.extend(options)
    args.append("--verbose")

    result = script.pip(*args,
                        allow_stderr_error=True,
                        allow_stderr_warning=True,
                        allow_error=True)

    # Check which packages got installed
    state = []
    for path in os.listdir(script.site_packages_path):
        if path.endswith(".dist-info"):
            name, version = (
                os.path.basename(path)[:-len(".dist-info")]
            ).rsplit("-", 1)
            # TODO: information about extras.
            state.append(" ".join((name, version)))

    return {"result": result, "state": sorted(state)}


@pytest.mark.yaml
@pytest.mark.parametrize(
    "case", generate_yaml_tests(DATA_DIR.parent / "yaml"), ids=id_func
)
def test_yaml_based(script, case):
    available = case.get("available", [])
    requests = case.get("request", [])
    responses = case.get("response", [])

    assert len(requests) == len(responses), (
        "Expected requests and responses counts to be same"
    )

    # Create a custom index of all the packages that are supposed to be
    # available
    # XXX: This doesn't work because this isn't making an index of files.
    for package in available:
        if isinstance(package, str):
            package = convert_to_dict(package)

        assert isinstance(package, dict), "Needs to be a dictionary"

        create_basic_wheel_for_package(script, **package)

    # use scratch path for index
    for request, response in zip(requests, responses):

        for action in 'install', 'uninstall':
            if action in request:
                break
        else:
            raise "Unsupported request {!r}".format(request)

        # Perform the requested action
        effect = handle_request(script, action,
                                request[action],
                                request.get('options', '').split(),
                                case[':resolver:'] == 'new')

        if 0:  # for analyzing output easier
            with open(DATA_DIR.parent / "yaml" /
                      case[':name:'].replace('*', '-'), 'w') as fo:
                result = effect['result']
                fo.write("=== RETURNCODE = %d\n" % result.returncode)
                fo.write("=== STDERR ===:\n%s\n" % result.stderr)

        if 'state' in response:
            assert effect['state'] == (response['state'] or []), \
                str(effect["result"])

        error = False
        if 'conflicting' in response:
            error = True

        if error:
            if case[":resolver:"] == 'old':
                assert effect["result"].returncode == 0, str(effect["result"])
            elif case[":resolver:"] == 'new':
                assert effect["result"].returncode == 1, str(effect["result"])
