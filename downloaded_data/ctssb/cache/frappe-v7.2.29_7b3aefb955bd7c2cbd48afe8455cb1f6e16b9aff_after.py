# Copyright (c) 2012 Web Notes Technologies Pvt Ltd (http://erpnext.com)
# 
# MIT License (MIT)
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT 
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 

"""
Sends email via outgoing server specified in "Control Panel"
Allows easy adding of Attachments of "File" objects
"""

import webnotes	
import conf
from webnotes import msgprint
import email

class EMail:
	"""
	Wrapper on the email module. Email object represents emails to be sent to the client. 
	Also provides a clean way to add binary `FileData` attachments
	Also sets all messages as multipart/alternative for cleaner reading in text-only clients
	"""
	def __init__(self, sender='', recipients=[], subject='', from_defs=0, alternative=0, reply_to=None):
		from email.mime.multipart import MIMEMultipart
		from email import Charset
		Charset.add_charset('utf-8', Charset.QP, Charset.QP, 'utf-8')

		if isinstance(recipients, basestring):
			recipients = recipients.replace(';', ',')
			recipients = recipients.split(',')
			
		self.from_defs = from_defs
		self.sender = sender
		self.reply_to = reply_to or sender
		self.recipients = recipients
		self.subject = subject
		
		self.msg_root = MIMEMultipart('mixed')
		self.msg_multipart = MIMEMultipart('alternative')
		self.msg_root.attach(self.msg_multipart)
		self.cc = []
	
	def set_text(self, message):
		"""
			Attach message in the text portion of multipart/alternative
		"""
		from email.mime.text import MIMEText
		if isinstance(message, unicode):
			message = message.encode('utf-8')
		part = MIMEText(message, 'plain', 'utf-8')		
		self.msg_multipart.attach(part)
		
	def set_html(self, message):
		"""
			Attach message in the html portion of multipart/alternative
		"""
		from email.mime.text import MIMEText		
		if isinstance(message, unicode):
			message = message.encode('utf-8')
		part = MIMEText(message, 'html', 'utf-8')
		self.msg_multipart.attach(part)
	
	def set_message(self, message, mime_type='text/html', as_attachment=0, filename='attachment.html'):
		"""
			Append the message with MIME content to the root node (as attachment)
		"""
		from email.mime.text import MIMEText
		
		maintype, subtype = mime_type.split('/')
		part = MIMEText(message, _subtype = subtype)
		
		if as_attachment:
			part.add_header('Content-Disposition', 'attachment', filename=filename)
		
		self.msg_root.attach(part)
		
	def attach_file(self, n):
		"""
		attach a file from the `FileData` table
		"""
		from webnotes.utils.file_manager import get_file		
		res = get_file(n)
		if not res:
			return
	
		self.add_attachment(res[0], res[1])
	
	def add_attachment(self, fname, fcontent, content_type=None):
	
		from email.mime.audio import MIMEAudio
		from email.mime.base import MIMEBase
		from email.mime.image import MIMEImage
		from email.mime.text import MIMEText
					
		import mimetypes

		if not content_type:
			content_type, encoding = mimetypes.guess_type(fname)

		if content_type is None:
			# No guess could be made, or the file is encoded (compressed), so
			# use a generic bag-of-bits type.
			content_type = 'application/octet-stream'
		
		maintype, subtype = content_type.split('/', 1)
		if maintype == 'text':
			# Note: we should handle calculating the charset
			part = MIMEText(fcontent, _subtype=subtype)
		elif maintype == 'image':
			part = MIMEImage(fcontent, _subtype=subtype)
		elif maintype == 'audio':
			part = MIMEAudio(fcontent, _subtype=subtype)
		else:
			part = MIMEBase(maintype, subtype)
			part.set_payload(fcontent)
			# Encode the payload using Base64
			from email import encoders
			encoders.encode_base64(part)
			
		# Set the filename parameter
		if fname:
			part.add_header('Content-Disposition', 'attachment', filename=fname)

		self.msg_root.attach(part)
	
	def validate(self):
		"""
		validate the email ids
		"""
		if not self.sender:
			self.sender = hasattr(conf, 'auto_email_id') \
					and conf.auto_email_id or '"ERPNext Notification" <automail@erpnext.com>'

		from webnotes.utils import validate_email_add
		# validate ids
		if self.sender and (not validate_email_add(self.sender)):
			webnotes.msgprint("%s is not a valid email id" % self.sender, raise_exception = 1)

		if self.reply_to and (not validate_email_add(self.reply_to)):
			webnotes.msgprint("%s is not a valid email id" % self.reply_to, raise_exception = 1)

		for e in self.recipients:
			if not validate_email_add(e):
				webnotes.msgprint("%s is not a valid email id" % e, raise_exception = 1)
	
	def setup(self):
		"""
		setup the SMTP (outgoing) server from `Control Panel` or defs.py
		"""
		if self.from_defs:
			import webnotes
			self.server = getattr(conf,'mail_server','')
			self.login = getattr(conf,'mail_login','')
			self.port = getattr(conf,'mail_port',None)
			self.password = getattr(conf,'mail_password','')
			self.use_ssl = getattr(conf,'use_ssl',0)

		else:	
			import webnotes.model.doc
			from webnotes.utils import cint

			# get defaults from control panel
			es = webnotes.model.doc.Document('Email Settings','Email Settings')
			self.server = es.outgoing_mail_server.encode('utf-8') or getattr(conf,'mail_server','')
			self.login = es.mail_login.encode('utf-8') or getattr(conf,'mail_login','')
			self.port = cint(es.mail_port) or getattr(conf,'mail_port',None)
			self.password = es.mail_password.encode('utf-8') or getattr(conf,'mail_password','')
			self.use_ssl = cint(es.use_ssl) or cint(getattr(conf, 'use_ssl', ''))

	def make_msg(self):
		self.msg_root['Subject'] = self.subject
		self.msg_root['From'] = self.sender
		self.msg_root['To'] = ', '.join([r.strip() for r in self.recipients])
		if self.reply_to and self.reply_to != self.sender:
			self.msg_root['Reply-To'] = self.reply_to
		if self.cc:
			self.msg_root['CC'] = ', '.join([r.strip() for r in self.cc])
	
	def add_to_queue(self):
		# write to a file called "email_queue" or as specified in email
		q = EmailQueue()
		q.push({
			'server': self.server, 
			'port': self.port, 
			'use_ssl': self.use_ssl,
			'login': self.login,
			'password': self.password,
			'sender': self.sender,
			'recipients': self.recipients, 
			'msg': self.msg_root.as_string()
		})
		q.close()

	def send(self, send_now = 0):
		"""		
		send the message
		"""
		from webnotes.utils import cint
		
		self.setup()
		self.validate()
		self.make_msg()
		
		sess = self.smtp_connect()
		
		sess.sendmail(self.sender, self.recipients, self.msg_root.as_string())
		
		try:
			sess.quit()
		except:
			pass
	

	def smtp_connect(self):
		"""
			Gets a smtp connection
		"""
		from webnotes.utils import cint
		import smtplib
		sess = smtplib.SMTP(self.server.encode('utf-8'), cint(self.port) or None)
		
		if self.use_ssl: 
			sess.ehlo()
			sess.starttls()
			sess.ehlo()
		
		ret = sess.login(self.login.encode('utf-8'), self.password.encode('utf-8'))

		# check if logged correctly
		if ret[0]!=235:
			msgprint(ret[1])
			raise Exception

		return sess