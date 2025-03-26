import json
import uuid
import hashlib
import time

import anchore_engine.services.common
import anchore_engine.configuration.localconfig
import anchore_engine.auth.anchore_resources
import anchore_engine.auth.aws_ecr
from anchore_engine import utils as anchore_utils
from anchore_engine.subsys import taskstate, logger, archive as archive_sys
from anchore_engine.clients import localanchore, simplequeue
from anchore_engine.db import db_users, db_subscriptions, db_catalog_image, db_policybundle, db_policyeval, db_eventlog, \
    db_registries, db_services, db_archivedocument
import anchore_engine.clients.policy_engine
from anchore_engine.services.policy_engine.api.models import ImageUpdateNotification, FeedUpdateNotification, ImageVulnerabilityListing, ImageIngressRequest, ImageIngressResponse, LegacyVulnerabilityReport

def registry_lookup(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    image_info = None
    input_type = None

    for t in ['tag', 'digest']:
        if t in params:
            input_string = params[t]
            if input_string:
                input_type = t
                image_info = anchore_engine.services.common.get_image_info(userId, "docker", input_string, registry_lookup=False, registry_creds=(None,None))
                break

    try:
        if not image_info:
            httpcode = 500
            raise Exception("need 'tag' or 'digest' in url params")
        else:
            try:
                registry_creds = db_registries.get_byuserId(userId, session=dbsession)
                try:
                    refresh_registry_creds(registry_creds, dbsession)
                except Exception as err:
                    logger.warn("failed to refresh registry credentials - exception: " + str(err))

                digest, manifest = anchore_engine.services.common.lookup_registry_image(userId, image_info, registry_creds)
                return_object['digest'] = image_info['registry'] + "/" + image_info['repo'] + "@" + digest
                return_object['manifest'] = manifest
                httpcode = 200
            except Exception as err:
                httpcode = 404
                raise Exception("cannot lookup image in registry - detail: " + str(err))
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def image(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    image_info = None
    input_type = None

    # set up params
    registry_lookup = False
    if params and 'registry_lookup' in params:
        registry_lookup = params['registry_lookup']

    history = False
    if params and 'history' in params:
        history = params['history']

    for t in ['tag', 'digest', 'imageId']:
        if t in params:
            input_string = params[t]
            if input_string:
                input_type = t
                image_info = anchore_engine.services.common.get_image_info(userId, "docker", input_string, registry_lookup=False, registry_creds=(None, None))
                break

    httpcode = 500
    try:
        if method == 'GET':
            if not input_string:
                httpcode = 200
                return_object = db_catalog_image.get_all_byuserId(userId, session=dbsession)
            else:
                if registry_lookup:
                    try:
                        registry_creds = db_registries.get_byuserId(userId, session=dbsession)
                        try:
                            refresh_registry_creds(registry_creds, dbsession)
                        except Exception as err:
                            logger.warn("failed to refresh registry credentials - exception: " + str(err))
                        image_info = anchore_engine.services.common.get_image_info(userId, "docker", input_string, registry_lookup=True, registry_creds=registry_creds)
                    except Exception as err:
                        httpcode = 404
                        raise Exception("cannot perform registry lookup - exception: " + str(err))

                if image_info:
                    try:
                        if history:
                            if input_type == 'tag':
                                filterkeys = ['registry', 'repo', 'tag', 'imageId']
                            else:
                                raise Exception("cannot use history without specifying an input tag")
                        else:
                            filterkeys = ['registry', 'repo', 'tag', 'digest', 'imageId']

                        dbfilter = {}
                        for k in filterkeys:
                            if k in image_info and image_info[k]:
                                dbfilter[k] = image_info[k]

                        logger.debug("image DB lookup filter: " + json.dumps(dbfilter, indent=4))
                        if history:
                            image_records = db_catalog_image.get_byimagefilter(userId, 'docker', dbfilter=dbfilter, session=dbsession)
                        else:
                            image_records = db_catalog_image.get_byimagefilter(userId, 'docker', dbfilter=dbfilter, onlylatest=True, session=dbsession)

                        if image_records:
                            return_object = image_records
                            httpcode = 200
                        else:
                            httpcode = 404
                            raise Exception("image data not found in DB")
                    except Exception as err:
                        raise err
                else:
                    httpcode = 404
                    raise Exception("image not found in DB")

        elif method == 'POST':
            if input_type == 'digest':
                raise Exception("catalog add only supports adding by tag")

            # body
            jsondata = {}
            if bodycontent:
                jsondata = bodycontent
    
            dockerfile = None
            if 'dockerfile' in jsondata:
                dockerfile = jsondata['dockerfile']
                try:
                    dockerfile.decode('base64')
                except Exception as err:
                    raise Exception("input dockerfile data must be base64 encoded - exception on decode: " + str(err))

            image_record = {}
            try:
                registry_creds = db_registries.get_byuserId(userId, session=dbsession)
                try:
                    refresh_registry_creds(registry_creds, dbsession)
                except Exception as err:
                    logger.warn("failed to refresh registry credentials - exception: " + str(err))

                image_info = anchore_engine.services.common.get_image_info(userId, 'docker', input_string, registry_lookup=True, registry_creds=registry_creds)
                logger.debug("ADDING/UPDATING IMAGE IN IMAGE POST: " + str(image_info))
                image_records = add_or_update_image(dbsession, userId, image_info['imageId'], tags=[image_info['fulltag']], digests=[image_info['fulldigest']], dockerfile=dockerfile)
                if image_records:
                    image_record = image_records[0]

            except Exception as err:
                httpcode = 404
                raise err

            if image_record:
                httpcode = 200
                return_object = image_record
            else:
                httpcode = 404
                raise Exception("could not add input image")

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def image_imageDigest(dbsession, request_inputs, imageDigest, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    image_info = None
    input_type = None
    
    try:
        if method == 'GET':
            image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
            if image_record:
                httpcode = 200
                return_object = [image_record]
            else:
                httpcode = 404
                raise Exception("image not found in DB")

        elif method == 'DELETE':
            try:
                image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
                if image_record:
                    
                    return_object, httpcode = do_image_delete(userId, image_record, dbsession)
                    if httpcode not in range(200,299):
                        raise Exception(return_object)

                else:
                    return_object = True
                    httpcode = 200

            except Exception as err:
                #httpcode = 500
                raise err
            
        elif method == 'PUT':
            # update an image

            jsondata = {}
            if bodycontent:
                jsondata = bodycontent

            updated_image_record = jsondata

            image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
            if image_record:
                rc = db_catalog_image.update_record(updated_image_record, session=dbsession)
                image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)

                httpcode = 200
                return_object = [image_record]
            else:
                httpcode = 404
                raise Exception("image not found")

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def image_import(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        jsondata = {}
        if bodycontent:
            try:
                jsondata = bodycontent
            except Exception as err:
                raise err

        anchore_data = [jsondata]

        try:
            # extract necessary input from anchore analysis data
            a = anchore_data[0]
            imageId = a['image']['imageId']
            docker_data = a['image']['imagedata']['image_report']['docker_data']

            digests = []
            islocal = False
            if not docker_data['RepoDigests']:
                islocal = True
            else:
                for digest in docker_data['RepoDigests']:
                    digests.append(digest)

            tags = []
            for tag in docker_data['RepoTags']:
                image_info = localanchore.parse_dockerimage_string(tag)
                if islocal:
                    image_info['registry'] = 'localbuild'
                    digests.append(image_info['registry'] + "/" + image_info['repo'] + "@local:" + imageId)
                fulltag = image_info['registry'] + "/" + image_info['repo'] + ":" + image_info['tag']
                tags.append(fulltag)
                
            # add the image w input anchore_analysis, as already analyzed
            logger.debug("ADDING/UPDATING IMAGE IN IMAGE IMPORT: " + str(imageId))
            ret_list = add_or_update_image(dbsession, userId, imageId, tags=tags, digests=digests, anchore_data=anchore_data)

            # return the new image:
            return_object = ret_list
            httpcode = 200
        except Exception as err:
            httpcode = 500
            raise err

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)


    return(return_object, httpcode)

def subscriptions(dbsession, request_inputs, subscriptionId=None, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        logger.debug("looking up subscription record: " + userId + " : " + str(subscriptionId))

        if method == 'GET':

            # set up the filter based on input
            dbfilter = {}
            if subscriptionId:
                dbfilter['subscription_id'] = subscriptionId

            records = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
            if not records:
                httpcode = 404
                raise Exception("subscriptions not found in DB")
            else:
                return_object = records
                httpcode = 200

        elif method == 'DELETE':
            if not subscriptionId:
                raise Exception("no subscriptionId passed in to delete")

            httpcode = 200
            return_object = True

            subscription_record = db_subscriptions.get(userId, subscriptionId, session=dbsession)
            if subscription_record:
                rc, httpcode = do_subscription_delete(userId, subscription_record, dbsession, force=True)
                if httpcode not in range(200,299):
                    raise Exception(str(rc))
            
            #dbfilter = {}
            #if subscriptionId:
            #    dbfilter['subscription_id'] = subscriptionId
            #rc = db_subscriptions.delete_byfilter(userId, session=dbsession, **dbfilter)
            #if not rc:
            #    raise Exception("DB delete failed")
            #else:
            #    httpcode = 200
            #    return_object = True

        elif method == 'POST':
            subscriptiondata = bodycontent

            subscription_key = subscription_type = None
            if 'subscription_key' in subscriptiondata:
                subscription_key=subscriptiondata['subscription_key']
            if 'subscription_type' in subscriptiondata:
                subscription_type=subscriptiondata['subscription_type']

            
            if not subscription_key or not subscription_type:
                httpcode = 500
                raise Exception("body does not contain both subscription_key and subscription_type")

            dbfilter = {'subscription_key':subscription_key, 'subscription_type':subscription_type}
            subscription_record = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
            if subscription_record:
                httpcode = 500
                raise Exception("subscription already exists in DB")

            rc = db_subscriptions.add(userId, subscription_key, subscription_type, subscriptiondata, session=dbsession)
            return_object = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
            httpcode = 200

        elif method == 'PUT':
            subscriptiondata = bodycontent

            subscription_key = subscription_type = None
            if 'subscription_key' in subscriptiondata:
                subscription_key=subscriptiondata['subscription_key']
            if 'subscription_type' in subscriptiondata:
                subscription_type=subscriptiondata['subscription_type']

            
            if not subscription_key or not subscription_type:
                httpcode = 500
                raise Exception("body does not contain both subscription_key and subscription_type")

            dbfilter = {'subscription_key':subscription_key, 'subscription_type':subscription_type}
            subscription_record = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
            if not subscription_record:
                httpcode = 404
                raise Exception("subscription to update does not exist in DB")

            rc = db_subscriptions.update(userId, subscription_key, subscription_type, subscriptiondata, session=dbsession)
            return_object = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
            httpcode = 200

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def events(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        jsondata = {}
        if bodycontent:
            try:
                jsondata = bodycontent
            except Exception as err:
                raise err
        
        if method == 'GET':
            records = db_eventlog.get_byfilter(session=dbsession, **jsondata)
            if not records:
                httpcode = 404
                raise Exception("events not found in DB")
            else:
                return_object = records
                httpcode = 200

        elif method == 'DELETE':
            rc = db_eventlog.delete_byfilter(session=dbsession, **jsondata)
            if not rc:
                raise Exception("DB delete failed")
            else:
                httpcode = 200
                return_object = True

        elif method == 'POST' or method == 'PUT':
            hostId = jsondata['hostId']
            service_name = jsondata['service_name']
            message = jsondata['message']
            level = jsondata['level']
            
            record = db_eventlog.get(hostId, service_name, message, level, session=dbsession)

            if method == 'PUT' and not record:
                httpcode = 404
                raise Exception("existing event not found to update")
            else:
                record.update(jsondata)
                rc = db_eventlog.update(hostId, service_name, message, level, jsondata, session=dbsession)
                if not rc:
                    raise Exception("DB update failed")
                else:
                    httpcode = 200
                    return_object = record

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def policies(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        jsondata = {}
        if bodycontent:
            try:
                jsondata = bodycontent
            except Exception as err:
                raise err
        
        if 'policyId' in jsondata:
            policyId = jsondata['policyId']
        else:
            policyId = None

        if 'active' in jsondata:
            active = jsondata['active']
        else:
            active = True

        logger.debug("looking up policy record: " + userId + " : " + str(policyId))

        if method == 'GET':

            # set up the filter based on input
            dbfilter = {}
            if policyId:
                dbfilter['policyId'] = policyId

            records = db_policybundle.get_byfilter(userId, session=dbsession, **dbfilter)
            if not records:
                httpcode = 404
                raise Exception("policy not found in DB")
            else:
                for record in records:
                    record['policybundle'] = {}
                    try:
                        policybundle =  archive_sys.get_document(userId, 'policy_bundles', record['policyId'])
                        if policybundle:
                            record['policybundle'] = policybundle
                    except:
                        pass

                return_object = records
                httpcode = 200

        elif method == 'DELETE':
            if not policyId:
                raise Exception ("must include 'policyId' in the json payload for this operation")

            httpcode = 200
            return_object = True

            policy_record = db_policybundle.get(userId, policyId, session=dbsession)
            if policy_record:
                if 'cleanup_evals' in params and params['cleanup_evals']:
                    cleanup_evals = True
                else:
                    cleanup_evals = False

                rc, httpcode = do_policy_delete(userId, policy_record, dbsession, force=True, cleanup_evals=cleanup_evals)
                if httpcode not in range(200,299):
                    raise Exception(str(rc))

            #rc = db_policybundle.delete(policyId, userId, session=dbsession)
            #if not rc:
            #    raise Exception("DB delete failed")
            #else:

            #    if 'cleanup_evals' in params and params['cleanup_evals']:
            #        dbfilter = {"policyId": policyId}
            #        eval_records = db_policyeval.tsget_byfilter(userId, session=dbsession, **dbfilter)
            #        for eval_record in eval_records:
            #            db_policyeval.delete_record(eval_record, session=dbsession)

            #    httpcode = 200
            #    return_object = True

        elif method == 'POST' or method == 'PUT':
            if not policyId:
                raise Exception ("must include 'policyId' in the json payload for this operation")

            record = db_policybundle.get(userId, policyId, session=dbsession)
            if method == 'PUT' and not record:
                httpcode = 404
                raise Exception("existing policyId not found to update")
            else:
                policybundle = jsondata['policybundle']
                rc =  archive_sys.put_document(userId, 'policy_bundles', policyId, policybundle)
                rc = db_policybundle.update(policyId, userId, active, jsondata, session=dbsession)
                record = db_policybundle.get(userId, policyId, session=dbsession)
                record['policybundle'] = jsondata['policybundle']

                if not rc:
                    raise Exception("DB update failed")
                else:
                    if active:
                        try:
                            rc = db_policybundle.set_active_policy(policyId, userId, session=dbsession)
                        except Exception as err:
                            httpcode = 500
                            raise Exception("could not set policy as active - exception: " + str(err))
                    httpcode = 200
                    return_object = record

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def evals(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        jsondata = {}
        if bodycontent:
            try:
                jsondata = bodycontent
            except Exception as err:
                raise err
        
        logger.debug("looking up eval record: " + userId)

        if method == 'GET':

            # set up the filter based on input
            dbfilter = {}
            for k in ['evalId', 'policyId', 'imageDigest', 'tag']:
                if k in jsondata:
                    dbfilter[k] = jsondata[k]

            # perform an interactive eval to get/install the latest
            try:
                logger.debug("performing eval refresh: " + str(dbfilter))
                imageDigest = dbfilter['imageDigest']
                if 'tag' in dbfilter:
                    evaltag = dbfilter['tag']
                else:
                    evaltag = None
                rc = perform_policy_evaluation(userId, imageDigest, dbsession, evaltag=evaltag)
            except Exception as err:
                logger.error("interactive eval failed, will return any in place evaluation records - exception: " + str(err))
                
            records = db_policyeval.tsget_byfilter(userId, session=dbsession, **dbfilter)
            if not records:
                httpcode = 404
                raise Exception("eval not found in DB")
            else:
                return_object = records
                httpcode = 200

        elif method == 'DELETE':
            dbfilter = {}
            for k in ['evalId', 'policyId', 'imageDigest', 'tag']:
                if k in jsondata:
                    dbfilter[k] = jsondata[k]

            if not dbfilter:
                raise Exception("not enough detail in body to find records to delete")

            rc = db_policyeval.delete_byfilter(userId, session=dbsession, **dbfilter)
            if not rc:
                raise Exception("DB delete failed")
            else:
                httpcode = 200
                return_object = True

        elif method == 'POST' or method == 'PUT':
            record = jsondata
            rc = db_policyeval.tsadd(record['policyId'], userId, record['imageDigest'], record['tag'], record['final_action'], {'policyeval':record['policyeval'], 'evalId':record['evalId']}, session=dbsession)
            if not rc:
                raise Exception("DB update failed")
            else:
                httpcode = 200
                return_object = record

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)
                
def users(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        user_records = db_users.get_all(session=dbsession)
        return_object = user_records
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def archive(dbsession, request_inputs, bucket, archiveid, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        if method == 'GET':
            try:
                return_object =  archive_sys.get(userId, bucket, archiveid)
                httpcode = 200
            except Exception as err:
                httpcode = 404
                raise err

        elif method == 'POST':
            try:
                jsondata = bodycontent
                rc =  archive_sys.put(userId, bucket, archiveid, jsondata)
                
                service_records = db_services.get_byname('catalog', session=dbsession)
                if service_records:
                    service_record = service_records[0]
                    resource_url = service_record['base_url'] + "/" + service_record['version'] + "/archive/" + bucket + "/" + archiveid
                else:
                    resource_url = "N/A"

                return_object = resource_url
                httpcode = 200
            except Exception as err:
                httpcode = 500
                raise err
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)
       
    return(return_object, httpcode)

def users_userId(dbsession, request_inputs, inuserId):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        if method == 'GET':
            try:
                user_record = db_users.get(inuserId, session=dbsession)
                return_object = user_record
                httpcode = 200
            except Exception as err:
                raise err

        elif method == 'DELETE':
            try:
                httpcode = 200
                return_object = True
            except Exception as err:
                raise err
   
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)
        
    return(return_object, httpcode)

def system(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        httpcode = 200
        return_object = ['services', 'registries']
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_services(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = []
    httpcode = 500

    try:
        service_records = db_services.get_all(session=dbsession)
        return_object = service_records
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_services_servicename(dbsession, request_inputs, inservicename):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = []
    httpcode = 500

    try:
        service_records = db_services.get_all(session=dbsession)
        for service_record in service_records:
            servicename = service_record['servicename']
            if servicename == inservicename:
                return_object.append(service_record)
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_services_servicename_hostId(dbsession, request_inputs, inservicename, inhostId):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = []
    httpcode = 500

    try:
        service_records = db_services.get_all(session=dbsession)
        for service_record in service_records:
            servicename = service_record['servicename']
            if servicename == inservicename:
                hostId = service_record['hostid']
                if hostId == inhostId:
                    if method == 'GET':
                        return_object = [service_record]
                        httpcode = 200
                    elif method == 'DELETE':
                        db_services.delete(hostId, servicename, session=dbsession)
                        return_object = True
                        httpcode = 200

        if not return_object:
            httpcode = 404
            raise Exception("servicename/hostId not found")
            
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_registries(dbsession, request_inputs, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = []
    httpcode = 500

    try:
        if method == 'GET':
            registry_records = db_registries.get_byuserId(userId, session=dbsession)
            try:
                refresh_registry_creds(registry_records, dbsession)
            except Exception as err:
                logger.warn("failed to refresh registry credentials - exception: " + str(err))

            return_object = registry_records
            httpcode = 200
        elif method == 'POST':
            registrydata = bodycontent
            if 'registry' in registrydata:
                registry=registrydata['registry']
            else:
                httpcode = 500
                raise Exception("body does not contain registry key")
            registry_records = db_registries.get(registry, userId, session=dbsession)
            if registry_records:
                httpcode = 500
                raise Exception("registry already exists in DB")

            localconfig = anchore_engine.configuration.localconfig.get_config()
            if (registrydata['registry_user'] == 'awsauto' or registrydata['registry_pass'] == 'awsauto') and not localconfig['allow_awsecr_iam_auto']:
                httpcode = 406
                raise Exception("'awsauto' is not enabled in service configuration")

            rc = db_registries.add(registry, userId, registrydata, session=dbsession)
            registry_records = db_registries.get(registry, userId, session=dbsession)
            try:
                refresh_registry_creds(registry_records, dbsession)
            except Exception as err:
                logger.warn("failed to refresh registry credentials - exception: " + str(err))

            return_object = registry_records
            httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def refresh_registry_creds(registry_records, dbsession):

    for registry_record in registry_records:

        #if registry_record['record_state_key'] in ['auth_failure'] and (int(time.time()) - int(registry_record['record_state_val']) < 30):
        #    logger.debug("SKIPPING "+str(registry_record['registry']) + " auth check: " + str(time.time()) + " : " + str(registry_record['record_state_val']))
        #    continue
        #else:
        #    try:
        #        logger.debug("PERFORMING "+str(registry_record['registry']) + " auth check: " + str(registry_record['record_state_val']) + " : " + str(int(time.time()) - int(registry_record['record_state_val'])))
        #    except:
        #        pass

        logger.debug("checking registry for up-to-date: " + str(registry_record['userId']) + " : " + str(registry_record['registry']) + " : " + str(registry_record['registry_type']))
        if 'registry_type' in registry_record and registry_record['registry_type'] in ['awsecr']:
            if registry_record['registry_type'] == 'awsecr':
                dorefresh = True
                if registry_record['registry_meta']:
                    ecr_data = json.loads(registry_record['registry_meta'])
                    expiresAt = ecr_data['expiresAt']
                    if time.time() < expiresAt:
                        dorefresh =False

                if dorefresh:
                    logger.debug("refreshing ecr registry: " + str(registry_record['userId']) + " : " + str(registry_record['registry']))
                    ecr_data = anchore_engine.auth.aws_ecr.refresh_ecr_credentials(registry_record['registry'], registry_record['registry_user'], registry_record['registry_pass'])
                    registry_record['registry_meta'] = json.dumps(ecr_data)
                    db_registries.update_record(registry_record, session=dbsession)

        #registry_status = anchore_engine.auth.docker_registry.ping_docker_registry(registry_record)
        #if not registry_status:
        #    if registry_record['record_state_key'] not in ['disabled']:
        #        registry_record['record_state_key'] = 'auth_failure'
        #        registry_record['record_state_val'] = str(int(time.time()))
        #        logger.debug("UPDATING: " + str(registry_record))
        #        db_registries.update_record(registry_record, session=dbsession)
        #elif registry_record['record_state_key'] not in ['active']:
        #    registry_record['record_state_key'] = 'active'
        #    registry_record['record_state_val'] = str(time.time())
        #    db_registries.update_record(registry_record, session=dbsession)

        logger.debug("registry up-to-date: " + str(registry_record['userId']) + " : " + str(registry_record['registry']) + " : " + str(registry_record['registry_type']))
    return(True)

def system_registries_registry(dbsession, request_inputs, registry, bodycontent={}):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = []
    httpcode = 500

    try:
        if method == 'GET':
            registry_records = db_registries.get(registry, userId, session=dbsession)
            if not registry_records:
                httpcode = 404
                raise Exception("registry not found in DB")
            
            try:
                refresh_registry_creds(registry_records, dbsession)
            except Exception as err:
                logger.warn("failed to refresh registry credentials - exception: " + str(err))

            return_object = registry_records
            httpcode = 200
        elif method == 'PUT':
            registrydata = bodycontent
            registry_record = db_registries.get(registry, userId, session=dbsession)
            if not registry_record:
                httpcode = 404
                raise Exception("could not find existing registry to update")
            
            localconfig = anchore_engine.configuration.localconfig.get_config()
            if (registrydata['registry_user'] == 'awsauto' or registrydata['registry_pass'] == 'awsauto') and not localconfig['allow_awsecr_iam_auto']:
                httpcode = 406
                raise Exception("'awsauto' is not enabled in service configuration")

            rc = db_registries.update(registry, userId, registrydata, session=dbsession)
            registry_records = db_registries.get(registry, userId, session=dbsession)
            try:
                refresh_registry_creds(registry_records, dbsession)
            except Exception as err:
                logger.warn("failed to refresh registry credentials - exception: " + str(err))

            return_object = registry_records
            httpcode = 200
        elif method == 'DELETE':
            if not registry:
                raise Exception("no registryId passed in to delete")

            httpcode = 200
            return_object = True
            
            registry_records = db_registries.get(registry, userId, session=dbsession)
            for registry_record in registry_records:
                rc, httpcode = do_registry_delete(userId, registry_record, dbsession, force=True)
                if httpcode not in range(200,299):
                    raise Exception(str(rc))
                    
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_subscriptions(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    return_object = {}
    httpcode = 500

    try:
        return_object = anchore_engine.services.common.subscription_types
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_prune_listresources(dbsession, request_inputs):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    allowed = anchore_engine.auth.anchore_resources.operation_access(userId, "system_prune_listresources", operation_access_scope={'allowed_userIds': anchore_engine.services.common.super_users})
    if not allowed:
        httpcode = 401
        return_object = anchore_engine.services.common.make_response_error("user has insufficient privs for this operation", in_httpcode=httpcode)
        return(return_object, httpcode)

    return_object = []
    httpcode = 500

    try:
        return_object = anchore_engine.services.common.resource_types
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def system_prune(dbsession, request_inputs, resourcetype, bodycontent=None):
    user_auth = request_inputs['auth']
    method = request_inputs['method']
    params = request_inputs['params']
    userId = request_inputs['userId']

    allowed = anchore_engine.auth.anchore_resources.operation_access(userId, "system_prune", operation_access_scope={'allowed_userIds': anchore_engine.services.common.super_users})
    if not allowed:
        httpcode = 401
        return_object = anchore_engine.services.common.make_response_error("user has insufficient privs for this operation", in_httpcode=httpcode)
        return(return_object, httpcode)

    if method == 'GET':
        return_object = {}
        httpcode = 500

        # param setup
        dangling = params['dangling']
        if params['olderthan']:
            olderthan = int(params['olderthan'])
        else:
            olderthan = None

        # get candidates
        try:
            return_object, httpcode = get_prune_candidates(resourcetype, dbsession, dangling=dangling, olderthan=olderthan)
        except Exception as err:
            return_object = anchore_engine.services.common.make_response_error("cannot get prune candidates - exception: " + str(err), in_httpcode=httpcode)

    elif method == 'POST':
        return_object = {}
        httpcode = 500
        
        # delete input candidates
        try:
            return_object, httpcode = delete_prune_candidates(resourcetype, bodycontent, dbsession)
        except Exception as err:
            return_object = anchore_engine.services.common.make_response_error("cannot delete prune candidates - exception: " + str(err), in_httpcode=httpcode)

    return(return_object, httpcode)

################################################################################

# helpers

def get_system_auth(dbsession):
    try:
        system_user = db_users.get('anchore-system', session=dbsession)
        system_userId = system_user['userId']
        system_password = system_user['password']
        system_user_auth = (system_userId, system_password)
    except Exception as err:
        logger.error("could not get system user auth record - exception: " + str(err))
        raise err

    return(system_user_auth)

def perform_vulnerability_scan(userId, imageDigest, dbsession, scantag=None, force_refresh=False):
    # prepare inputs
    try:
        system_user_auth = get_system_auth(dbsession)
        system_userId = system_user_auth[0]
        system_password = system_user_auth[1]

        localconfig = anchore_engine.configuration.localconfig.get_config()
        verify = localconfig['internal_ssl_verify']
        image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
        if not scantag:
            raise Exception("must supply a scantag")
    except Exception as err:
        raise Exception("could not gather/prepare all necessary inputs for vulnerability - exception: " + str(err))

    client = anchore_engine.clients.policy_engine.get_client(user=system_userId, password=system_password, verify_ssl=verify)

    imageIds = []
    for image_detail in image_record['image_detail']:
        imageId = image_detail['imageId']
        if imageId and imageId not in imageIds:
            imageIds.append(imageId)

    for imageId in imageIds:
        # do the image load, just in case it was missed in analyze...
        try:
            request = ImageIngressRequest()
            request.user_id = userId
            request.image_id = imageId
            request.fetch_url='catalog://'+str(userId)+'/analysis_data/'+str(imageDigest)
            logger.debug("policy engine request (image add): " + str(request))
            resp = client.ingress_image(request)
            logger.debug("policy engine response (image add): " + str(resp))
        except Exception as err:
            logger.warn("failed to add/check image")

        resp = client.get_image_vulnerabilities(user_id=userId, image_id=imageId, force_refresh=force_refresh)
        curr_vuln_result = resp.to_dict()

        last_vuln_result = {}
        try:
            last_vuln_result = archive_sys.get_document(userId, 'vulnerability_scan', scantag)
        except:
            pass

        # compare them
        doqueue = False

        vdiff = {}
        if last_vuln_result and curr_vuln_result:
            vdiff = anchore_utils.process_cve_status(old_cves_result=last_vuln_result['legacy_report'], new_cves_result=curr_vuln_result['legacy_report'])

        archive_sys.put_document(userId, 'vulnerability_scan', scantag, curr_vuln_result)

        try:
            if vdiff and (vdiff['updated'] or vdiff['added'] or vdiff['removed']):
                logger.debug("detected difference in vulnerability results (current vs last)")
                doqueue = True
            else:
                logger.debug("no difference in vulnerability scan")
        except Exception as err:
            logger.warn("unable to interpret vulnerability difference data - exception: " + str(err))

        # if different, set up a policy eval notification update
        if doqueue:
            logger.debug("queueing vulnerability update notification")
            inobj = {
                'userId': userId,
                'subscription_key': scantag,
                'notificationId': str(uuid.uuid4()),
                'diff_vulnerability_result': vdiff
            }
            qobj = simplequeue.enqueue(system_user_auth, 'vuln_update', inobj)
            logger.debug("queueing vulnerability notification: " + json.dumps(qobj, indent=4))        
    
    return(True)

def perform_policy_evaluation(userId, imageDigest, dbsession, evaltag=None):
    # prepare inputs
    try:
        system_user_auth = get_system_auth(dbsession)
        system_userId = system_user_auth[0]
        system_password = system_user_auth[1]

        localconfig = anchore_engine.configuration.localconfig.get_config()
        verify = localconfig['internal_ssl_verify']
        image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
        policy_record = db_policybundle.get_active_policy(userId, session=dbsession)
        policyId = policy_record['policyId']
        policy_bundle = archive_sys.get_document(userId, 'policy_bundles', policyId)

        if not evaltag:
            raise Exception("must supply an evaltag")

    except Exception as err:
        raise Exception("could not gather/prepare all necessary inputs for policy evaluation - exception: " + str(err))

    client = anchore_engine.clients.policy_engine.get_client(user=system_userId, password=system_password, verify_ssl=verify)

    imageId = None
    for image_detail in image_record['image_detail']:
        try:
            imageId = image_detail['imageId']
            break
        except:
            pass

    tagset = [evaltag]
    for fulltag in tagset:
        # do the image load, just in case it was missed in analyze...
        try:
            request = ImageIngressRequest()
            request.user_id = userId
            request.image_id = imageId
            request.fetch_url='catalog://'+str(userId)+'/analysis_data/'+str(imageDigest)
            logger.debug("policy engine request (image add): " + str(request))
            resp = client.ingress_image(request)
            logger.debug("policy engine response (image add): " + str(resp))
        except Exception as err:
            logger.warn("failed to add/check image")

        logger.debug("calling policy_engine: " + str(userId) + " : " + str(imageId) + " : " + str(fulltag))

        try:
            resp = client.check_user_image_inline(user_id=userId, image_id=imageId, tag=fulltag, bundle=policy_bundle)
        except Exception as err:
            raise err

        curr_final_action = resp.final_action.upper()
        
        # set up the newest evaluation
        evalId = hashlib.md5(':'.join([policyId, userId, imageDigest, fulltag, str(curr_final_action)])).hexdigest()
        curr_evaluation_record = anchore_engine.services.common.make_eval_record(userId, evalId, policyId, imageDigest, fulltag, curr_final_action, "policy_evaluations/"+evalId)
        curr_evaluation_result = resp.to_dict()

        # get last image evaluation
        last_evaluation_record = db_policyeval.tsget_latest(userId, imageDigest, fulltag, session=dbsession)
        last_evaluation_result = {}
        last_final_action = None
        if last_evaluation_record:
            last_evaluation_result = archive_sys.get_document(userId, 'policy_evaluations', last_evaluation_record['evalId'])
            last_final_action = last_evaluation_result['final_action'].upper()

        # store the newest evaluation
        archive_sys.put_document(userId, 'policy_evaluations', evalId, curr_evaluation_result)
        db_policyeval.tsadd(policyId, userId, imageDigest, fulltag, curr_final_action, curr_evaluation_record, session=dbsession)

        # compare last with newest evaluation
        doqueue = False
        if last_evaluation_result and curr_evaluation_result:
            if last_final_action != curr_final_action:
                logger.debug("detected difference in policy eval results (current vs last)")
                doqueue = True
            else:
                logger.debug("no difference in policy evaluation")

        # if different, set up a policy eval notification update
        if doqueue:
            logger.debug("queueing policy eval notification")
            inobj = {
                'userId': userId,
                'subscription_key': fulltag,
                'notificationId': str(uuid.uuid4()),
                'last_eval': last_evaluation_result,
                'curr_eval': curr_evaluation_result,
            }
            qobj = simplequeue.enqueue(system_user_auth, 'policy_eval', inobj)
            logger.debug("queueing eval notification: " + json.dumps(qobj, indent=4))

        # done
            
    return(True)

def add_or_update_image(dbsession, userId, imageId, tags=[], digests=[], anchore_data=None, dockerfile=None):
    ret = []

    logger.debug("adding based on input tags/digests for imageId ("+str(imageId)+") tags="+str(tags)+" digests="+str(digests))

    # input to this section is imageId, list of digests and list of tags (full dig/tag strings with reg/repo[:@]bleh)
    image_ids = {}
    for d in digests:
        image_info = localanchore.parse_dockerimage_string(d)
        registry = image_info['registry']
        repo = image_info['repo']
        digest = image_info['digest']

        if registry not in image_ids:
            image_ids[registry] = {}
        if repo not in image_ids[registry]:
            image_ids[registry][repo] = {'digests':[], 'tags':[], 'imageId':imageId}
        if digest not in image_ids[registry][repo]['digests']:
            image_ids[registry][repo]['digests'].append(digest)

    for d in tags:
        image_info = localanchore.parse_dockerimage_string(d)
        registry = image_info['registry']
        repo = image_info['repo']
        digest = image_info['tag']

        if registry not in image_ids:
            image_ids[registry] = {}
        if repo not in image_ids[registry]:
            image_ids[registry][repo] = {'digests':[], 'tags':[], 'imageId':imageId}
        if digest not in image_ids[registry][repo]['tags']:
            image_ids[registry][repo]['tags'].append(digest)

    if not dockerfile and anchore_data:
        a = anchore_data[0]
        try:
            dockerfile = a['image']['imagedata']['image_report']['dockerfile_contents'].encode('base64')
        except Exception as err:
            logger.warn("could not extract dockerfile_contents from input anchore_data - exception: " + str(err))
            dockerfile = None

    logger.debug("rationalized input for imageId ("+str(imageId)+"): " + json.dumps(image_ids, indent=4))

    addlist = {}
    for registry in image_ids.keys():
        for repo in image_ids[registry].keys():
            imageId = image_ids[registry][repo]['imageId']
            digests = image_ids[registry][repo]['digests']
            tags = image_ids[registry][repo]['tags']
            for d in digests:
                fulldigest = registry + "/" + repo + "@" + d
                for t in tags:
                    fulltag = registry + "/" + repo + ":" + t
                    new_image_record = anchore_engine.services.common.make_image_record(userId, 'docker', None, image_metadata={'tag':fulltag, 'digest':fulldigest, 'imageId':imageId, 'dockerfile':dockerfile}, registry_lookup=False, registry_creds=(None, None))
                    imageDigest = new_image_record['imageDigest']
                    image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
                    if not image_record:
                        new_image_record['image_status'] = taskstate.init_state('image_status', None)
                        if anchore_data:
                            rc =  archive_sys.put_document(userId, 'analysis_data', imageDigest, anchore_data)

                            #image_content_metadata = {'anchore_image_report': anchore_data[0]['image']['imagedata']['image_report'], 'anchore_distro_meta': anchore_data[0]['image']['imagedata']['analysis_report']['analyzer_meta']['analyzer_meta']['base']}
                            #rc = archive_sys.put_document(userId, 'image_content_metadata', imageDigest, image_content_metadata)
                            image_content_data = {}
                            for content_type in anchore_engine.services.common.image_content_types:
                                try:
                                    image_content_data[content_type] = anchore_engine.services.common.extract_analyzer_content(anchore_data, content_type)
                                except:
                                    image_content_data[content_type] = {}
                            if image_content_data:
                                logger.debug("adding image content data to archive")
                                rc = archive_sys.put_document(userId, 'image_content_data', imageDigest, image_content_data)

                            image_summary_data = {}
                            try:
                                image_summary_data = anchore_engine.services.common.extract_analyzer_content(anchore_data, 'metadata')
                            except:
                                image_summary_data = {}
                            if image_summary_data:
                                logger.debug("adding image summary data to archive")
                                rc = archive_sys.put_document(userId, 'image_summary_data', imageDigest, image_summary_data)

                            new_image_record['analysis_status'] = taskstate.complete_state('analyze')
                        else:
                            new_image_record['analysis_status'] = taskstate.init_state('analyze', None)

                        rc = db_catalog_image.add_record(new_image_record, session=dbsession)
                        image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)
                    else:
                        new_image_detail = anchore_engine.services.common.clean_docker_image_details_for_update(new_image_record['image_detail'])
                        if 'imageId' not in new_image_detail or not new_image_detail['imageId']:
                            for image_detail in image_record['image_detail']:
                                if 'imageId' in image_detail and image_detail['imageId']:
                                    for new_id in new_image_detail:
                                        new_id['imageId'] = image_detail['imageId']
                                    break

                        rc = db_catalog_image.update_record_image_detail(image_record, new_image_detail, session=dbsession)
                        image_record = db_catalog_image.get(imageDigest, userId, session=dbsession)

                    addlist[imageDigest] = image_record

    logger.debug("final dict of image(s) to add: " + json.dumps(addlist, indent=4))
    for imageDigest in addlist.keys():
        ret.append(addlist[imageDigest])

    logger.debug("returning: " + json.dumps(ret, indent=4))
    return(ret)

def delete_prune_candidates(resourcetype, bodycontent, dbsession, resource_user=None):
    return_object = {}
    httpcode = 500

    try:
        if not bodycontent:
            httpcode = 404
            raise Exception("no body content passed to POST")
        else:
            resource_types = anchore_engine.services.common.resource_types
            if resourcetype == 'all':
                types_to_run = resource_types
            else:
                types_to_run = [resourcetype]

            jsondata = bodycontent
            pruned_resources = []
            for resource in jsondata['prune_candidates']:
                logger.debug("considering resource: " + str(resource))
                httpcode = 500

                skipresource = True
                try:
                    if resource_user:
                        if resource['userId'] == resource_user:
                            skipresource = False
                    else:
                        skipresource = False
                except:
                    pass

                input_resourcetype = resource['resourcetype']
                if input_resourcetype not in types_to_run:
                    skipresource = True

                if skipresource:
                    continue

                ruserId = resource['userId']

                if input_resourcetype == 'images':
                    imageDigest = resource['resource_ids']['imageDigest']
                    image_record = db_catalog_image.get(imageDigest, ruserId, session=dbsession)
                    if image_record:
                        rc, httpcode = do_image_delete(ruserId, image_record, dbsession, force=True)
                        if httpcode in range(200,299):
                            pruned_resources.append(resource)

                elif input_resourcetype == 'policies':
                    policyId = resource['resource_ids']['policyId']
                    policy_record = db_policybundle.get(ruserId, policyId, session=dbsession)
                    if policy_record:
                        rc, httpcode = do_policy_delete(ruserId, policy_record, dbsession, force=True)
                        if httpcode in range(200,299):
                            pruned_resources.append(resource)

                elif input_resourcetype == 'subscriptions':
                    subscriptionId = resource['resource_ids']['subscription_id']
                    subscription_record = db_subscriptions.get(ruserId, subscriptionId, session=dbsession)
                    if subscription_record:
                        rc, httpcode = do_subscription_delete(ruserId, subscription_record, dbsession, force=True)
                        if httpcode in range(200,299):
                            pruned_resources.append(resource)
                        else:
                            logger.warn("prune delete failed: " + str(httpcode) + " : " + str(rc))

                elif input_resourcetype == 'evaluations':
                    dbfilter = {'evalId': resource['resource_ids']['evalId']}
                    eval_records = db_policyeval.tsget_byfilter(ruserId, session=dbsession, **dbfilter)
                    if eval_records:
                        for eval_record in eval_records:
                            rc, httpcode = do_evaluation_delete(ruserId, eval_record, dbsession, force=True)
                            if httpcode in range(200,299):
                                pruned_resources.append(resource)
                            else:
                                logger.warn("prune delete failed: " + str(httpcode) + " : " + str(rc))
                elif input_resourcetype == 'users':
                    duserId = resource['resource_ids']['userId']
                    user_record = db_users.get(duserId, session=dbsession)
                    if user_record:
                        rc, httpcode = do_user_delete(ruserId, user_record, dbsession, force=True)
                        if httpcode in range(200,299):
                            pruned_resources.append(resource)
                        else:
                            logger.warn("prune delete failed: " + str(httpcode) + " : " + str(rc))
                elif input_resourcetype == 'archive':
                    bucket = resource['resource_ids']['bucket']
                    archiveId = resource['resource_ids']['archiveId']
                    archive_document = db_archivedocument.exists(ruserId, bucket, archiveId, session=dbsession)
                    if archive_document:
                        rc, httpcode = do_archive_delete(ruserId, archive_document, dbsession, force=True)
                        if httpcode in range(200, 299):
                            pruned_resources.append(resource)
                        else:
                            logger.warn("prune delete failed: " + str(httpcode) + " : " + str(rc))

                elif input_resourcetype == 'registries':
                    registryId = resource['resource_ids']['registry']
                    registry_records = db_registries.get(registryId, ruserId, session=dbsession)
                    if registry_records:
                        for registry_record in registry_records:
                            rc, httpcode = do_registry_delete(ruserId, registry_record, dbsession, force=True)
                            if httpcode in range(200,299):
                                pruned_resources.append(resource)
                            else:
                                logger.warn("prune delete failed: " + str(httpcode) + " : " + str(rc))

            return_object['pruned_resources'] = pruned_resources
            httpcode = 200

    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def get_prune_candidates(resourcetype, dbsession, dangling=True, olderthan=None, resource_user=None):
    return_object = {}
    prune_candidates = []
    httpcode = 500

    try:
        # get all the things
        user_records = {}
        records = db_users.get_all(session=dbsession)
        for record in records:
            user_records[record['userId']] = record
        user_ids = user_records.keys()

        image_records = {}
        fulltags = []
        records = db_catalog_image.get_all(session=dbsession)
        for record in records:
            image_records[record['imageDigest']] = record
            for image_detail in record['image_detail']:
                fulltag = image_detail['registry'] + "/" + image_detail['repo'] + ":" + image_detail['tag']
                if fulltag not in fulltags:
                    fulltags.append(fulltag)
        image_digests = image_records.keys()

        policy_records = {}
        records = db_policybundle.get_all(session=dbsession)
        for record in records:
            policy_records[record['policyId']] = record
        policy_ids = policy_records.keys()

        eval_records = {}
        records = db_policyeval.get_all(session=dbsession)
        for record in records:
            eval_records[record['evalId']] = record
        eval_ids = eval_records.keys()

    except Exception as err:
        httpcode = 500
        raise Exception("failed to gather full DB records for pruning run")

    try:
        resource_types = anchore_engine.services.common.resource_types

        if resourcetype == 'all':
            types_to_run = resource_types
        else:
            types_to_run = [resourcetype]


        for resourcetype in types_to_run:

            if resourcetype not in resource_types:
                httpcode = 404
                raise Exception("input resource_type ("+str(resourcetype)+") is not in list of available resource_types ("+str(resource_types)+")")

            if resourcetype == 'users':
                records = user_records.values()
                for record in records:
                    dangling_candidate = False
                    prune_candidate = True
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    if record['userId'] in ['admin', 'anchore-system']:
                        continue

                    if not record['active']:
                        dangling_candidate = True
                        dangling_reason = "user is marked as inactive"
                    else:
                        prune_candidate = False

                    if prune_candidate:
                        result_keys = ['userId', 'created_at']
                        record_idkeys = ['userId']
                        el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                        for k in result_keys:
                            el[k] = record[k]
                        for k in record_idkeys:
                            el['resource_ids'][k] = record[k]

                        if dangling:
                            if dangling_candidate and (not olderthan or record_age > olderthan):
                                prune_candidates.append(el)
                        elif olderthan and record_age > olderthan:
                            el['reason'] = "record age is older than that specified"
                            prune_candidates.append(el)                        

                httpcode = 200
            elif resourcetype == 'registries':
                records = db_registries.get_all(session=dbsession)
                for record in records:
                    dangling_candidate = False
                    prune_candidate = True
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    registry_id = record['registry']
                    registry_userId = record['userId']

                    if registry_userId not in user_ids:
                        logger.debug("candidate registry - registry_userId not in users")
                        dangling_candidate = True
                        dangling_reason = "user id owning registry is not a valid user"
                    else:
                        pass


                    result_keys = ['userId', 'created_at']
                    record_idkeys = ['registry']
                    el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                    for k in result_keys:
                        el[k] = record[k]
                    for k in record_idkeys:
                        el['resource_ids'][k] = record[k]

                    if dangling:
                        if dangling_candidate and (not olderthan or record_age > olderthan):
                            prune_candidates.append(el)
                    elif olderthan and record_age > olderthan:
                        el['reason'] = "record age is older than that specified"
                        prune_candidates.append(el)                        

                httpcode = 200

            elif resourcetype == 'images':
                records = image_records.values()
                for record in records:
                    dangling_candidate = False
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])
                    for image_detail in record['image_detail']:
                        tag_record_age = int(time.time() - image_detail['created_at'])
                        if tag_record_age > record_age:
                            record_age = tag_record_age

                    if record['userId'] not in user_ids:
                        dangling_candidate = True

                    result_keys = ['userId', 'created_at']
                    record_idkeys = ['imageDigest']
                    el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                    for k in result_keys:
                        el[k] = record[k]
                    for k in record_idkeys:
                        el['resource_ids'][k] = record[k]

                    if dangling:
                        if dangling_candidate and (not olderthan or record_age > olderthan):
                            prune_candidates.append(el)
                    elif olderthan and record_age > olderthan:
                        el['reason'] = "record age is older than that specified"
                        prune_candidates.append(el)                        

            elif resourcetype == 'policies':
                records = policy_records.values()
                for record in records:
                    # dangling_candidate is set if the resource is determined to have no supporting references.  
                    # prune_candidate is unset if the resource should be held, even if supporting resources cannot 
                    # be determined.

                    dangling_candidate = False
                    prune_candidate = True
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    policy_id = record['policyId']
                    policy_userId = record['userId']
                    
                    if record['active']:
                        dangling_candidate = False
                        prune_candidate = False
                    elif record['userId'] not in user_ids:
                        dangling_candidate = True
                        dangling_reason = "record userId is not a valid user"
                    else:
                        dbfilter = {'policyId': policy_id}
                        user_eval_records = db_policyeval.tsget_byfilter(policy_userId, session=dbsession, **dbfilter)
                        if not user_eval_records:
                            dangling_reason = "no evaluations match policyId"
                            dangling_candidate = True

                    if prune_candidate:
                        result_keys = ['userId', 'created_at']
                        record_idkeys = ['policyId']
                        el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                        for k in result_keys:
                            el[k] = record[k]
                        for k in record_idkeys:
                            el['resource_ids'][k] = record[k]

                        if dangling:
                            if dangling_candidate and (not olderthan or record_age > olderthan):
                                prune_candidates.append(el)
                        elif olderthan and record_age > olderthan:
                            el['reason'] = "record age is older than that specified"
                            prune_candidates.append(el)                        

            elif resourcetype == 'subscriptions':
                records = db_subscriptions.get_all(session=dbsession)
                for record in records:
                    dangling_candidate = False
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    subscription_key = record['subscription_key']

                    if record['userId'] not in user_ids:
                        dangling_candidate = True
                        dangling_reason = "record userId is not a valid user"
                    else:
                        if subscription_key not in fulltags:
                            dangling_candidate = True
                            dangling_reason = "subscription_key (image tag) is not found against any image in DB"

                    result_keys = ['userId', 'created_at']
                    record_idkeys = ['subscription_id', 'subscription_type', 'subscription_key']
                    el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                    for k in result_keys:
                        el[k] = record[k]
                    for k in record_idkeys:
                        el['resource_ids'][k] = record[k]

                    if dangling:
                        if dangling_candidate and (not olderthan or record_age > olderthan):
                            prune_candidates.append(el)
                    elif olderthan and record_age > olderthan:
                        el['reason'] = "record age is older than that specified"
                        prune_candidates.append(el)

            elif resourcetype == 'archive':
                bucket_types = anchore_engine.services.common.bucket_types

                records = db_archivedocument.list_all(session=dbsession)
                for record in records:
                    dangling_candidate = False
                    prune_candidate = True
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    archive_bucket = record['bucket']
                    archive_id = record['archiveId']

                    if archive_bucket not in bucket_types:
                        dangling_candidate = True
                        dangling_candidate = "bucket is not in known bucket types"
                    else:
                        #TODO need to change logic to use prune_candidate check
                        if archive_bucket == 'analysis_data':
                            if archive_id not in image_digests:
                                dangling_candidate = True
                                dangling_reason = "no image digest matches archive id"
                            else:
                                prune_candidate = False
                        elif archive_bucket == 'query_data':
                            if archive_id not in image_digests:
                                dangling_candidate = True
                                dangling_reason = "no image digest matches archive id"
                            else:
                                prune_candidate = False
                        elif archive_bucket == 'policy_bundles':
                            if archive_id not in policy_ids:
                                dangling_candidate = True
                                dangling_reason = "no policy id matches archive id"
                            else:
                                prune_candidate = False
                        elif archive_bucket == 'policy_evaluations':
                            if archive_id not in eval_ids:
                                dangling_candidate = True
                                dangling_reason = "no eval id matches archive id"
                            else:
                                prune_candidate = False
                        elif archive_bucket == 'vulnerability_scan': 
                            if archive_id not in fulltags:
                                dangling_reason = "no image tag matches archive id"
                                dangling_candidate = True
                            else:
                                prune_candidate = False

                    if prune_candidate:
                        result_keys = ['userId', 'created_at']
                        record_idkeys = ['bucket', 'archiveId']
                        el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                        for k in result_keys:
                            el[k] = record[k]
                        for k in record_idkeys:
                            el['resource_ids'][k] = record[k]

                        if dangling:
                            if dangling_candidate and (not olderthan or record_age > olderthan):
                                prune_candidates.append(el)
                        elif olderthan and record_age > olderthan:
                            el['reason'] = "record age is older than that specified"
                            prune_candidates.append(el)                        

            elif resourcetype == 'evaluations':
                #records = db_subscriptions.get_all(session=dbsession)
                records = eval_records.values()
                for record in records:
                    dangling_candidate = False
                    dangling_reason = "not_set"
                    record_age = int(time.time() - record['created_at'])

                    if record['userId'] not in user_ids:
                        dangling_candidate = True
                        dangling_reason = "record userId is not a valid user"
                    else:
                        if record['policyId'] not in policy_ids:
                            dangling_candidate = True
                            dangling_reason = "eval record has policy ID that is not in DB"
                        elif record['imageDigest'] not in image_digests:
                            dangling_candidate = True
                            dangling_reason = "eval record has image digest that is not in DB"
                        elif record['tag'] not in fulltags:
                            dangling_candidate = True
                            dangling_reason = "eval record has image tag that is not in DB"

                    result_keys = ['userId', 'created_at']
                    record_idkeys = ['evalId', 'policyId']
                    el = {'reason': dangling_reason, 'resourcetype': resourcetype, 'resource_ids': {}}
                    for k in result_keys:
                        el[k] = record[k]
                    for k in record_idkeys:
                        el['resource_ids'][k] = record[k]

                    if dangling:
                        if dangling_candidate and (not olderthan or record_age > olderthan):
                            prune_candidates.append(el)
                    elif olderthan and record_age > olderthan:
                        el['reason'] = "record age is older than that specified"
                        prune_candidates.append(el)

        if resource_user:
            filtered_prune_candidates = []
            for prune_candidate in prune_candidates:
                try:
                    if resource_user == prune_candidate['userId']:
                        filtered_prune_candidates.append(prune_candidate)
                except:
                    pass

            prune_candidates = filtered_prune_candidates

        return_object = {
            'prune_candidates': prune_candidates
        }
        httpcode = 200
    except Exception as err:
        return_object = anchore_engine.services.common.make_response_error(err, in_httpcode=httpcode)

    return(return_object, httpcode)

def do_image_delete(userId, image_record, dbsession, force=False):
    return_object = False
    httpcode = 500

    try:
        imageDigest = image_record['imageDigest']
        dodelete = False
        msgdelete = "could not make it though delete checks"
        image_ids = []

        if force:
            dodelete = True
        else:
            # do some checking before delete
            try:
                # check one - don't delete anything that is being analyzed
                if image_record['analysis_status'] == taskstate.working_state('analyze'):
                    raise Exception("cannot delete image that is being analyzed")

                # check two - don't delete anything that is the latest of any of its tags, and has an active subscription
                for image_detail in image_record['image_detail']:
                    fulltag = image_detail['registry'] + "/" + image_detail['repo'] + ":" + image_detail['tag']

                    if 'imageId' in image_detail and image_detail['imageId']:
                        image_ids.append(image_detail['imageId'])

                    dbfilter = {}
                    dbfilter['registry'] = image_detail['registry']
                    dbfilter['repo'] = image_detail['repo']
                    dbfilter['tag'] = image_detail['tag']

                    latest_image_records = db_catalog_image.get_byimagefilter(userId, 'docker', dbfilter=dbfilter, onlylatest=True, session=dbsession)
                    for latest_image_record in latest_image_records:
                        if latest_image_record['imageDigest'] == image_record['imageDigest']:
                            dbfilter = {}
                            dbfilter['subscription_key'] = fulltag
                            subscription_records = db_subscriptions.get_byfilter(userId, session=dbsession, **dbfilter)
                            for subscription_record in subscription_records:
                                if subscription_record['active']:
                                    raise Exception("cannot delete image that is the latest of its tags, and has active subscription")

                # checked out - do the delete
                dodelete = True

            except Exception as err:
                msgdelete = str(err)
                dodelete = False

        if dodelete:
            logger.debug("DELETEing image from catalog")
            rc = db_catalog_image.delete(imageDigest, userId, session=dbsession)

            for bucket in ['analysis_data', 'query_data', 'image_content_data', 'image_summary_data']:
                logger.debug("DELETEing image from archive " + str(bucket) + "/" + str(imageDigest))
                rc = archive_sys.delete(userId, bucket, imageDigest)

            #logger.debug("DELETEing image from archive query_data")
            #rc = archive_sys.delete(userId, 'query_data', imageDigest)
            #logger.debug("DELETEing image from archive image_content_metadata")
            #rc = archive_sys.delete(userId, 'image_content_metadata', imageDigest)

            logger.debug("DELETEing image from policy_engine")
            # prepare inputs
            try:
                system_user_auth = get_system_auth(dbsession)
                system_userId = system_user_auth[0]
                system_password = system_user_auth[1]

                localconfig = anchore_engine.configuration.localconfig.get_config()
                verify = localconfig['internal_ssl_verify']

                client = anchore_engine.clients.policy_engine.get_client(user=system_userId, password=system_password, verify_ssl=verify)
                for img_id in set(image_ids):
                    logger.debug("DELETING image from policy engine userId = {} imageId = {}".format(userId, img_id))
                    rc = client.delete_image(user_id=userId, image_id=img_id)
            except:
                logger.exception('Failed deleting image from policy engine')
                raise

            return_object = True
            httpcode = 200
        else:
            httpcode = 409
            raise Exception(msgdelete)
    except Exception as err:
        logger.warn("DELETE failed - exception: " + str(err))
        return_object = str(err)

    return(return_object, httpcode)

def do_subscription_delete(userId, subscription_record, dbsession, force=False):
    return_object = False
    httpcode = 500

    try:
        dbfilter = {'subscription_id': subscription_record['subscription_id']}
        rc = db_subscriptions.delete_byfilter(userId, remove=True, session=dbsession, **dbfilter)
        if not rc:
            raise Exception("DB delete failed")

        return_object = True
        httpcode = 200
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)

def do_policy_delete(userId, policy_record, dbsession, cleanup_evals=False, force=False):
    return_object = False
    httpcode = 500

    try:
        policyId = policy_record['policyId']

        rc = db_policybundle.delete(policyId, userId, session=dbsession)
        if not rc:
            httpcode = 500
            raise Exception("DB delete of policyId ("+str(policyId)+") failed")
        else:
            if cleanup_evals:
                dbfilter = {"policyId": policyId}
                eval_records = db_policyeval.tsget_byfilter(userId, session=dbsession, **dbfilter)
                for eval_record in eval_records:
                    db_policyeval.delete_record(eval_record, session=dbsession)

        return_object = True
        httpcode = 200
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)

def do_evaluation_delete(userId, eval_record, dbsession, force=False):
    return_object = False
    httpcode = 500

    try:
        rc = db_policyeval.delete_record(eval_record, session=dbsession)
        if not rc:
            raise Exception("DB update failed")

        httpcode = 200
        return_object = True
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)
        
def do_archive_delete(userId, archive_document, session, force=False):
    return_object = False
    httpcode = 500
    
    try:        
        rc = archive_sys.delete(userId, archive_document['bucket'], archive_document['archiveId'])
        if not rc:
            raise Exception("archive delete failed")

        return_object = True
        httpcode = 200
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)

def do_user_delete(userId, user_record, dbsession, force=False):
    return_object = False
    httpcode = 500

    try:
        userId = user_record['userId']
        rc = db_users.delete(userId, session=dbsession)
        if not rc:
            raise Exception("DB delete failed")

        return_object = True
        httpcode = 200
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)

def do_registry_delete(userId, registry_record, dbsession, force=False):
    return_object = False
    httpcode = 500

    try:
        registryId = registry_record['registry']
        rc = db_registries.delete(registryId, userId, session=dbsession)
        if not rc:
            raise Exception("DB delete failed")

        return_object = True
        httpcode = 200
    except Exception as err:
        return_object = str(err)

    return(return_object, httpcode)



################################################################################

