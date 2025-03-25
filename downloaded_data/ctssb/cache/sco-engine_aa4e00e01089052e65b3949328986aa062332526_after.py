"""Standard Cortical Observer - Workflow Engine API.

The workflow engine is used to register and run predictive models. The engine
maintains a registry for existing models and it is used to run models for
experiments that are defined in the SCO Data Store.

Workers are used to actually execute a predictive model run. The engine
interacts with these workers over defined communication channels. In the
current implementation the only supported communication forms are via RabbitMQ
or sockets. Thus, each model is registered with the necessary parameters for the
engine communicate run requests to a worker that can execute the model. The
workers may run locally on the same machine as the engine (and the web server)
or on remote machines.

The SCO Engine package is intended to bridge the decoupling of the web server
code from the predictive model code.
"""

from abc import abstractmethod
import json
import pika
from pymongo.errors import DuplicateKeyError

from model import ModelRegistry


# ------------------------------------------------------------------------------
#
# Constants
#
# ------------------------------------------------------------------------------

"""Identifier for known connectors that are used to communicate with model
workers.
"""
CONNECTOR_RABBITMQ = 'rabbitmq'


# ------------------------------------------------------------------------------
#
# Classes
#
# ------------------------------------------------------------------------------

class SCOEngine(object):
    """SCO workflow engine. Maintains a registry of models and communicates with
    backend workers to run predictive models.
    """
    def __init__(self, mongo):
        """Initialize the MongoDB collection where models and connector
        information is stored.

        Parameters
        ----------
        mongo : scodata.MongoDBFactory
            MongoDB connector
        """
        # Data is bein stored in a collection named 'models'
        self.registry = ModelRegistry(mongo)

    def delete_model(self, model_id):
        """Delete the model with the given identifier from the model registry.

        Parameters
        ----------
        model_id : string
            Unique model identifier

        Returns
        -------
        ModelHandle
            handle of deleted model or None if it did not exist.
        """
	# Ensure that the existing model is erased so we can re-register a model
	# with the same identifier later on.
        return self.registry.delete_model(model_id, erase=True)

    def get_model(self, model_id):
        """Get the registered model with the given identifier.

        Parameters
        ----------
        model_id : string
            Unique model identifier

        Returns
        -------
        ModelHandle
            Handle for requested model or None if no model with given identifier
            exists.
        """
        return self.registry.get_model(model_id)

    def list_models(self, limit=-1, offset=-1):
        """Get a list of models in the registry.

	Parameters
	----------
        limit : int
            Limit number of items in the result set
        offset : int
            Set offset in list (order as defined by object store)

        Returns
        -------
        list(ModelHandle)
        """
        return self.registry.list_models(limit=limit, offset=offset)

    def register_model(self, model_id, properties, parameters, outputs, connector):
        """Register a new model with the engine. Expects connection information
        for RabbitMQ to submit model run requests to workers.

        Raises ValueError if the given model identifier is not unique.

        Parameters
        ----------
        model_id : string
            Unique model identifier
        properties : Dictionary
            Dictionary of model specific properties.
        parameters :  list(scodata.attribute.AttributeDefinition)
            List of attribute definitions for model run parameters
        outputs : ModelOutputs
            Description of model outputs
        connector : dict
            Connection information to communicate with model workers. Expected
            to contain at least the connector name 'connector'.

        Returns
        -------
        ModelHandle
        """
        # Validate the given connector information
        if not 'connector' in connector:
            raise ValueError('missing connector name')
        elif connector['connector'] != CONNECTOR_RABBITMQ:
            raise ValueError('unknown connector: ' + str(connector['connector']))
        # Call the connector specific validator. Will raise a ValueError if
        # given connector information is invalid
        RabbitMQClient.validate(connector)
        # Connector information is valid. Ok to register the model. Will raise
        # ValueError if model with given identifier exists. Catch duplicate
        # key error to transform it into a ValueError
        try:
            return self.registry.register_model(
                model_id,
                properties,
                parameters,
                outputs,
                connector
            )
        except DuplicateKeyError as ex:
            raise ValueError(str(ex))

    def run_model(self, model_run, run_url):
        """Execute the given model run.

        Throws a ValueError if the given run specifies an unknown model or if
        the model connector is invalid. An EngineException is thrown if running
        the model (i.e., communication with the backend) fails.

        Parameters
        ----------
        model_run : ModelRunHandle
            Handle to model run
        run_url : string
            URL for model run information
        """
        # Get model to verify that it exists and to get connector information
        model = self.get_model(model_run.model_id)
        if model is None:
            raise ValueError('unknown model: ' + model_run.model_id)
        # By now there is only one connector
        RabbitMQClient(model.connector).run_model(model_run, run_url)

    def upsert_model_properties(self, model_id, properties):
        """Upsert properties of given model.

        Raises ValueError if given property dictionary results in an illegal
        operation.

        Parameters
        ----------
        model_id : string
            Unique model identifier
        properties : Dictionary()
            Dictionary of property names and their new values.

        Returns
        -------
        ModelHandle
            Handle for updated model or None if model doesn't exist
        """
        return self.registry.upsert_object_property(model_id, properties)


# ------------------------------------------------------------------------------
# Connectors
# ------------------------------------------------------------------------------

class SCOEngineConnector(object):
    """Connector to interact with worker."""
    @abstractmethod
    def run_model(self, model_run, run_url):
        """Run model by sending message to remote worker.

        Throws a EngineException if communication with the worker fails.

        Parameters
        ----------
        model_run : ModelRunHandle
            Handle to model run
        run_url : string
            URL for model run information
        """
        pass


class RabbitMQClient(SCOEngineConnector):
    """SCO Workflow Engine client using RabbitMQ. Sends Json messages containing
    run identifier (and experiment identifier) to run model.
    """
    def __init__(self, connector):
        """Initialize the client by providing host name and queue identifier
        for message queue. In addition, requires a HATEOAS reference factory
        to generate resource URLs.

        Parameters
        ----------
        connector : dict
            Connection information for RabbitMQ
        """
        # Validate the connector information. Raises ValueError in case of an
        # invalid connector.
        RabbitMQClient.validate(connector)
        self.host = connector['host']
        self.port = connector['port']
        self.virtual_host = connector['virtualHost']
        self.queue = connector['queue']
        self.user = connector['user']
        self.password = connector['password']

    def run_model(self, model_run, run_url):
        """Run model by sending message to RabbitMQ queue containing the
        run end experiment identifier. Messages are persistent to ensure that
        a worker will process process the run request at some point.

        Throws a EngineException if communication with the server fails.

        Parameters
        ----------
        model_run : ModelRunHandle
            Handle to model run
        run_url : string
            URL for model run information
        """
        # Open connection to RabbitMQ server. Will raise an exception if the
        # server is not running. In this case we raise an EngineException to
        # allow caller to delete model run.
        try:
            credentials = pika.PlainCredentials(self.user, self.password)
            con = pika.BlockingConnection(pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                virtual_host=self.virtual_host,
                credentials=credentials
            ))
            channel = con.channel()
            channel.queue_declare(queue=self.queue, durable=True)
        except pika.exceptions.AMQPError as ex:
            raise EngineException(str(ex), 500)
        # Create model run request
        request = RequestFactory().get_request(model_run, run_url)
        # Send request
        channel.basic_publish(
            exchange='',
            routing_key=self.queue,
            body=json.dumps(request.to_json()),
            properties=pika.BasicProperties(
                delivery_mode = 2, # make message persistent
            )
        )

    @staticmethod
    def validate(connector):
        """Validate the given connector information. Expects the following
        elements: host, port (int), virtualHost, queue, user, and password.

        Raises ValueError if any of the mandatory elements is missing or not of
        expected type.
        """
        for key in ['host', 'port', 'virtualHost', 'queue', 'user', 'password']:
            if not key in connector:
                raise ValueError('missing connector information: ' + key)
        # Try to convert the value for'port' to int.
        int(connector['port'])


# ------------------------------------------------------------------------------
# Request Factory
# ------------------------------------------------------------------------------

class RequestFactory(object):
    """Helper class to generate request object for model runs. The requests are
    interpreted by different worker implementations to run the predictive model.
    """
    def get_request(self, model_run, run_url):
        """Create request object to run model. Requests are handled by SCO
        worker implementations.

        Parameters
        ----------
        model_run : ModelRunHandle
            Handle to model run
        run_url : string
            URL for model run information

        Returns
        -------
        ModelRunRequest
            Object representing model run request
        """
        return ModelRunRequest(
            model_run.identifier,
            model_run.experiment_id,
            run_url
        )


class ModelRunRequest(object):
    """Object capturing information to run predictive model. Contains run and
    experiment identifier (used primarily by local workers) as well as resource
    Url (for remote worker that use SCO Client).

    Attributes
    ----------
    run_id : string
        Unique model run identifier
    experiment_id : string
        Unique experiment identifier
    resource_url : string
        Url for model run instance
    """
    def __init__(self, run_id, experiment_id, resource_url):
        """Initialize request attributes.

        Parameters
        ----------
        run_id : string
            Unique model run identifier
        experiment_id : string
            Unique experiment identifier
        resource_url : string
            Url for model run instance
        """
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.resource_url = resource_url

    @staticmethod
    def from_json(json_obj):
        """Create model run request from Json object.

        Parameters
        ----------
        json_obj : Json Object
            Json dump for object representing the model run request.

        Returns
        -------
        ModelRunRequest
        """
        return ModelRunRequest(
            json_obj['run_id'],
            json_obj['experiment_id'],
            json_obj['href']
        )

    def to_json(self):
        """Return Json representation of the run request.

        Returns
        -------
        Json Object
            Json dump for object representing the model run request.
        """
        return {
            'run_id' : self.run_id,
            'experiment_id' : self.experiment_id,
            'href' : self.resource_url
        }


# ------------------------------------------------------------------------------
# Exception
# ------------------------------------------------------------------------------

class EngineException(Exception):
    """Base class for SCO engine exceptions."""
    def __init__(self, message, status_code):
        """Initialize error message and status code.

        Parameters
        ----------
        message : string
            Error message.
        status_code : int
            Http status code.
        """
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code

    def to_dict(self):
        """Dictionary representation of the exception.

        Returns
        -------
        Dictionary
        """
        return {'message' : self.message}


# ------------------------------------------------------------------------------
#
# Helper Methods
#
# ------------------------------------------------------------------------------

def init_registry(mongo, model_defs, clear_collection=False):
    """Initialize a model registry with a list of model definitions in Json
    format.

    Parameters
    ----------
    mongo : scodata.MongoDBFactory
        Connector for MongoDB
    model_defs : list()
        List of model definitions in Json-like format
    clear_collection : boolean
        If true, collection will be dropped before models are created
    """
    # Create model registry
    registry = SCOEngine(mongo).registry
    # Drop collection if clear flag is set to True
    if clear_collection:
        registry.clear_collection()
    for i in range(len(model_defs)):
        model = registry.from_json(model_defs[i])
        registry.register_model(
            model.identifier,
            model.properties,
            model.parameters,
            model.outputs,
            model.connector
        )


def init_registry_from_json(mongo, filename, clear_collection=False):
    """Initialize a model registry with a list of model definitions that are
    stored in a given file in Json format.

    Parameters
    ----------
    mongo : scodata.MongoDBFactory
        Connector for MongoDB
    filename : string
        Path to file containing model definitions
    clear_collection : boolean
        If true, collection will be dropped before models are created
    """
    # Read model definition file (JSON)
    with open(filename, 'r') as f:
        models = json.load(f)
    init_registry(mongo, models, clear_collection)
