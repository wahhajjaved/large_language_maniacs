"""
<Program>
  transition_canonical_to_twopercent.py

<Purpose>
  The purpose of this program is to transition nodes from the
  canonical state to the twopercent state by bypassing
  through the movingto_twopercent state.

<Started>
  November 10, 2010

<Author>
  Monzur Muhammad
  monzum@cs.washington.edu

<Usage>
  Ensure that seattlegeni and seattle are in the PYTHONPATH. 
  Ensure that the database is setup properly and django settings
    are set correctly.

  python transition_canonical_to_twopercent.py 
"""


import os

from seattlegeni.node_state_transitions import node_transition_lib






# The full path to the onepercentmanyevents.resources file, including the filename.
RESOURCES_TEMPLATE_FILE_PATH = os.path.join(os.path.dirname(__file__), "resource_files", "twopercent.resources")





def main():
  """
  <Purpose>
    The main function that calls the process_nodes_and_change_state() function
    in the node_transition_lib passing in the process and error functions.

  <Arguments>
    None
 
  <Exceptions>
    None

  <Side Effects>
    None
  """

  # Open and read the resource file that is necessary for twopercent vessels.
  # This will determine how the vessels will be split and how much resource 
  # will be allocated to each vessel.
  twopercent_resource_fd = file(RESOURCES_TEMPLATE_FILE_PATH)
  twopercent_resourcetemplate = twopercent_resource_fd.read()
  twopercent_resource_fd.close()
  
  # We are going to transition all the nodes that are in the canonical state
  # to the twopercent state. We are going to do this in three different 
  # state. First we are going to transition all the canonical state nodes
  # to the movingto_twopercent state with a no-op function. The reason for
  # this is, so if anything goes wrong, we can revert back.
  # In the second step we are going to attempt to move all the nodes in the
  # movingto_twopercent state to the twopercent state. The way to do this, is
  # we are going to split the vessels by giving each vessel the resources 
  # that are described in the resource template.
  # Next we are going to try to transition all the nodes in the 
  # movingto_twopercent state to the canonical state. Any nodes that failed 
  # to go to the twopercent are still stuck in the movingto_twopercent state,
  # and we want to move them back to the canonical state.

  # Variables that determine weather to mark a node inactive or not.
  mark_node_inactive = False
  mark_node_active = True

  state_function_arg_tuplelist = [
    ("canonical", "movingto_twopercent", node_transition_lib.noop, 
     node_transition_lib.noop, mark_node_inactive),

    ("movingto_twopercent", "twopercent", node_transition_lib.split_vessels, 
     node_transition_lib.noop, mark_node_active, twopercent_resourcetemplate),

    ("movingto_twopercent", "canonical", node_transition_lib.combine_vessels, 
     node_transition_lib.noop, mark_node_inactive)]
 
  sleeptime = 10
  process_name = "canonical_to_twopercent"
  parallel_instances = 10

  #call process_nodes_and_change_state() to start the node state transition
  node_transition_lib.process_nodes_and_change_state(state_function_arg_tuplelist, process_name, sleeptime, parallel_instances) 





if __name__ == '__main__':
  main()
