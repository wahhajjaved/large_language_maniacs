# coding=utf-8
from walter import project
import pandas,os
from walter.data_access import get_data_dir
from pathlib2 import Path
import numpy.testing as np
import re

_atol_PAR = 200 # windows and linux version of walter lead up to 200 PAR output difference


def test_same_result():
    #assert : verify if the same wheat field have the same results for the same chosen parameters.

    p = project.Project(name='same') # Create the simulation directory
    directory = project.walter_data()
    params = p.csv_parameters(str(directory/'sim_scheme_ref.csv'))[0] # recovery of parameters
    p.run(**params)
    result_directory = str(p.output_path()) + '/'
    reference_directory = get_data_dir() + "/ref_output/" # Reference folder
    list_of_file_ref = os.listdir(reference_directory) # Listing of the different reference files
    list_of_result = os.listdir(result_directory)
    np.assert_array_equal(list_of_file_ref, list_of_result)  # Check that the 2 lists are equal

    for i in list_of_file_ref:
        element = reference_directory + i # Recover the absolut path
        reference = pandas.read_csv(element, sep='\t') # Recover file and content
        my_file = Path(result_directory + i)
        if my_file.is_file():
            dfout = pandas.read_csv(my_file, sep='\t')
            print(' \n The tested file is : '+ i + '\n')
            for column in reference.columns:
                if re.match('.*PAR.*', column):
                    if column == 'Sum_PAR':
                        np.assert_allclose(dfout[column], reference[column], atol=11 * _atol_PAR)
                    else:
                        np.assert_allclose(dfout[column], reference[column], atol=_atol_PAR)
                else:
                    np.assert_array_equal(dfout[column], reference[column])
        else:
            print(' \n The ' + my_file + ' file is non-existent ')


    p.remove(force=True)

