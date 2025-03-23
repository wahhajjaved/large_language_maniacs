from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

from dss_dispatcher.dispatcher import Dispatcher


class DispatchService:
    """ Service providing access to the dispatcher """

    def __init__(self, dispatcher: Dispatcher, bind_address):
        self._server = SimpleXMLRPCServer(
            bind_address, SimpleXMLRPCRequestHandler, allow_none=True)

        self._server.register_instance(DispatchServiceInterface(dispatcher))

    def serve_forever(self):
        """ Serves until shutdown """
        self._server.serve_forever()

    def shutdown(self):
        """ Stops the serve_forever loop """
        self._server.shutdown()

    def server_close(self):
        """ Cleans-up the server: releases all resources used by the server """
        self._server.server_close()


class DispatchServiceInterface:
    """ Frontend interface to access the Dispatch Service """

    def __init__(self, dispatcher: Dispatcher):
        self._dispatcher = dispatcher

    def register(self) -> str:
        return self._dispatcher.register()

    def next_simulation(self, simulator_id: str) -> dict:
        simulation = self._dispatcher.next_simulation(simulator_id)

        # noinspection PyProtectedMember
        # Although the method name starts with an underscore, this is a
        # documented method. See https://docs.python.org/3/library/collections.html#collections.somenamedtuple._asdict
        return simulation._asdict() if simulation else None

    def notify_finished(self, simulator_id: str, simulation_id: str):
        self._dispatcher.notify_finished(simulator_id, simulation_id)
