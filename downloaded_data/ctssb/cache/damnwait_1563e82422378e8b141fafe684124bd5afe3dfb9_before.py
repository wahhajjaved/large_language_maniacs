import webapp2
from google.appengine.api import memcache

class TestCron(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'

        # cnt = memcache.get("cron_key")

        # if cnt is None:
        # 	self.response.write('Cron task is not running\n')
        # else:
        # 	self.response.write('U have counted to %s' % cnt)
        
        local_time = memcache.get("local_time")
        appt_wait_time = memcache.get("appt_wait_time")
        nonappt_wait_time = memcache.get("nonappt_wait_time")

        #test if parameter is extracted correctly

        if local_time is None or appt_wait_time is None:
			self.response.write('Cron task is not running\n')

        else:
			self.response.write('Data extracted successfully\n')
			self.response.write('Local time: %s\n' % local_time)
			self.response.write('Appointment wait time: %s\n' % appt_wait_time)
			self.response.write('None appointment wait time: %s\n' % nonappt_wait_time)