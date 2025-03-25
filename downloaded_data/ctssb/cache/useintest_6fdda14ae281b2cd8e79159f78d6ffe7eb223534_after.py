import logging
import os
from abc import ABCMeta
from time import sleep

from testwithirods.irods_contoller import IrodsServerController, create_static_irods_server_controller, \
    IrodsServerControllerClassBuilder
from testwithirods.models import IrodsServer, ContainerisedIrodsServer, IrodsUser, Version

_IRODS_CONFIG_FILE_NAME = ".irodsEnv"

_IRODS_HOST_PARAMETER_NAME = "irodsHost"
_IRODS_PORT_PARAMETER_NAME = "irodsPort"
_IRODS_USERNAME_PARAMETER_NAME = "irodsUserName"
_IRODS_ZONE_PARAMETER_NAME = "irodsZone"


class Irods3ServerController(IrodsServerController, metaclass=ABCMeta):
    """
    Controller for containerised iRODS 3 servers.
    """
    def write_connection_settings(self, file_location: str, irods_server: IrodsServer):
        if os.path.isfile(file_location):
            raise ValueError("Settings cannot be written to a file that already exists")

        user = irods_server.users[0]
        config = [
            (_IRODS_USERNAME_PARAMETER_NAME, user.username),
            (_IRODS_HOST_PARAMETER_NAME, irods_server.host),
            (_IRODS_PORT_PARAMETER_NAME, irods_server.port),
            (_IRODS_ZONE_PARAMETER_NAME, user.zone)
        ]
        logging.debug("Writing iRODS connection config to: %s" % file_location)
        with open(file_location, 'w') as settings_file:
            settings_file.write('\n'.join(["%s %s" % x for x in config]))

    def _wait_for_start(self, container: ContainerisedIrodsServer) -> bool:
        logging.info("Waiting for iRODS server to have setup")
        for line in IrodsServerController._DOCKER_CLIENT.logs(container.native_object, stream=True, follow=True):
            logging.debug(line)
            if "exited: irods" in str(line):
                if "not expected" in str(line):
                    return False
                else:
                    break

        # Just because iRODS says it has started, it does not mean it is ready to do queries!
        status_query = IrodsServerController._DOCKER_CLIENT.exec_create(
            container.name, "su - irods -c \"/home/irods/iRODS/irodsctl --verbose status\"", stdout=True)
        while "No servers running" in IrodsServerController._DOCKER_CLIENT.exec_start(status_query).decode("utf8"):
            # Nothing else to check on - just sleep it out
            logging.info("Still waiting on iRODS setup")
            sleep(0.1)

        return True


# Controller for containerised iRODS 3.3.1 servers
Irods3_3_1ServerController = IrodsServerControllerClassBuilder(
    "mercury/icat:3.3.1",
    Version("3.3.1"),
    [IrodsUser("rods", "iplant", "rods", admin=True)],
    Irods3ServerController
).build()

# Static iRODS 3.3.1 server controller, implemented (essentially) using a `Irods3_3_1ServerController` singleton
StaticIrods3_3_1ServerController = create_static_irods_server_controller(Irods3_3_1ServerController())
