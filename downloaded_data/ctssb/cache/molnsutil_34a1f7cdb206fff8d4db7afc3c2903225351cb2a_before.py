""" 
  Utility module for MOLNs^2. 
  
  molnsutil contains implementations of a persisitent storage API for 
  staging objects to an Object Store in the clouds supported by MOLNs^2. 
  This can be used in MOLNs^2 to write variables that are presistent
  between sessions, provides a convenetient way to get data out of the
  system, and it also provides a means during parallel computations to 
  stage data so that it is visible to all compute engines, in contrast
  to using the local scratch space on the engines.

  molnsutil also contains parallel implementations of common Monte Carlo computational
  workflows, such as the generaion of ensembles and esitmation of moments.
  
"""


import boto
import boto.ec2
from os import environ
import logging
from boto.s3.connection import S3Connection
logging.basicConfig(filename="boto.log", level=logging.DEBUG)
from boto.s3.key import Key
import uuid
import math
import dill
import cloud

import swiftclient.client
import IPython.parallel
import uuid
from IPython.display import HTML, Javascript, display

class MolnsUtilException(Exception):
    pass

class MolnsUtilStorageException(Exception):
    pass


try:
    import dill as pickle
except:
    import pickle

import json

#     s3.json is a JSON file that contains the follwing info:
#
#     'aws_access_key_id' : AWS access key
#     'aws_secret_access_key' : AWS private key
#   s3.json needs to be created and put in .molns/s3.json in the root of the home directory. 

import os
with open(os.environ['HOME']+'/.molns/s3.json','r') as fh:
    s3config = json.loads(fh.read())


class LocalStorage():
    """ This class provides an abstraction for storing and reading objects on/from
        the ephemeral storage. """
    
    def __init__(self):
        self.folder_name = "/home/ubuntu/localarea"
	
    def put(self, filename, data):
        with open(self.folder_name+"/"+filename,'wb') as fh:
            cloud.serialization.cloudpickle.dump(data,fh)

    def get(self, filename):
        with open(self.folder_name+"/"+filename, 'rb') as fh:
            data = cloud.serialization.cloudpickle.load(fh)
        return data

    def delete(self,filename):
        os.remove(self.folder_name+"/"+filename)

class SharedStorage():
    """ This class provides an abstraction for storing and reading objects on/from
        the sshfs mounted storage on the controller. """
    
    def __init__(self):
        self.folder_name = "/home/ubuntu/shared"
	
    def put(self, filename, data):
        with open(self.folder_name+"/"+filename,'wb') as fh:
            cloud.serialization.cloudpickle.dump(data,fh)

    def get(self, filename):
        with open(self.folder_name+"/"+filename, 'rb') as fh:
            data = cloud.serialization.cloudpickle.loads(fh.read())
        return data

    def delete(self,filename):
        os.remove(self.folder_name+"/"+filename)


class S3Provider():
    def __init__(self, bucket_name):
        self.connection = S3Connection(is_secure=False,
                                 calling_format='boto.s3.connection.OrdinaryCallingFormat',
                                 **s3config['credentials']
                                 )
        self.set_bucket(bucket_name)
    
    def set_bucket(self,bucket_name=None):
        if not bucket_name:
            self.bucket_name = "molns_bucket_{0}".format(str(uuid.uuid1()))
            bucket = self.connection.create_bucket(self.bucket_name)
        else:
            self.bucket_name = bucket_name
            try:
                bucket = self.connection.get_bucket(bucket_name)
            except:
                try:
                    bucket = self.connection.create_bucket(bucket_name)
                except Exception, e:
                    raise MolnsUtilStorageException("Failed to create/set bucket in the object store."+str(e))
            self.bucket = bucket

    def create_bucket(self,bucket_name):
        return self.connection.create_bucket(bucket_name)

    def put(self, name, data):
        k = Key(self.bucket)
        if not k:
            raise MolnsUtilStorageException("Could not obtain key in the global store. ")
        k.key = name
        try:
            num_bytes = k.set_contents_from_string(data)
            if num_bytes == 0:
                raise MolnsUtilStorageException("No bytes written to key.")
        except Exception, e:
            return {'status':'failed', 'error':str(e)}
        return {'status':'success', 'num_bytes':num_bytes}

    def get(self, name, validate=False):
        k = Key(self.bucket,validate)
        k.key = name
        try:
            obj = k.get_contents_as_string()
        except boto.exception.S3ResponseError, e:
            raise MolnsUtilStorageException("Could not retrive object from the datastore."+str(e))
        return obj

    def delete(self, name):
        """ Delete an object. """
        k = Key(self.bucket)
        k.key = name
        self.bucket.delete_key(k)


    def delete_all(self):
        """ Delete all objects in the global storage area. """
        for k in self.bucket.list():
            self.bucket.delete_key(k.key)

    def list(self):
        """ List all containers. """
        return self.bucket.list()


class SwiftProvider():
    def __init__(self, bucket_name):
        self.connection = swiftclient.client.Connection(auth_version=2.0,**s3config['credentials'])
        self.set_bucket(bucket_name)
    
    def set_bucket(self,bucket_name):
        self.bucket_name = bucket_name
        if not bucket_name:
            self.bucket_name = "molns_bucket_{0}".format(str(uuid.uuid1()))
            bucket = self.provider.create_bucket(self.bucket_name)
        else:
            self.bucket_name = bucket_name
            try:
                bucket = self.connection.get_bucket(bucket_name)
            except:
                try:
                    bucket = self.create_bucket(bucket_name)
                except Exception, e:
                    raise MolnsUtilStorageException("Failed to create/set bucket in the object store."+str(e))
            
            self.bucket = bucket


    def create_bucket(self, bucket_name):
        bucket = self.connection.put_container(bucket_name)
        return bucket

    def get_all_buckets(self):
        """ List all bucket in this provider. """

    def put(self, object_name, data):
        self.connection.put_object(self.bucket_name, object_name, data)

    def get(self, object_name, validate=False):
        (response, obj) = self.connection.get_object(self.bucket_name, object_name)
        return obj

    def delete(self, object_name):
        self.connection.delete_object(self.bucket_name, object_name)

    def delete_all(self):
        print self.connection.head_container(self.bucket_name)

    def list(self):
        """ TODO: implement. """

    def close(self):
        self.connection.close()

    def __del__(self):
        self.close()


class PersistentStorage():
    """
       Provides an abstaction for interacting with the Object Stores
       of the supported clouds.
    """

    def __init__(self, bucket_name=None):
        #print s3config['credentials']
        
        if bucket_name is None:
            # try reading it from the config file
            try:
                bucket_name = s3config['bucket_name']
            except:
                pass
    
        if s3config['provider_type'] == 'EC2':
            self.provider = S3Provider(bucket_name)
        # self.provider = S3Provider()
        elif s3config['provider_type'] == 'OpenStack':
            self.provider = SwiftProvider(bucket_name)
        else:
            raise MolnsUtilStorageException("Unknown provider type.")
        

    def list_buckets(self):
        all_buckets=self.provider.get_all_buckets()
        buckets = []
        for bucket in all_buckets:
            buckets.append(bucket.name)
        return buckets

    def set_bucket(self,bucket_name=None):
        if not bucket_name:
            bucket = self.provider.create_bucket("molns_bucket_{0}".format(str(uuid.uuid1())))
        else:
            try:
                bucket = self.provider.get_bucket(bucket_name)
            except:
                try:
                    bucket = self.provider.create_bucket(bucket_name)
                except Exception, e:
                    raise MolnsUtilStorageException("Failed to create/set bucket in the object store: "+str(e))
                        
        self.bucket = bucket

    def put(self, name, data):
        self.provider.put(name, cloud.serialization.cloudpickle.dumps(data))
    
    
    def get(self, name, validate=False):
        return cloud.serialization.cloudpickle.loads(self.provider.get(name, validate))
    
    def delete(self, name):
        """ Delete an object. """
        self.provider.delete(name)
    
    def list(self):
        """ List all containers. """
        return self.provider.list()

    def delete_all(self):
        """ Delete all objects in the global storage area. """
        self.provider.delete_all()

#------  default aggregators -----
def builtin_aggregator_list_append(new_result, aggregated_results=None, parameters=None):
    """ default chunk aggregator. """
    if aggregated_results is None:
        aggregated_results = []
    aggregated_results.append(new_result)
    return aggregated_results

def builtin_aggregator_add(new_result, aggregated_results=None, parameters=None):
    """ chunk aggregator for the mean function. """
    if aggregated_results is None:
        return (new_result, 1)
    return (aggregated_results[0]+new_result, aggregated_results[1]+1)

def builtin_aggregator_sum_and_sum2(new_result, aggregated_results=None, parameters=None):
    """ chunk aggregator for the mean+variance function. """
    if aggregated_results is None:
        return (new_result, new_result**2, 1)
    return (aggregated_results[0]+new_result, aggregated_results[1]+new_result**2, aggregated_results[2]+1)

def builtin_reducer_default(result_list, parameters=None):
    """ Default passthrough reducer. """
    return result_list

def builtin_reducer_mean(result_list, parameters=None):
    """ Reducer to calculate the mean, use with 'builtin_aggregator_add' aggregator. """
    sum = 0.0
    n = 0.0
    for r in result_list:
        sum += r[0]
        n += r[1]
    return sum/n

def builtin_reducer_mean_variance(result_list, parameters=None):
    """ Reducer to calculate the mean and variance, use with 'builtin_aggregator_sum_and_sum2' aggregator. """
    sum = 0.0
    sum2 = 0.0
    n = 0.0
    for r in result_list:
        sum += r[0]
        sum2 += r[1]
        n += r[2]
    return (sum/n, (sum2 - (sum**2)/n)/n )


#----- functions to use for the DistributedEnsemble class ----
def run_ensemble_map_and_aggregate(model_class, parameters, param_set_id, seed_base, number_of_trajectories, mapper, aggregator=None):
    """ Generate an ensemble, then run the mappers are aggreator.  This will not store the results. """
    import pyurdme
    from pyurdme.nsmsolver import NSMSolver
    import sys
    import uuid
    if aggregator is None:
        aggregator = builtin_aggregator_list_append
    # Create the model
    try:
        model_class_cls = cloud.serialization.cloudpickle.loads(model_class)
        if parameters is not None:
            model = model_class_cls(**parameters)
        else:
            model = model_class_cls()
    except Exception as e:
        notes = "Error instantiation the model class, caught {0}: {1}\n".format(type(e),e)
        notes += "pyurdme in dir()={0}\n".format('pyurdme' in dir())
        notes +=  "dir={0}\n".format(dir())
        raise MolnsUtilException(notes)
    # Run the solver
    solver = NSMSolver(model)
    res = None
    num_processed = 0
    for i in range(number_of_trajectories):
        try:
            result = solver.run(seed=seed_base+i)
            mapres = mapper(result)
            res = aggregator(mapres, res)
            num_processed +=1
        except TypeError as e:
            notes = "Error running mapper and aggregator, caught {0}: {1}\n".format(type(e),e)
            notes += "type(mapper) = {0}\n".format(type(mapper))
            notes += "type(aggregator) = {0}\n".format(type(aggregator))
            notes +=  "dir={0}\n".format(dir())
            raise MolnsUtilException(notes)
    return {'result':res, 'param_set_id':param_set_id, 'num_sucessful':num_processed, 'num_failed':number_of_trajectories-num_processed}

def run_ensemble(model_class, parameters, param_set_id, seed_base, number_of_trajectories, storage_mode="Shared"):
    """ Generates an ensemble consisting of number_of_trajectories realizations by
        running pyurdme nt number of times. The resulting pyurdme result objects
        are serialized and written to one of the MOLNs storage locations, each
        assigned a random filename. The default behavior is to write the
        files to the Shared storage location (global non-persistent). Optionally, files can be
        written to the Object Store (global persistent), storage_model="Persistent"
        
        Returns: a list of filenames for the serialized result objects.
        
        """
    import pyurdme
    from pyurdme.nsmsolver import NSMSolver
    import sys
    import uuid
    from molnsutil import PersistentStorage, LocalStorage, SharedStorage
    
    if storage_mode=="Shared":
        storage  = SharedStorage()
    elif storage_mode=="Persistent":
        storage = PersistentStorage()
    else:
        raise MolnsUtilException("Unknown storage type '{0}'".format(storage_mode))
    # Create the model
    try:
        model_class_cls = cloud.serialization.cloudpickle.loads(model_class)
        if parameters is not None:
            model = model_class_cls(**parameters)
        else:
            model = model_class_cls()
    except Exception as e:
        notes = "Error instantiation the model class, caught {0}: {1}\n".format(type(e),e)
        notes += "pyurdme in dir()={0}\n".format('pyurdme' in dir())
        notes +=  "dir={0}\n".format(dir())
        raise MolnsUtilException(notes)

    # Run the solver
    solver = NSMSolver(model)
    filenames = []
    for i in range(number_of_trajectories):
        try:
            result = solver.run(seed=seed_base+i)
            filename = str(uuid.uuid1())
            storage.put(filename, result)
            filenames.append(filename)
        except:
            raise
    
    return {'filenames':filenames, 'param_set_id':param_set_id}

def map_and_aggregate(results, param_set_id, mapper, aggregator=None, cache_results=False):
    """ Reduces a list of results by applying the map function 'mapper'.
        When this function is applied on an engine, it will first
        look for the result object in the local ephemeral storage (cache),
        then in the Shared area (global non-persisitent), then in the
        Object Store (global persistent).
        
        If cache_results=True, then result objects will be written
        to the local epehemeral storage (file cache), so subsequent
        postprocessing jobs may run faster.
        
        """
    import dill
    import numpy
    from molnsutil import PersistentStorage, LocalStorage, SharedStorage
    ps = PersistentStorage()
    ss = SharedStorage()
    ls = LocalStorage()
    if aggregator is None:
        aggregator = builtin_aggregator_list_append
    num_processed=0
    res = None
    result = None
    for i,filename in enumerate(results):
        enotes = ''
        try:
            result = ls.get(filename)
        except Exception as e:
            enotes += "In fetching from local store, caught  {0}: {1}\n".format(type(e),e)
        
        if result is None:
            try:
                result = ss.get(filename)
                if cache_results:
                    ls.put(filename, result)
            except Exception as e:
                enotes += "In fetching from shared store, caught  {0}: {1}\n".format(type(e),e)
        if result is None:
            try:
                result = ps.get(filename)
                if cache_results:
                    ls.put(filename, result)
            except Exception as e:
                enotes += "In fetching from global store, caught  {0}: {1}\n".format(type(e),e)
        if result is None:
            notes = "Error could not find file '{0}' in storage\n".format(filename)
            notes += enotes
            raise MolnsUtilException(notes)

        try:
            mapres = mapper(result)
            res = aggregator(mapres, res)
            num_processed +=1
        except Exception as e:
            notes = "Error running mapper and aggregator, caught {0}: {1}\n".format(type(e),e)
            notes += "type(mapper) = {0}\n".format(type(mapper))
            notes += "type(aggregator) = {0}\n".format(type(aggregator))
            notes +=  "dir={0}\n".format(dir())
            raise MolnsUtilException(notes)

    return {'result':res, 'param_set_id':param_set_id, 'num_sucessful':num_processed, 'num_failed':len(results)-num_processed}

    #return res

class DistributedEnsemble():
    """ A class to provide an API for execution of a distributed ensemble. """
    
    def __init__(self, model_class=None, parameters=None, client=None):
        """ Constructor """
        self.my_class_name = 'DistributedEnsemble'
        self.model_class = cloud.serialization.cloudpickle.dumps(model_class)
        self.parameters = [parameters]
        self.number_of_realizations = 0
        self.seed_base = self.generate_seed_base()
        # A chunk list
        self.result_list = {}
        # Set the Ipython.parallel client
        self._update_client(client)
    
    def generate_seed_base(self):
        """ Create a random number and truncate to 64 bits. """
        x = int(uuid.uuid4())
        if x.bit_length() >= 64:
            x = x & ((1<<64)-1)
            if x > (1 << 63) -1:
                x -= 1 << 64
        return x

    #--------------------------
    def save_state(self, name):
        """ Serialize the state of the ensemble, for persistence beyond memory."""
        state = {}
        state['model_class'] = self.model_class
        state['parameters'] = self.parameters
        state['number_of_realizations'] = self.number_of_realizations
        state['seed_base'] = self.seed_base
        state['result_list'] = self.result_list
        if not os.path.isdir('.molnsutil'):
            os.makedirs('.molnsutil')
        with open('.molnsutil/{1}-{0}'.format(name, self.my_class_name)) as fd:
            pickle.dump(state, fd)

    def load_state(self, name):
        """ Recover the state of an ensemble from a previous save. """
        with open('.molnsutil/{1}-{0}'.format(name, self.my_class_name)) as fd:
            state = pickle.load(fd)
        if state['model_class'] is not self.model_class:
            raise MolnsUtilException("Can only load state of a class that is identical to the original class")
        self.parameters = state['parameters']
        self.number_of_realizations = state['number_of_realizations']
        self.seed_base = state['seed_base']
        self.result_list = state['result_list']
    
    #--------------------------
    # MAIN FUNCTION
    #--------------------------
    def run(self, mapper, aggregator=None, reducer=None, number_of_realizations=None, chunk_size=None, verbose=True, progress_bar=True, store_realizations=True, storage_mode="Shared", cache_results=False):
        """ Main entry point """
        if store_realizations:
            # Do we have enough trajectores yet?
            if number_of_realizations is None and self.number_of_realizations == 0:
                raise MolnsUtilException("number_of_realizations is zero")
            # Run simulations
            if self.number_of_realizations < number_of_realizations:
                self.add_realizations( number_of_realizations - self.number_of_realizations, chunk_size=chunk_size, verbose=verbose, storage_mode=storage_mode, cache_results=cache_results)

            if chunk_size is None:
                chunk_size = self._determine_chunk_size(self.number_of_realizations)
            if verbose:
                print "Running mapper & aggregator on the result objects (number of results={0}, chunk size={1})".format(self.number_of_realizations*len(self.parameters), chunk_size)
            else:
                progress_bar=False
            
            # chunks per parameter
            num_chunks = int(math.ceil(self.number_of_realizations/float(chunk_size)))
            chunks = [chunk_size]*(num_chunks-1)
            chunks.append(self.number_of_realizations-chunk_size*(num_chunks-1))
            # total chunks
            pchunks = chunks*len(self.parameters)
            num_pchunks = num_chunks*len(self.parameters)
            pparams = []
            param_set_ids = []
            presult_list = []
            for id, param in enumerate(self.parameters):
                param_set_ids.extend( [id]*num_chunks )
                pparams.extend( [param]*num_chunks )
                for i in range(num_chunks):
                    presult_list.append( self.result_list[id][i*chunk_size:(i+1)*chunk_size] )
            # Run mapper & aggregator
            #if len(presult_list) != len(param_set_ids):
            #    raise MolnsUtilException(" len(presult_list) != len(param_set_ids) ")
            #if len(presult_list) != len():
            #def map_and_aggregate(results, param_set_id, mapper, aggregator=None, cache_results=False):
            #print "len(presult_list) = {0}".format(len(presult_list))
            #print "len(param_set_ids) = {0}".format(len(param_set_ids))
            #print "num_pchunks = {0} num_chunks={1} len(self.parameters)={2}".format(num_pchunks, num_chunks, len(self.parameters))
            #print "presult_list = {0}".format(presult_list)
            results = self.lv.map_async(map_and_aggregate, presult_list, param_set_ids, [mapper]*num_pchunks,[aggregator]*num_pchunks,[cache_results]*num_pchunks)
        else:
            # If we don't store the realizations (or use the stored ones)
            if chunk_size is None:
                chunk_size = self._determine_chunk_size(number_of_realizations)
            if not verbose:
                progress_bar=False
            else:
                print "Generating {0} realizations of the model, running mapper & aggregator (chunk size={1})".format(number_of_realizations,chunk_size)
            
            # chunks per parameter
            num_chunks = int(math.ceil(number_of_realizations/float(chunk_size)))
            chunks = [chunk_size]*(num_chunks-1)
            chunks.append(number_of_realizations-chunk_size*(num_chunks-1))
            # total chunks
            pchunks = chunks*len(self.parameters)
            num_pchunks = num_chunks*len(self.parameters)
            pparams = []
            param_set_ids = []
            for id, param in enumerate(self.parameters):
                param_set_ids.extend( [id]*num_chunks )
                pparams.extend( [param]*num_chunks )
            
            seed_list = []
            for _ in range(len(self.parameters)):
                #need to do it this way cause the number of run per chunk might not be even
                seed_list.extend(range(self.seed_base, self.seed_base+number_of_realizations, chunk_size))
                self.seed_base += number_of_realizations
            #def run_ensemble_map_and_aggregate(model_class, parameters, seed_base, number_of_trajectories, mapper, aggregator=None):
            results  = self.lv.map_async(run_ensemble_map_and_aggregate, [self.model_class]*num_pchunks, pparams, param_set_ids, seed_list, pchunks, [mapper]*num_pchunks, [aggregator]*num_pchunks)

    
        if progress_bar:
            # This should be factored out somehow.
            divid = str(uuid.uuid4())
            pb = HTML("""
                          <div style="border: 1px solid black; width:500px">
                          <div id="{0}" style="background-color:blue; width:0%">&nbsp;</div>
                          </div>
                          """.format(divid))
            display(pb)
        
        # We process the results as they arrive.
        mapped_results = {}
        for i,rset in enumerate(results):
            param_set_id = rset['param_set_id']
            r = rset['result']
            if param_set_id not in mapped_results:
                mapped_results[param_set_id] = []
            if type(r) is type([]):
                mapped_results[param_set_id].extend(r) #if a list is returned, extend that list
            else:
                mapped_results[param_set_id].append(r)
            if progress_bar:
                display(Javascript("$('div#%s').width('%f%%')" % (divid, 100.0*(i+1)/len(results))))

        if verbose:
            print "Running reducer on mapped and aggregated results (size={0})".format(len(mapped_results[0]))
        if reducer is None:
            reducer = builtin_reducer_default
        # Run reducer
        return self.run_reducer(reducer, mapped_results)



    def run_reducer(self, reducer, mapped_results):
        """ Inside the run() function, apply the reducer to all of the map'ped-aggregated result values. """
        return reducer(mapped_results[0], parameters=self.parameters[0])



    
    #--------------------------
    def add_realizations(self, number_of_realizations=None, chunk_size=None, verbose=True, progress_bar=True, storage_mode="Shared"):
        """ Add a number of realizations to the ensemble. """
        if number_of_realizations is None:
            raise MolnsUtilException("No number_of_realizations specified")
        if type(number_of_realizations) is not type(1):
            raise MolnsUtilException("number_of_realizations must be an integer")
        
        if chunk_size is None:
            chunk_size = self._determine_chunk_size(number_of_realizations)

        if not verbose:
            progress_bar=False
        else:
            print "Generating {0} realizations of the model (chunk size={1})".format(number_of_realizations,chunk_size)
        
        self.number_of_realizations += number_of_realizations
        
        num_chunks = int(math.ceil(number_of_realizations/chunk_size))
        chunks = [chunk_size]*(num_chunks-1)
        chunks.append(number_of_realizations-chunk_size*(num_chunks-1))
        # total chunks
        pchunks = chunks*len(self.parameters)
        num_pchunks = num_chunks*len(self.parameters)
        pparams = []
        param_set_ids = []
        for id, param in enumerate(self.parameters):
            param_set_ids.extend( [id]*num_chunks )
            pparams.extend( [param]*num_chunks )
        
        seed_list = []
        for _ in range(len(self.parameters)):
            #need to do it this way cause the number of run per chunk might not be even
            seed_list.extend(range(self.seed_base, self.seed_base+number_of_realizations, chunk_size))
            self.seed_base += number_of_realizations
        
        results  = self.lv.map_async(run_ensemble, [self.model_class]*num_pchunks, pparams, param_set_ids, seed_list, pchunks, [storage_mode]*num_pchunks)
            #TODO: results here should be a class 'RemoteResults' which has model parameters and location
        
        # TODO: Refactor this so it can be reused by other methods.
        if progress_bar:
            # This should be factored out somehow.
            divid = str(uuid.uuid4())
            pb = HTML("""
                          <div style="border: 1px solid black; width:500px">
                          <div id="{0}" style="background-color:blue; width:0%">&nbsp;</div>
                          </div>
                          """.format(divid))
            display(pb)
        
        # We process the results as they arrive.
        for i,ret in enumerate(results):
            r = ret['filenames']
            param_set_id = ret['param_set_id']
            if param_set_id not in self.result_list:
                self.result_list[param_set_id] = []
            self.result_list[param_set_id].extend(r)
            if progress_bar:
                display(Javascript("$('div#%s').width('%f%%')" % (divid, 100.0*(i+1)/len(results))))
        
        
        return {'wall_time':results.wall_time}
    

    
    #-------- Convenience functions with builtin mappers/reducers  ------------------

    def mean_variance(self, mapper=None, number_of_realizations=None, chunk_size=None, verbose=True, store_realizations=True, storage_mode="Shared", cache_results=False):
        """ Compute the mean and variance (second order central moment) of the function g(X) based on number_of_realizations realizations
            in the ensemble. """
        return self.run(mapper=mapper, aggregator=builtin_aggregator_sum_and_sum2, reducer=builtin_reducer_mean_variance, number_of_realizations=number_of_realizations, chunk_size=chunk_size, verbose=verbose, store_realizations=store_realizations, storage_mode=storage_mode, cache_results=cache_results)

    def mean(self, mapper=None, number_of_realizations=None, chunk_size=None, verbose=True, store_realizations=True, storage_mode="Shared", cache_results=False):
        """ Compute the mean of the function g(X) based on number_of_realizations realizations
            in the ensemble. It has to make sense to say g(result1)+g(result2). """
        return self.run(mapper=mapper, aggregator=builtin_aggregator_add, reducer=builtin_reducer_mean, number_of_realizations=number_of_realizations, chunk_size=chunk_size, verbose=verbose, store_realizations=store_realizations, storage_mode=storage_mode, cache_results=cache_results)
   

    def moment(self, g=None, order=1, number_of_realizations=None):
        """ Compute the moment of order 'order' of g(X), using number_of_realizations
            realizations in the ensemble. """
        raise Exception('TODO')
    
    def histogram_density(self, g=None, number_of_realizations=None):
        """ Estimate the probability density function of g(X) based on number_of_realizations realizations
            in the ensemble. """
        raise Exception('TODO')

    #--------------------------

    def _update_client(self, client=None):
        if client is None:
            self.c = IPython.parallel.Client()
        else:
            self.c = client
        self.c[:].use_dill()
        self.dv = self.c[:]
        self.lv = self.c.load_balanced_view()

    def _determine_chunk_size(self, number_of_realizations):
        """ Determine a optimal chunk size. """
        num_proc = len(self.c.ids)
        return int(max(1, round(number_of_realizations/float(num_proc))))

    # TODO: take a hard look at the following functions
    def rebalance_chunk_list(self):
        """ It seems like it can be necessary to be able to rebalance the chunk list if
            the number of engines change. Like if you suddenly have more engines than chunks, you
            want to create more chunks. """

    def _clear_cache(self):
        """ Remove all cached result objects on the engines. """
        pass
        # TODO
    
    def delete_realizations(self):
        """ Delete realizations from the object store. """
        pass
        # TODO



class ParameterSweep(DistributedEnsemble):
    """ Making parameter sweeps on distributed compute systems easier. """

    def __init__(self, model_class, parameters):
        """ Constructor.
        Args:
          model_class: a class object of the model for simulation, must be a sub-class of URDMEModel
          parameters:  either a dict or a list.
            If it is a dict, the keys are the arguments to the class constructions and the
              values are a list of values that argument should take.
              e.g.: {'arg1':[1,2,3],'arg2':[1,2,3]}  will produce 9 parameter points.
            If it is a list, where each element of the list is a dict
            """
        self.my_class_name = 'ParameterSweep'
        self.model_class = cloud.serialization.cloudpickle.dumps(model_class)
        self.number_of_realizations = 0
        self.seed_base = self.generate_seed_base()
        self.result_list = {}
        self.parameters = []
        # process the parameters
        if type(parameters) is type({}):
            pkeys = parameters.keys()
            pkey_lens = [0]*len(pkeys)
            pkey_ndxs = [0]*len(pkeys)
            for i,key in enumerate(pkeys):
                pkey_lens[i] = len(parameters[key])
            num_params = sum(pkey_lens)
            for _ in range(num_params):
                param = {}
                for i,key in enumerate(pkeys):
                    param[key] = parameters[key][pkey_ndxs[i]]
                self.parameters.append(param)
                # incriment indexes
                for i,key in enumerate(pkeys):
                    pkey_ndxs[i] += 1
                    if pkey_ndxs[i] >= pkey_lens[i]:
                        pkey_ndxs[i] = 0
                    else:
                        break
        
        elif type(parameters) is type([]):
            self.parameters = parameters
        else:
            raise MolnsUtilException("parameters must be a dict.")

        # Set the Ipython.parallel client
        self._update_client(client)

    def _determine_chunk_size(self, number_of_realizations):
        """ Determine a optimal chunk size. """
        num_procs = len(self.c.ids)
        num_params = len(self.parameters)
        if num_params >= num_procs:
            return number_of_realizations
        return int(max(1, math.ceil(number_of_realizations*num_params/float(num_procs))))

    def run_reducer(self, reducer, mapped_results):
        """ Inside the run() function, apply the reducer to all of the map'ped-aggregated result values. """
        ret = ParameterSweepResultList()
        for param_set_id, param in enumerate(self.parameters):
            ret.append(ParameterSweepResult(reducer(mapped_results[param_set_id], parameters=param), parameters=param))
        return ret
    #--------------------------




class ParameterSweepResult():
    """TODO"""
    def __init__(self, result, parameters):
        self.result = result
        self.parameters = parameters

class ParameterSweepResultList(list):
    """TODO"""
    pass





if __name__ == '__main__':
    
    ga = PersistentStorage()
    #print ga.list_buckets()
    ga.put('testtest.pyb',"fdkjshfkjdshfjdhsfkjhsdkjfhdskjf")
    print ga.get('testtest.pyb') 
    ga.delete('testtest.pyb')
    ga.list()
    ga.put('file1', "fdlsfjdkls")
    ga.put('file2', "fdlsfjdkls")
    ga.put('file2', "fdlsfjdkls")
    ga.delete_all()
