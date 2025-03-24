'''
This script contains classes/tasks for Luigi to execute.

These tasks use the `GASPredict` class in this submodule to determine what systems
to relax next, and then it performs the relaxation.
'''
__author__ = 'Kevin Tran'
__email__ = '<ktran@andrew.cmu.edu>'
# Since this is in a submodule, we add the parent folder to the python path
import pdb
import sys
sys.path.append("..")
from gas_predict import GASPredict
from gaspy_toolbox import UpdateAllDB
from gaspy_toolbox import FingerprintRelaxedAdslab
import luigi


# Location of the Local databases. Do not include the database names.
DB_LOC = '/global/cscratch1/sd/zulissi/GASpy_DB'    # Cori
#DB_LOC = '/Users/Ktran/Nerd/GASpy'                  # Local

# Exchange correlational
#XC = 'rpbe'
XC = 'beef-vdw'

# The adsorbate(s) we want to look at
ADS = ['CO']

# Maximum number of rows to dump from the Aux DB to the Local DBs. Set it to zero for no limit.
MAX_DUMP = 0

# Whether or not we want to dump the Aux DB to the Local energies DB
WRITE_DB = True

# The location of the pickled model we want to use for the feedback loop. Include the
# name of the file, as well.
MODEL_LOC = '/global/project/projectdirs/m2755/Kevin/GASpy/GASpy_regressions/pkls/CoordcounAds_Energy_GP.pkl'

# The maximum number of predictions that we want to send through the feedback loop. Note that
# the total number of submissions will be MAX_PRED*len(ADS)
MAX_PRED = 10


class CoordcountAdsToEnergy(luigi.WrapperTask):
    '''
    Before Luigi does anything, let's declare this task's arguments and establish defaults.
    These may be overridden on the command line when calling Luigi. If not, we pull them from
    above.

    Note that the pickled models should probably be updated as well. But instead of re-running
    the regression here, our current setup has use using Cron to periodically re-run the
    regression (and re-pickling the new model).
    '''
    xc = luigi.Parameter(XC)
    max_processes = luigi.IntParameter(MAX_DUMP)
    write_db = luigi.BoolParameter(WRITE_DB)
    model_location = luigi.Parameter(MODEL_LOC)
    max_pred = luigi.IntParameter(MAX_PRED)

    def requires(self):
        '''
        We need to update the Aux and Local databases before predicting the next set of
        systems to run.
        '''
        # This write_db thing here is here really only a placeholder for debugging.
        if self.write_db:
            return UpdateAllDB(writeDB=True, max_processes=self.max_processes)
        else:
            return UpdateAllDB(writeDB=False, max_processes=self.max_processes)


    def run(self):
        '''
        Here, we use the GASPredict class to identify the list of parameters that we can use
        to run the next set of relaxations.
        '''
        # We need to create a new instance of the gas_predictor for each adsorbate. Thus,
        # max_predictions is actually max_predictions_per_adsorbate
        for ads in ADS:
            gas_predict = GASPredict(adsorbate=ads,
                                     pkl=self.model_location,
                                     calc_setting=self.xc)
            parameters_list = gas_predict.energy_fr_coordcount_ads(max_predictions=self.max_pred)
            for parameters in parameters_list:
                yield FingerprintRelaxedAdslab(parameters=parameters)
