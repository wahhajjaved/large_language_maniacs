import logging
import sys
import utils

log = logging.getLogger(__name__)


def start(args):
    """
    Start the service(s) passed in the command line. If no services are passed,
    everything in the directory is started. Creates a temporary docker-compose
    file and removes it on Ctrl+c.
    """
    services = utils.get_list_of_services(args.services)
    utils.construct_docker_compose_file(services)
    utils.start_docker_compose_services()


def pull(args):
    """Pulls specified (or all) images built on DockerHub"""
    utils.dockerhub_pull(args.services)


def gitpull(args):
    """Pulls git repositories of specified, or all, projects"""
    services = utils.get_list_of_services(args.services)
    for service in services:
        utils.git_pull_master(service, args.keep)


def attach(args):
    """Drops into a bash shell on a running docker service"""
    if not utils.check_for_docker_compose_file():
        log.error('No microservices docker-compose file found!')
        sys.exit(1)
    utils.docker_compose_attach(args.service)


def run(args):
    """Run a command inside a one-off Docker container"""
    utils.run_one_off_command(args.directory, args.command, args.service)


def kill(args):
    """
    Stop any running Docker containers and remove the temporary docker-compose
    file if it exists
    """
    utils.kill_all_docker_containers()

    if utils.check_for_docker_compose_file():
        utils.remove_docker_compose_file()


def add_commands(subparsers):
    attach_parser = subparsers.add_parser('attach')
    attach_parser.add_argument('service')
    attach_parser.set_defaults(func=attach)

    start_parser = subparsers.add_parser('start')
    start_parser.add_argument('services', nargs='*')
    start_parser.set_defaults(func=start)

    gitpull_parser = subparsers.add_parser('gitpull')
    gitpull_parser.add_argument('--keep', action='store_true', default='False',
                                help='Return to original branch if not on master after pull')
    gitpull_parser.add_argument('services', nargs='*')
    gitpull_parser.set_defaults(func=gitpull)

    pull_parser = subparsers.add_parser('pull')
    pull_parser.add_argument('services', nargs='*')
    pull_parser.set_defaults(func=pull)

    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('--service', help='The name of the service to run the command (e.g. web, worker)')
    run_parser.add_argument('directory')
    run_parser.add_argument('command', nargs='*')
    run_parser.set_defaults(func=run)

    kill_parser = subparsers.add_parser('kill')
    kill_parser.set_defaults(func=kill)
