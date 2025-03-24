from ..psmc_check import psmc_check, model_path
from acis_thermal_check.regression_testing import \
    load_test_template
import os

default_model_spec = os.path.join(model_path, "psmc_model_spec.json")

def test_psmc_may3016(answer_store):
    run_start = "2016:122:12:00:00.000"
    load_week = "MAY3016"
    load_test_template("1pdeaat", "psmc", answer_store, run_start,
                       load_week, default_model_spec, psmc_check)
