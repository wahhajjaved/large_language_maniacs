__author__ = 'Rakesh Kumar'

import sys
import time
from collections import defaultdict

sys.path.append("./")

from controller_man import ControllerMan
from experiment import Experiment
from network_configuration_hardware import NetworkConfiguration
from flow_specification import FlowSpecification
from model.match import Match

sys.path.append("./")
sys.path.append("../")

class QosDemo(Experiment):

    def __init__(self, network_configuration):

        super(QosDemo, self).__init__("number_of_hosts", 1)
        self.network_configuration = network_configuration
        self.controller_port = 6633


    def trigger(self):

	self.network_configuration.setup_network_graph(mininet_setup_gap=1, synthesis_setup_gap=1)
	self.network_configuration.init_flow_specs()
	self.network_configuration.synthesis.synthesize_flow_specifications(self.network_configuration.flow_specs)



def prepare_flow_specifications(measurement_rates=None, tests_duration=None, delay_budget=None):

    flow_specs = []

    flow_match = Match(is_wildcard=True)
    flow_match["ethernet_type"] = 0x0800
    switch_hosts = ["h1s1", "h2s1", "h1s2", "h2s2"]

    for src_host in switch_hosts:
        for dst_host in switch_hosts:
            if src_host != dst_host:
                continue

            h1s1_to_h2s1 = FlowSpecification(src_host_id=src_host,
                                             dst_host_id=dst_host,
                                             configured_rate=50,
                                             flow_match=flow_match,
                                             measurement_rates=measurement_rates,
                                             tests_duration=tests_duration,
                                             delay_budget=delay_budget)

            h2s1_to_h1s1 = FlowSpecification(src_host_id=dst_host,
                                             dst_host_id=src_host,
                                             configured_rate=50,
                                             flow_match=flow_match,
                                             measurement_rates=measurement_rates,
                                             tests_duration=tests_duration,
                                             delay_budget=delay_budget)

            flow_specs.append(h1s1_to_h2s1)
            flow_specs.append(h2s1_to_h1s1)

    return flow_specs

def main():

    flow_specs = prepare_flow_specifications()

    network_configuration =  NetworkConfiguration("ryu_old",
                                      conf_root="configurations/",
                                      synthesis_name="SynthesizeQoS",
                                      synthesis_params={"same_output_queue": True},
                                      flow_specs=flow_specs)

    exp = QosDemo(network_configuration)

    exp.trigger()

if __name__ == "__main__":
    main()
