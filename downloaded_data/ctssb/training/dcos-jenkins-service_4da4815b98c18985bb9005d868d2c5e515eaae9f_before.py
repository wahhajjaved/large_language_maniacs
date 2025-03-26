import logging
import os
import pytest
import sys
import distutils.util

log_level = os.getenv('TEST_LOG_LEVEL', 'INFO').upper()
log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'EXCEPTION')
assert log_level in log_levels, \
    '{} is not a valid log level. Use one of: {}'.format(log_level,
                                                         ', '.join(log_levels))
# write everything to stdout due to the following circumstances:
# - shakedown uses print() aka stdout
# - teamcity splits out stdout vs stderr into separate outputs, we'd want them combined
logging.basicConfig(
        format='[%(asctime)s|%(name)s|%(levelname)s]: %(message)s',
        level=log_level,
        stream=sys.stdout)


def pytest_addoption(parser):
    parser.addoption('--masters', action='store', default=1,
                     help='Number of Jenkins masters to launch.')
    parser.addoption('--jobs', action='store', default=1,
                     help='Number of test jobs to launch.')
    parser.addoption('--single-use', action='store', default=True,
                     help='Use Mesos Single-Use agents')
    parser.addoption('--run-delay', action='store', default=1,
                     help='Run job every X minutes.')
    parser.addoption('--cpu-quota', action='store', default=0.0,
                     help='CPU quota to set. 0.0 to set no quota.')
    parser.addoption('--work-duration', action='store', default=600,
                     help='Duration, in seconds, for the workload to '
                          'last (sleep).')
    parser.addoption('--mom', action='store', default='',
                     help='Marathon on Marathon instance name.')
    parser.addoption('--external-volume', action='store', default=False,
                     help='Use rexray external volumes.')
    parser.addoption('--scenario', action='store', default='sleep',
                     help='Test scenario to run (sleep, buildmarathon) '
                          '(default: sleep).')


@pytest.fixture
def master_count(request) -> int:
    return int(request.config.getoption('--masters'))


@pytest.fixture
def job_count(request) -> int:
    return int(request.config.getoption('--jobs'))


@pytest.fixture
def single_use(request) -> int:
    return request.config.getoption('--single-use')


@pytest.fixture
def run_delay(request) -> int:
    return int(request.config.getoption('--run-delay'))


@pytest.fixture
def cpu_quota(request) -> float:
    return float(request.config.getoption('--cpu-quota'))


@pytest.fixture
def work_duration(request) -> int:
    return int(request.config.getoption('--work-duration'))


@pytest.fixture
def mom(request) -> str:
    return request.config.getoption('--mom')


@pytest.fixture
def scenario(request) -> str:
    return request.config.getoption('--scenario')


@pytest.fixture
def external_volume(request) -> bool:
    v = request.config.getoption('--external-volume')
    if type(v) == bool:
        return v
    return bool(distutils.util.strtobool(v))
