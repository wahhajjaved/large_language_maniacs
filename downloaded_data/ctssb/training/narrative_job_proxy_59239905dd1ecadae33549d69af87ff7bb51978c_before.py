#BEGIN_HEADER
from biokbase.userandjobstate.client import UserAndJobState
import time
#END_HEADER


class NarrativeJobProxy:
    '''
    Module Name:
    NarrativeJobProxy

    Module Description:
    Very simple proxy that reauthenticates requests to the user_and_job_state
service as the narrative user
    '''

    ######## WARNING FOR GEVENT USERS #######
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    #########################################
    #BEGIN_CLASS_HEADER
    UPDATE_TOKEN_INTERVAL = 24 * 60 * 60 # 1 day in sec
#    UPDATE_TOKEN_INTERVAL = 10
    
    
    def _update_token(self):
        if self._updating:
            return
        if (time.time() - self._updated_at < self.UPDATE_TOKEN_INTERVAL):
            return
        self._updating = True
        print('Updating token at ' + str(time.time()))
        self._ujs = UserAndJobState(self._url, user_id=self._user,
                                    password=self._pwd)
        self._updated_at = time.time()
        self._updating = False
    
    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self._user = config.get('narrative_user')
        self._pwd = config.get('narrative_user_pwd')
        if not self._user or not self._pwd:
            raise ValueError(
                'narrative user and/or narrative pwd missing from deploy.cfg')
        self._url = config.get('ujs_url')
        if not self._url:
            raise ValueError('UJS url missing from deploy.cfg')
        self._updated_at = - self.UPDATE_TOKEN_INTERVAL
        self._updating = False
        self._update_token()
        #END_CONSTRUCTOR
        pass

    def ver(self):
        # self.ctx is set by the wsgi application class
        # return variables are: ver
        #BEGIN ver
        ver = '0.0.1'
        #END ver

        #At some point might do deeper type checking...
        if not isinstance(ver, basestring):
            raise ValueError('Method ver return value ' +
                             'ver is not type basestring as required.')
        # return the results
        return [ver]

    def get_detailed_error(self, job):
        # self.ctx is set by the wsgi application class
        # return variables are: error
        #BEGIN get_detailed_error
        self._update_token()
        error = self._ujs.get_detailed_error(job)
        #END get_detailed_error

        #At some point might do deeper type checking...
        if not isinstance(error, basestring):
            raise ValueError('Method get_detailed_error return value ' +
                             'error is not type basestring as required.')
        # return the results
        return [error]

    def get_job_info(self, job):
        # self.ctx is set by the wsgi application class
        # return variables are: info
        #BEGIN get_job_info
        self._update_token()
        info = self._ujs.get_job_info(job)
        #END get_job_info

        #At some point might do deeper type checking...
        if not isinstance(info, list):
            raise ValueError('Method get_job_info return value ' +
                             'info is not type list as required.')
        # return the results
        return [info]
