import sys

from flask import Flask
from flask import request

import simplejson
from subprocess import CalledProcessError, check_output

from github_payload import github_payload
from cspy_conf import cspy_conf
from mailer import mailer
from template_parser import template_parser

import datetime

''' Load Configuration '''
conf = cspy_conf('cspy_man.conf.ini')
current_time = datetime.datetime.now()

app = Flask(__name__)

@app.route('/')
def index():
	app.logger.debug(request)	
	return 'Welcome to CS Python Course Manager'

'''
Hook to Deploy Course Website
'''
@app.route('/deploy', methods=['GET', 'POST'])
def deploy():
	if request.method == 'POST':
		''' POST Request processing '''
		#Parse GitHub payload
		post_data = simplejson.loads(request.form['payload'])
		#app.logger.debug(post_data)
		payload = github_payload(post_data)
		
		''' Execute deployment script '''
		try:
			#app.logger.debug('SCRIPT: {}'.format(conf.scripts['remote_deploy']))
			output = check_output(['bash', conf.scripts['remote_deploy']])
			
			
		except CalledProcessError as e:
			#app.logger.debug('[ERROR]: {}'.format(e))
			output = '[PROCESS_ERROR] {}'.format(e)
		except:
			output = '[OS_ERROR] {}'.format(sys.exc_info()[0])
		
		#Prepare & Send Deployment Email
		tags = {}
		tags['TIMESTAMP'] = current_time.strftime("%Y-%m-%d %I:%M%p %Z")
		tags['REPO_URL'] = payload.repo_url
		tags['REPO_NAME'] = '{}/{}'.format(payload.repo_org, payload.repo_name)
		tags['COMMIT_ID'] = payload.commit_id
		tags['COMMIT_URL'] = payload.commit_url
		tags['COMMIT_TIMESTAMP'] = payload.commit_timestamp
		tags['AUTHOR_NAME'] = payload.author_name
		tags['AUTHOR_EMAIL'] = payload.author_email
		tags['GH_USERNAME'] = payload.author_gh_username
		tags['SCRIPT_LOG'] = output.replace('\n', '<br/>').replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')
		
		tp = template_parser(conf.templates['website_deploy'])
		tp.replace(tags)
		
		mail = mailer(conf)
		mail.send(tp.get_subject(), payload.author_emailstring, tp.get_body())
		
		return 'POST request processed, check logs'
	
	else:
		''' GET Request processing '''
		return 'GET request not supported'

'''
Hook to log commit messages from GitHub
'''
@app.route('/log', methods=['GET', 'POST'])
def deploy():
	if request.method == 'POST':
		return 'POST request processed, check logs'
	else:
		''' GET Request processing '''
		return 'GET request not supported'



if __name__ == '__main__':
	#app.debug = True
	#app.host = '0.0.0.0'
	app.run()

