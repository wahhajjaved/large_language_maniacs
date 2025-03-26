#
# driver.py
#
"""Solve the equilibrium ode"""

# These modules are used to parse arguments
import sys
import os
import logging

# These are the programs modules
# from . import input_output
from . import plotter, fileIO, experiment_class
from . import handy_functions as HANDY
import numpy as np

# Initialize logger:
# tell the program to send messages on its own behalf.
logger = logging.getLogger(__name__)

temp_diag = True
diag = os.path.join("Diagnose" + os.sep)
graph = os.path.join("Graphs" + os.sep)

# for now we use 'rxn_mechanism' since puzzle and solution can both be used here
# input_model is an instance of class experiment
# this function executes the necessary mathematical operations to find the Keq array - i.e. equilibrates the reaction


def equilibrate(input_model, progress_tick, in_conc=None, diag=False):
        # the meat and potatoes
    input_model.find_rate_constant()
    input_model.find_reaction_rate_function()
    input_model.find_reaction_profile(diagnostic_output=diag)
    input_model.find_experimental_Keq_array()
    input_model.remove_flat_region()
    return True


def run_true_experiment(puzzle, condition, condition_path, progress_tick, stream=sys.stdout):
    def show_all_concentrations():
        logger.info(
            "                    Update the concentration record of the whole lab:")
        buff = '                        '
        for i in condition.molecule_concentrations.keys():
            buff += i + '\t'
        buff = '                        '
        for i in condition.molecule_concentrations.values():
            buff += str(i)[:4] + "\t"
        logger.info(buff)

    #sys.stdout = open(diag + "diagnostic_stdout_" + str(condition.reaction_temperature) + "_.dat", "w") if (temp_diag == True) else system_output
    logger.info("            First, pre-equilibrate every reagent:")
    # zero out all the condition objects molecule concentrations as a saftey measure
    # this should probably be made a funciton in the condition class at some later point
    for reagent_name, reagent_obj in puzzle.reagent_dict.items():
        logger.info("                Pre-equilibrate " + reagent_name + ":")
        for name, index in reagent_obj.coefficient_dict.items():
            condition.molecule_concentrations[name] = 0

        # make the array that will hold the concentration values for each REAGENT, the "beakers" that the user can change the conc of
        reagent_conc_array = np.zeros((1, reagent_obj.number_of_species))
        # we start with the concentrations defined by the user in the condition object they passed to us
        reagent_conc_array[0][reagent_obj.coefficient_dict[reagent_name]
                              ] = condition.reagent_concentrations[reagent_name]
        #
        #logger.info("Reagent temps: " + str(condition.reagent_temperatures))

        # suppose the REAGENT is O2, then by itself in a canister or beaker it would actually be comprised
        # of some small amount of O and O2, as the O2 can dissociate.
        # therefore we may need to pre-equilibrate

        # if there is only one species no pre-equilibration is needed as no dissociation can occur
        if reagent_obj.number_of_species == 1:
            # then directly add the reagents concentrations to their associated molecule concentrations
            condition.molecule_concentrations[name] += condition.reagent_concentrations[reagent_name]

            logger.info(
                "                    This reagent only has one species so no pre-equilibration happened.")
            logger.info("                    This reagent had a concentration of " +
                        str(condition.reagent_concentrations[reagent_name]))
            show_all_concentrations()
            # this break is for the loop on line 44, remember that we check each reagent for pre-equilibration
            # some reagents may need to pre-equilibrate and some may not
            break

        # create the experiment object, this object handles all the necessary mathematical calculations to determine
        # how much of each species is created, consumed during dissociation/pre-equilibration
        pre_equil_model = experiment_class.experiment(reagent_obj,
                                                      condition.reagent_temperatures[reagent_name],
                                                      rxn_profile=reagent_conc_array

                                                      )

        # actually preform the mathematical calculations
        # (diagnostics) diag is an optional argument that if true prints all the output from the integrator inside the experiment object
        # this is a lotttt of extra output
        logger.info("			* reagent_obj.coefficient_dict: " +
                    str(reagent_obj.coefficient_dict))
        logger.info("			* reagent_conc_array -- before: " +
                    str(reagent_conc_array))

        equilibrate(pre_equil_model, progress_tick, diag=False)
        logger.info("			* reagent_conc_array -- after: " +
                    str(pre_equil_model.reaction_profile[-1]))
        # finally after we have obtained the new equilibrated concentrations we place those in the condition object
        for name, index in reagent_obj.coefficient_dict.items():
            concentration_of_this_species = pre_equil_model.reaction_profile[-1][index]
            if np.isnan(concentration_of_this_species):
                logger.info('                    [Warning] Concentration of ' + name +
                            ' is NaN. Falling back to un-pre-equilibrated concentrations. This is a bug.')
                concentration_of_this_species = reagent_conc_array[0][index]
            condition.molecule_concentrations[name] += concentration_of_this_species

        # collect the equilibrated concentrations
        show_all_concentrations()
        # we no longer need this obj
        del pre_equil_model

    # now that we have left the loop over REAGENTS we have pre-equilibrated all necessary REAGENTS
    logger.info(
        "            Pre-equilibration finished -- now all reagents are under pre-equilibrium.")
    # this temp array seems to be due to a change in the parameter specs for the experiment objects instantiation method
    # basically a quick hack that needs to be factorized/cleaned up
    temp = np.zeros((1, puzzle.number_of_species))
    for name, value in puzzle.coefficient_dict.items():
        temp[0][value] = condition.molecule_concentrations[name]
    #logger.info("Conc array passed in: ", temp, '\n')

    # this is the experiment object that represents the "actual reaction"
    true_model = experiment_class.experiment(
        puzzle, condition.reaction_temperature, input_time=[0.0], rxn_profile=temp)
    # now we perform the same mathematical operations as before, but this time we have all the molecules present instead of isolated reactions
    logger.info(
        "            Now we can finally let the actual reaction happen -- let's pour everything into the beaker:")
    equilibrate(true_model, progress_tick, in_conc=condition.reagent_concentrations,
                diag=False)  # the magical math happens

    # for the progress bar, to represent that we finished calculating the true model

    # write the solution to a file
    # so this is the only location where the condition path is used, and if we can wrap this in a fashion, or have the solution object store its 'location' then i can remove the condition paths from driver completely
    # input_output.write_ODE(condition.reaction_temperature, true_model.time_array, true_model.reaction_profile, data_file_name = os.path.join(condition_path, "plotData_t_"))
    written_data = np.transpose(np.column_stack(
        [true_model.time_array, true_model.reaction_profile]))

    logger.info("                Reactant Rate Constants " + HANDY.np_repr(true_model.reactant_rate_constants)
                + "\n                 Product  Rate Constants " +
                HANDY.np_repr(true_model.product_rate_constants)
                + "\n                 Theoretical   K_eq  " +
                HANDY.np_repr(true_model.theoretical_Keq_array)
                + "\n                 Experimental  K_eq  " + HANDY.np_repr(true_model.experimental_Keq_array))

    # sys.stdout.close()
    #sys.stdout = system_output if (temp_diag == True) else sys.stdout
    del true_model

    logger.info("            True model sucessfully constructed.")
    return written_data
###################################


def run_proposed_experiment(puzzle, condition, condition_path, progress_tick, solution, solution_path, written_true_data=None, stream=sys.stdout):
    #sys.stdout = open(diag + "diagnostic_stdout_student_" + str(condition.reaction_temperature) + "_.dat", "w") if (temp_diag == True) else system_output

    # load the species from the true model
    if written_true_data is not None:
        data = written_true_data
    else:
        data = fileIO.load_modelData(os.path.join(
            condition_path, "plotData_t_") + str(condition.reaction_temperature) + '_.dat')

    # make the experiment object
    proposed_model = experiment_class.experiment(
        solution, condition.reaction_temperature, input_time=data[0][:], rxn_profile=np.swapaxes(data[1::1][:], 0, 1))

    try:
        # try to find the rate constants
        rate_consants = proposed_model.get_matrix_rate_solution()
        #logger.info("Rate Constants " + str(rate_consants))

    # try to handle bad rate constants
    except HANDY.User as u_error:
        bad_rxn = np.flatnonzero(u_error.value)

        # if more than one reaction has forward and backward rate constants of negative value then crash
        if(bad_rxn.size > 1):

            logger.info("An issue has been detected. Reactions "
                        + str(bad_rxn + 1)
                        + " are unstable.\n Cannot proceed with user reaction, input new reaction.")
            # sys.stdout.close()
            #sys.stdout = system_output
            # input_output.write_failed_userData(condition.reaction_temperature, data_file_name = os.path.join(solution_path, "plotData_t_"))
            return False
        # if only one reaction is 'bad' then try to remove it and solve again
        elif(bad_rxn.size == 1):

            logger.info("An issue has been detected. Reaction "
                        + str(bad_rxn[0] + 1)
                        + " is unstable. \n Trying to correct simulation by removing reaction.")
            try:
                proposed_model.remove_rxn(bad_rxn[0])

                # try to find the rate constants again
                rate_consants = proposed_model.get_matrix_rate_solution()

            # if we fail again then crash
            except HANDY.User as u_error:

                logger.error("Another issue has been detected. Reaction "
                             + str(bad_rxn[0] + 1)
                             + " is unstable. \n Cannot proceed, crashing.")
                # sys.stdout.close()
                #sys.stdout = system_output
                # input_output.write_failed_userData(condition.reaction_temperature, data_file_name = os.path.join(solution_path, "plotData_t_"))
                return False

        # completed try successfully

    # find the reaction rate
    proposed_model.find_reaction_rate_function()

    # calculate the new reaction profile
    temp = np.zeros(solution.number_of_species)
    logger.info(condition.molecule_concentrations)
    for name, value in solution.coefficient_dict.items():
        temp[value] = condition.molecule_concentrations[name]

    logger.info("            Concentrations: " + str(temp))
    proposed_model.find_reaction_profile(
        input_concentration=temp, diagnostic_output=False)
    proposed_model.remove_flat_region()
    # write the solution to a file
    # so this is the only location where the solution path is used, and if we can wrap this in a fashion, or have the solution object store its 'location' then i can remove the solution paths from driver completely
    # input_output.write_ODE(condition.reaction_temperature, proposed_model.time_array, proposed_model.reaction_profile, data_file_name = os.path.join(solution_path, "plotData_t_"))
    written_data = np.transpose(np.column_stack(
        [proposed_model.time_array, proposed_model.reaction_profile]))

    logger.info(str(proposed_model.rate_constant_array))
    logger.info(str(proposed_model.theoretical_Keq_array))
    logger.info(str(proposed_model.experimental_Keq_array))

    logger.info("            Rate Constant array " + HANDY.np_repr(proposed_model.rate_constant_array)
                + "            Experimental  K_eq  " + HANDY.np_repr(proposed_model.experimental_Keq_array))

    # sys.stdout.close()
    #sys.stdout = system_output if (temp_diag == True) else sys.stdout
    return written_data  # ?

    del proposed_model  # speed up?

    logger.info("            Successfully constructed proposed model.")


# just a wrapper for backwards compatibility until i replace all the places its used in the code
def drive_data(puzzle, puzzle_path, condition, condition_path, progress_tick, solution=None, solution_path=None, written_true_data=None):
    #system_output = sys.stdout
    # if we are simulating the true_model then solution argument is none
    if(solution == None):
        return run_true_experiment(puzzle, condition, condition_path, progress_tick)
    else:
        return run_proposed_experiment(puzzle, condition, condition_path, progress_tick, solution, solution_path, written_true_data)
