import logging
from argparse import ArgumentParser
from configobj import ConfigObj

from updaters.agentupdater import AgentUpdater
from updaters.puppetupdater import PuppetUpdater


def get_arguments():
    """Build and parse command-line arguments."""
    
    parser = ArgumentParser()
    
    parser.add_argument('-e', '--environments', nargs='+', help='Apply puppet updates to these environments')
    parser.add_argument('-p', '--projects', nargs='+', help='Apply puppet updates to these projects')
    parser.add_argument('-m', '--manifests', action='store_true', default=False, help='Apply updates to the puppet manifests directory')
    parser.add_argument('-f', '--config', default='tugboat.cfg', help='Use configuration file specified instead')
    parser.add_argument('-d', '--delay', default=5, type=int, help='Specify delay s seconds between updates to each host')

    return parser.parse_args()
        
def get_config(cmd_line_args):
    """Load configuration file from command-line args or default tugboat.cfg."""
    
    return ConfigObj(cmd_line_args.config)

def run():
    """Start tugboat."""
    
    args = get_arguments()
    config = get_config(args)
    
    log = logging.getLogger(__name__)
    logging.basicConfig(filename='tugboat.log', level=logging.INFO,
                        format='%(asctime)s:%(levelname)s:%(name)s:%(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')
    log.info('Started tugboat')

    puppetupdater = PuppetUpdater(args.environments, args.projects)
    puppetupdater.update()

    agentupdater = AgentUpdater()
    agentupdater.update()

    log.info('Finished')
