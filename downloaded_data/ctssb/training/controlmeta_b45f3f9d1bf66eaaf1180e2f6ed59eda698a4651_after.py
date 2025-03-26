import requests
import json
import tempfile 

class  Media:
    def __init__(self, document_id, document_url):
        self.document_id = document_id
        self.document_url = document_url

def new_media_result(rv):
    return Media(rv['media_id'], rv['media_url'])


class  Meta:
    def __init__(self, media_id, media_url, meta_id, meta_url, meta_type, meta_content):
        self.media_id = media_id
        self.media_url = media_url
        self.meta_id = meta_id
        self.url = meta_url
        self.type = meta_type
        self.content = meta_content

def new_meta_result(rv):
        return Meta(
            rv['media_id'],
            rv['media_url'],
            rv['meta_id'],
            rv['meta_url'],
            rv['meta_type'],
            rv['meta_content'])

class  Task:
    def __init__(self, task_id, status, parameters, task_type):
        self.status = status
        self.parameters = parameters
        self.id = task_id
        self.task_type = task_type


    def __repr__(self):
        return "<Task id:'%r', type:'%r',  status:'%r', parameters:'%r'>" % \
            (self.id, self.task_type, self.status, self.parameters)

def new_task_result(rv):
    if not rv: 
        raise ClientException(
            None, 
            "Attempt to create task instance from empty dictionary")

    return Task(
        rv['task_id'],
        rv['status'],
        rv['parameters'],
        rv['task_type']
        )



    
class ClientException(Exception):

    httpcode=None
    def __init__(self, httpcode, message):
        self.httpcode=httpcode
        if httpcode:
            self.value = "HTTP return code %s: %s" % (str(httpcode), message)
        else:
            self.value = message
        
    def __str__(self):
        return repr(self.value)

    
class  ControlMetaClient:
    JSON_HEADERS = {'content-type': 'application/json'}

    def __init__(self,
                 base_url=None,
                 auth=None):
        if base_url and not base_url.endswith("/"):
            base_url = base_url + "/"

        self.base_url = base_url
        self.auth = auth

    def process(self, function,  url, payload, expected_status, error_message, null_allowed=True, null_json_allowed=True):

        if not payload:
            payload = {}

        raw_response  = function(
                url,
                auth = self.auth,
                data = json.dumps(payload),
                headers = self.JSON_HEADERS)

        status_code = raw_response.status_code
        if status_code != expected_status:
            raise ClientException(
                    status_code, 
                    error_message)

        # If there was no content, then return none

        if not raw_response.text and  null_allowed:
            return None
        elif not raw_response.text:
            raise ClientException(status_code, "Illegal null response for %s request %s detected." %\
                                      (function, url))

        # Since there was a response we will assume it was
        # json and interpret it as such, and return the
        # interpretation as a collection (or list, or whatever :-)

        json_retval = json.loads(raw_response.text)
        if not json_retval and not null_json_allowed:
            raise ClientException(status_code, "Illegal empty json response for %s request %s detected." %\
                                      (function, url))
        return json_retval

    

    def post(self, url, payload, expected_status, error_message, null_allowed=True, null_json_allowed=True):
        return self.process(requests.post,
                            url, payload, expected_status, error_message, null_allowed=null_allowed, null_json_allowed=null_json_allowed)

    def get(self, url,  expected_status, error_message):
        return self.process(requests.get,
                            url, None, expected_status, error_message, null_allowed=True)

    def delete(self, url, payload, expected_status, error_message):
        return self.process(requests.delete, 
                            url, payload, expected_status, error_message,  null_allowed=True)

    def all_tasks(self):
        url = "%stask" %(self.base_url)
        task_list = self.get(url,  200, "Unable to get task list")
        return map(new_task_result, task_list)
        
    def upload_task(self, type, parameters):
        tasktypepath = "task/type/%s" % type
        url = "%s%s" %(self.base_url, tasktypepath)
        task  = self.post(url, parameters, 201, "Unable to upload task")
        return new_task_result(task)


    def pick_task(self, type, agent_id):
        parameters = {'agentId':agent_id}
        url = "%stask/waiting/type/%s/pick" %(self.base_url, type)
        error_message = "Unable to pick task of type %s for agent %s"%(type, agent_id)
        task = self.post(url, parameters, 200, error_message, null_allowed=False, null_json_allowed=False)
        print "task = ", task
        return new_task_result(task)
        
    def declare_task_done(self, task_id, agent_id):
        url="%stask/id/%s/done" %(self.base_url, task_id)
        payload={'agentId': agent_id}
        error_message="Unable to declare task " + str(task_id) + " as done."
        task = self.post(url, payload,  200, error_message)
        return new_task_result(task)


    def supplement_meta_with_media(self, media_id, meta_id):
        url = "%smedia/id/%s/supplement-meta/%s" %(self.base_url, media_id, meta_id)
        error_message = "Unable to  supplement metadata with with id  "\
            + str(meta_id) + \
            " with media with id  " + \
            str(media_id)
        result = self.post(url, {},  200, error_message)
        return new_media_result(result)



    def upload_metadata_for_media(self, media_id, metadata_type, metadata):
        url = "%smedia/id/%s/metatype/%s" %(self.base_url, media_id, metadata_type)
        payload = json.dumps(metadata)
        error_message = "Unable to  upload metadata of type  "\
            + str(metadata_type ) + \
            " to media with id " + \
            media_id
        meta = self.post(url, payload,  200, error_message)
        return new_meta_result(meta)

    def upload_metadata(self, type, data):
        url="%s/media/metatype/%s" %(self.base_url, type)
        error_message="Unable to create naked  metadata instance."
        raw_response = self.post(url, data, 200, error_message)
        jrv = json.loads(raw_response.text)
        return new_meta_result(jrv)

    def upload_media_from_file(self, type, filepath):
        url="%smedia/" %(self.base_url)
        with open(filepath, 'r') as content_file:
            content = content_file.read()
            return self.upload_media(type, content)

    def get_media(self, id):
        url="%smedia/id/%s" %(self.base_url, str(id))
        result = requests.get(url, auth=self.auth)
        content_type = result.headers['Content-Type']
        # XXX What is it called?
        return (result.content, content_type)

    def delete_media(self, id):
        url="%smedia/id/%s" %(self.base_url, str(id))
        result = requests.delete(url, auth=self.auth)
        if result.status_code != 204:
            raise ClientException("Could not delete media with id " + str(id))

    def exists_media(self, id):
        url="%smedia/id/%s/exists" %(self.base_url, str(id))
        result = requests.get(url, auth=self.auth)
        content_type = result.headers['Content-Type']
        return (result.status_code == 200)



    def  get_new_tempfile_name(self):
        filename = tempfile.NamedTemporaryFile()
        return filename.name

    def get_media_to_tempfile(self, id):
        (content, content_type) = self.get_media(id)
        tempfile_name = self.get_new_tempfile_name()                                      
        tempfile = open(tempfile_name, "w")
        tempfile.write(content)
        tempfile.close()
        return (tempfile_name, content_type)

    
    # Upload unidentified metadata, get a data ID back
    # XXX Rewrite using the post method.
    def  upload_media(self, type, data):
        url="%smedia/" %(self.base_url)
        raw_response = requests.post(
            url,
            auth=self.auth,
            data=data,
            headers= {'content-type': type})
        if (raw_response.status_code // 100) !=  2:
            msg = "Could not upload media."
            raise ClientException(raw_response.status_code, msg)
        jrv=json.loads(raw_response.text)
        return new_media_result(jrv)

