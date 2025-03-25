#!/usr/bin/env python
# -*-coding:utf-8-*-
# Copyright (C) 2015: Frédéric MOHIER
#
# This file incorporates work covered by the following copyright and
# permission notice:
#
# Copyright (C) 2012:
#    Romain Forlot, rforlot@yahoo.com
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import socket
import logging
import getpass
import smtplib
import urllib
# from html import HTML
from optparse import OptionParser, OptionGroup
from email.mime.text import MIMEText
from email.MIMEImage import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

# Global var
image_dir = '/var/lib/shinken/share/images'
customer_logo = 'customer_logo.jpg'
webui_config_file = '/etc/shinken/modules/webui.cfg'

webui2_config_file = '/etc/shinken/modules/webui2.cfg'
webui2_image_dir = '/var/lib/shinken/share/photos'


# Set up root logging
def setup_logging():
    log_level = logging.INFO
    if opts.debug:
        log_level = logging.DEBUG
    if opts.logfile:
        logging.basicConfig(filename=opts.logfile, level=log_level, format='%(asctime)s:%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=log_level, format='%(asctime)s:%(levelname)s: %(message)s')


# Get WebUI information
def get_webui_logo():
    company_logo = ''

    try:
        webui_config_fh = open(webui2_config_file)
    except IOError:
        # WebUI2 not installed ...
        full_logo_path = os.path.join(image_dir, customer_logo)
        if os.path.isfile(full_logo_path):
            return full_logo_path

    if opts.webui:
        # WebUI2 installed
        logging.debug('Webui2 is installed')
        webui_config = webui_config_fh.readlines()
        for line in webui_config:
            if 'company_logo' in line:
                company_logo = line.rsplit('company_logo')[1].strip()
                company_logo += '.png'
        logging.debug('Found company logo property: %s', company_logo)
        if company_logo:
            full_logo_path = os.path.join(webui2_image_dir, company_logo)
            if os.path.isfile(full_logo_path):
                logging.debug('Found company logo file: %s', full_logo_path)
                return full_logo_path
            else:
                logging.debug('File %s does not exist!', full_logo_path)
                return ''

    return company_logo


def get_webui_port():
    port = ''

    try:
        webui_config_fh = open(webui2_config_file)
    except IOError:
        # WebUI2 not installed, try WebUI1
        try:
            webui_config_fh = open(webui_config_file)
        except IOError:
            # No WebUI
            return ''
        else:
            # WebUI1 installed
            logging.debug('Webui1 is installed')
    else:
        # WebUI2 installed
        logging.debug('Webui2 is installed')

    logging.debug('Webui file handler: %s' % (webui_config_fh))
    webui_config = webui_config_fh.readlines()
    # logging.debug('Webui config: %s' % (webui_config))
    for line in webui_config:
        if 'port' in line:
            port = line.rsplit('port')[1].strip()
    return port


def get_webui_url():
    if opts.webui:
        hostname = socket.gethostname()
        webui_port = get_webui_port()
        if not webui_port:
            return

        if opts.webui_url:
            url = '%s/%s/%s' % (opts.webui_url, opts.notification_object, urllib.quote(host_service_var['Hostname']))
        else:
            url = 'http://%s:%s/%s/%s' % (hostname, webui_port, opts.notification_object, urllib.quote(host_service_var['Hostname']))

        # Append service if we notify a service object
        if opts.notification_object == 'service':
            url += '/%s' % (urllib.quote(notification_object_var['service']['Service description']))

        return url


# Get current process user that will be the mail sender
def get_user():
    if opts.sender:
        return opts.sender
    else:
        return '@'.join((getpass.getuser(), socket.gethostname()))


#############################################################################
# Common mail functions and var
#############################################################################
mail_welcome = 'Alignak Monitoring System Notification'
mail_format = {'html': MIMEMultipart(), 'txt': MIMEMultipart('alternative')}


# Construct mail subject field based on which object we notify
def get_mail_subject(object):
    mail_subject = {
        'host': 'Host %s alert for %s since %s' % (
            notification_object_var['host']['Host state'],
            host_service_var['Hostname'],
            notification_object_var['host']['Host state duration']
        ),
        'service': '%s on Host: %s about service %s since %s' % (
            notification_object_var['service']['Service state'],
            host_service_var['Hostname'],
            notification_object_var['service']['Service description'],
            notification_object_var['service']['Service state duration']
        )
    }

    return mail_subject[object]


def get_content_to_send():
    host_service_var.update(notification_object_var[opts.notification_object])


# Translate a comma separated list of mail recipient into a python list
def make_receivers_list(receivers):
    if ',' in receivers:
        ret = receivers.split(',')
    else:
        ret = [receivers]

    return ret


# This just create mail skeleton and doesn't have any content.
# But can be used to add multiple and differents contents.
def create_mail(format):
    # Fill SMTP header and body.
    # It has to be multipart since we can include an image in it.
    logging.debug('Mail format: %s' % (format))
    msg = mail_format[format]
    logging.debug('From: %s' % (get_user()))
    msg['From'] = get_user()
    logging.debug('To: %s' % (opts.receivers))
    msg['To'] = opts.receivers
    logging.debug('Subject: %s' % (opts.prefix + get_mail_subject(opts.notification_object)))
    msg['Subject'] = opts.prefix + get_mail_subject(opts.notification_object)
    msg['Date'] = formatdate()

    return msg


#############################################################################
# Txt creation lair
#############################################################################
def create_txt_message(msg):
    txt_content = [mail_welcome]

    get_content_to_send()
    for k, v in sorted(host_service_var.iteritems()):
        txt_content.append(k + ': ' + v)

    # Add url at the end
    url = get_webui_url()
    logging.debug('Grabbed WebUI URL : %s' % url)
    if url is not None:
        txt_content.append('More details on : %s' % url)

    txt_content = '\r\n'.join(txt_content)

    msgText = MIMEText(txt_content, 'text')
    msg.attach(msgText)
    return msg

#############################################################################
# Html creation lair
#############################################################################


# Process customer logo into mail message so it can be referenced in it later
def add_image2mail(img, mail):
    fp = open(img, 'rb')
    try:
        msgLogo = MIMEImage(fp.read())
        msgLogo.add_header('Content-ID', '<customer_logo>')
        mail.attach(msgLogo)
    except:
        pass

    fp.close()
    return mail


def create_html_message(msg):

    # default state color => OK / UP
    state_color = '#27ae60'
    if opts.notification_object == 'service':
        if notification_object_var['service']['Service state'] == 'WARNING':
            state_color = '#e67e22'
        elif notification_object_var['service']['Service state'] == 'CRITICAL':
            state_color = '#e74c3c'
        elif notification_object_var['service']['Service state'] == 'UNKNOWN':
            state_color = '#2980b9'
        elif notification_object_var['service']['Service state'] == 'ACKNOWLEDGE':
            state_color = '#95a5a6'
        elif notification_object_var['service']['Service state'] == 'DOWNTIME':
            state_color = '#9b59b6'
    else:
        if notification_object_var['host']['Host state'] == 'DOWN':
            state_color = '#e74c3c'
        elif notification_object_var['host']['Host state'] == 'UNREACHABLE':
            state_color = '#e67e22'
        elif notification_object_var['host']['Host state'] == 'ACKNOWLEDGE':
            state_color = '#95a5a6'
        elif notification_object_var['host']['Host state'] == 'DOWNTIME':
            state_color = '#9b59b6'

    # Header part
    html_content = ['''
<html>\r
<head>\r
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">\r
</head>\r
<body style="font-family: Helvetica;">\r''']

    # css
    css_table = 'border-collapse: collapse;width: 650px;'
    css_table_title = 'border-radius: 6px;background-color: #0e7099;color: white;height: 60px;'
    css_state = 'height: 30px;background-color: %s;text-align: center;' % state_color
    css_point = 'height: 20px;width: 20px;border-radius: 100%%;background-color: %s;' % state_color
    css_past = 'display: block;width: 100%%;height: 1px;border: 0;border-top: 2px solid %s;margin: 0;padding: 0;' % state_color
    css_future = 'display: block;width: 100%;height: 1px;border: 0;border-top: 2px dotted #ccc;margin: 1em 0;padding: 0;'
    css_point_title = 'text-align: center;font-size: 12px;color: #acacac;'
    css_length = 'text-align: center;font-size: 12px;color: %s;' % state_color
    css_end = 'width: 628px;display: block;height: 1px;border: 0;border-top: 1px solid #0e7099;'
    css_footer = 'padding-left: 10px;display: block;font-size: 11px;color: #0e7099;height: 40px;'
    css_separator = 'display: block;width: 180px;height: 2px;border: 0;border-top: 2px solid #ccc;margin: 10;padding: 10;'
    css_background = 'background-color: #f8f8f8;width: 648px;border-left: 1px solid #ccc;border-right: 1px solid #ccc;border-bottom: 1px solid #ccc;border-bottom-left-radius: 6px;border-bottom-right-radius: 6px;'


    # Head of the email
    html_content.append('<table style="%s %s">' % (css_table, css_table_title))
    html_content.append('<tr style="height: 60px">')
    html_content.append('<td rowspan="2" style="width:160px">')
    html_content.append('<img alt="Alignak" title="Alignak" width="120" height="35" src="https://raw.githubusercontent.com/Alignak-monitoring-contrib/alignak-notifications/master/alignak.png"/>')
    html_content.append('</td>')
    html_content.append('<td style="width:50px;height: 30px;">')
    html_content.append('<b>Host</b>')
    html_content.append('</td>')
    html_content.append('<td>')
    html_content.append(host_service_var['Hostname'])
    html_content.append('</td>')
    html_content.append('</tr>')

    html_content.append('<tr>')
    html_content.append('<td style="height: 30px;">')
    if opts.notification_object == 'service':
        html_content.append('<b>Service</b>')
    html_content.append('</td>')
    html_content.append('<td>')
    if opts.notification_object == 'service':
        html_content.append(notification_object_var['service']['Service description'])
    html_content.append('</td>')
    html_content.append('</tr>')

    # State
    html_content.append('<tr style="height: 30px">')
    html_content.append('<td colspan="3" style="%s"><b>' % css_state)
    if opts.notification_object == 'service':
        html_content.append(notification_object_var['service']['Service state'])
    else:
        html_content.append(notification_object_var['host']['Host state'])
    html_content.append('</b></td>')
    html_content.append('</tr>')

    html_content.append('</table>')

    # Second part with output of check
    html_content.append('<div style="%s">' % css_background)
    html_content.append('<table style="%s">' % css_table)
    html_content.append('<tr style="height: 100px;">')
    html_content.append('<td style="width: 20px;">')
    html_content.append('</td>')
    html_content.append('<td style="width: 120px;">')
    html_content.append('<b>Message</b>')
    html_content.append('</td>')
    html_content.append('<td style="width: 510">')
    if opts.notification_object == 'service':
        html_content.append(notification_object_var['service']['Service output'])
    html_content.append('</td>')
    html_content.append('</tr>')
    html_content.append('</table>')

    # separator with notification type
    html_content.append('<table style="%s">' % css_table)
    html_content.append('<tr>')
    html_content.append('<td style="width: 200px;">')
    html_content.append('<hr style="%s"/>' % css_separator)
    html_content.append('</td>')
    html_content.append('<td style="width: 250px;text-align: center;">')
    html_content.append('<b>Notification type</b> ')
    html_content.append(host_service_var['Notification type'])
    html_content.append('</td>')
    html_content.append('<td style="width: 200px;">')
    html_content.append('<hr style="%s"/>' % css_separator)
    html_content.append('</td>')
    html_content.append('</tr>')
    html_content.append('</table>')
    html_content.append('<br/>')
    html_content.append('<br/>')
    html_content.append('<br/>')

    # timeline
    html_content.append('<table style="%s">' % css_table)
    html_content.append('<tr>')
    html_content.append('<td style="%swidth: 70px;"><b>' % css_point_title)
    html_content.append(host_service_var['Date'])
    html_content.append('</b></td>')
    html_content.append('<td style="%swidth: 380px;">' % css_length)
    if opts.notification_object == 'service':
        html_content.append(notification_object_var['service']['Service state duration'])
    else:
        html_content.append(notification_object_var['host']['Host state duration'])
    html_content.append('</td>')
    html_content.append('<td style="">')
    html_content.append('</td>')
    html_content.append('</tr>')
    html_content.append('</table>')

    html_content.append('<table style="%s">' % css_table)
    html_content.append('<tr>')
    html_content.append('<td style="width: 20px;">')
    html_content.append('</td>')
    html_content.append('<td style="width: 20px;padding:0;margin:0;">')
    html_content.append('<div style="%s"></div>' % css_point)
    html_content.append('</td>')
    html_content.append('<td style="width: 430px;padding:0;margin:0;">')
    html_content.append('<hr style="%s"/>' % css_past)
    html_content.append('</td>')
    html_content.append('<td style="padding:0;margin:0;">')
    html_content.append('<hr style="%s"/>' % css_future)
    html_content.append('</td>')
    html_content.append('</tr>')
    html_content.append('</table>')

    html_content.append('<br/><br/><br/>')

    # footer
    html_content.append('<hr style="%s"/>' % css_end)
    html_content.append('<div style="%s">' % css_footer)
    html_content.append('This email was generated by Alignak on ')
    html_content.append(formatdate())
    html_content.append('</div>')

    html_content.append('</div>')

    html_content.append('</body></html>')

    # Make final string var to send and encode it to stdout encoding
    # avoiding decoding error.
    html_content = '\r\n'.join(html_content)
    try:
        html_msg = html_content.encode(sys.stdout.encoding)
    except UnicodeDecodeError as e:
        logging.debug('Content is Unicode encoded.')
        html_msg = html_content.decode('utf-8').encode(sys.stdout.encoding)

    logging.debug('HTML string: %s' % html_msg)

    msgText = MIMEText(html_msg, 'html')
    logging.debug('MIMEText: %s' % msgText)
    msg.attach(msgText)
    logging.debug('Mail object: %s' % msg)

    return msg

if __name__ == "__main__":
    parser = OptionParser(description='Send email notifications for Alignak alerts. Message can be formatted in html and embed a customer logo and a link to the WebUI. To include a customer logo, copy an image file named %s in the directory %s' % (customer_logo, image_dir))

    group_debug = OptionGroup(parser, 'Debugging and test options', 'Useful to debug the script run by Alignak processes. Useful to just make a standalone test of script to see what it looks like.')
    group_general = OptionGroup(parser, 'General options', 'Default options to setup mail format, and mail information.')
    group_host_service = OptionGroup(parser, 'Host/service macros to specify concerned object.', 'Used to specify usual macros for notification. If not specified then the script will try to get them from environment variable. You need to enable_environment_macros in alignak.cfg if you want to use them. It is not recommended to use environment variables in large environment. You would better use option -n, -c and -o depending upon which object is concerned.')
    group_details = OptionGroup(parser, 'Details and additionnals informations', 'You can include some useful additional information to notifications with these options. Good practice is to add HOST or SERVICE macros with these details and provide them to the script')
    group_webui = OptionGroup(parser, 'Web User Interface.', 'Used to include some Web User Interface information in the notifications.')

    # Debug and test options
    group_debug.add_option('-D', '--debug', dest='debug', default=False,
                      action='store_true', help='Set log level to debug (verbose mode)')
    group_debug.add_option('-t', '--test', dest='test', default=False,
                      action='store_true', help='Generate a test mail message')
    group_debug.add_option('-l', '--logfile', dest='logfile',
                      help='Specify a log file. Default: log to stdout.')

    # General options
    group_general.add_option('-f', '--format', dest='format', type='choice', choices=['txt', 'html'],
                      default='html', help='Mail format "html" or "txt". Default: html')
    group_general.add_option('-r', '--receivers', dest='receivers',
                      help='Mail recipients. At least on enamil address but you can specify a comma-separated list of email addresses.')
    group_general.add_option('-F', '--sender', dest='sender', default='@'.join((getpass.getuser(), socket.gethostname())),
                      help='Sender email address, default is system user: %s' % '@'.join((getpass.getuser(), socket.gethostname())))
    group_general.add_option('-S', '--SMTP', dest='smtp', default='localhost',
                      help='Target SMTP hostname. None for just a sendmail lanch. Default: localhost')
    group_general.add_option('-L', '--LOGIN', dest='smtplogin', default='',
                      help='Login for SMTP. None for not need login. Default: ')
    group_general.add_option('-P', '--PASSWORD', dest='smtppassword', default='',
                      help='Password for SMTP. None for not need password. Default: ')
    group_general.add_option('-p', '--prefix', dest='prefix', default='',
                      help='Mail subject prefix. Default is no prefix')

    # Host/service options
    group_host_service.add_option('-n', '--notification-object', dest='notification_object', type='choice', default='host',
                      choices=['host', 'service'], help='Choose between host or service notification.')
    group_host_service.add_option('-c', '--commonmacros', dest='commonmacros',
                      help='Double comma separated macros in this order : "NOTIFICATIONTYPE$,,$HOSTNAME$,,$HOSTADDRESS$,,$LONGDATETIME$".')
    group_host_service.add_option('-o', '--objectmacros', dest='objectmacros',
                      help='Double comma separated object macros in this order : "$SERVICEDESC$,,$SERVICESTATE$,,$SERVICEOUTPUT$,,$SERVICEDURATION$" for a service object and "$HOSTSTATE$,,$HOSTDURATION$" for an host object')

    # Details options
    group_details.add_option('-d', '--detailleddesc', dest='detailleddesc',
                      help='Specify $_SERVICEDETAILLEDDESC$ custom macros')
    group_details.add_option('-i', '--impact', dest='impact',
                      help='Specify the $_SERVICEIMPACT$ custom macros')
    group_details.add_option('-a', '--action', dest='fixaction',
                      help='Specify the $_SERVICEFIXACTIONS$ custom macros')

    # WebUI options
    group_webui.add_option('-w', '--webui', dest='webui', default=False,
                      action='store_true', help='Include link to the problem in WebUI.')
    group_webui.add_option('-u', '--url', dest='webui_url',
                      help='WebUI URL as http://my_webui:port/url')

    parser.add_option_group(group_debug)
    parser.add_option_group(group_general)
    parser.add_option_group(group_host_service)
    parser.add_option_group(group_details)
    parser.add_option_group(group_webui)

    (opts, args) = parser.parse_args()

    setup_logging()

    # Check and process arguments
    #
    # Retrieve and setup macros that make the mail content
    if opts.commonmacros == None:
        host_service_var = {
            'Notification type': os.getenv('NAGIOS_NOTIFICATIONTYPE'),
            'Hostname': os.getenv('NAGIOS_HOSTNAME'),
            'Host address': os.getenv('NAGIOS_HOSTADDRESS'),
            'Date': os.getenv('NAGIOS_LONGDATETIME')
        }
    else:
        macros = opts.commonmacros.split(',,')
        host_service_var = {
            'Notification type': macros[0],
            'Hostname': macros[1],
            'Host address': macros[2],
            'Date': macros[3]
        }
    if opts.objectmacros == None:
        notification_object_var = {
            'service': {
                'Service description': os.getenv('NAGIOS_SERVICEDESC'),
                'Service state': os.getenv('NAGIOS_SERVICESTATE'),
                'Service output': os.getenv('NAGIOS_SERVICEOUTPUT'),
                'Service state duration': os.getenv('NAGIOS_SERVICEDURATION')
            },
            'host': {
                'Host state': os.getenv('NAGIOS_HOSTSTATE'),
                'Host state duration': os.getenv('NAGIOS_HOSTDURATION')
            }
        }
    else:
        macros = opts.objectmacros.split(',,')
        if opts.notification_object == 'service':
            notification_object_var = {
                'service': {
                    'Service description': macros[0],
                    'Service state': macros[1],
                    'Service output': macros[2],
                    'Service state duration': macros[3]
                },
                'host': {
                    'Host state': '',
                    'Host state duration': ''
            }

            }
        else:
            notification_object_var = {
                 'service': {
                    'Service description': '',
                    'Service state': '',
                    'Service output': '',
                    'Service state duration': ''
                 },
                'host': {
                    'Host state': macros[0],
                    'Host state duration': macros[1]
                }
            }

    # Load test values
    if opts.test:
        notification_object_var = {
            'service': {
                'Service description': 'Test_Service',
                'Service state': 'TEST',
                'Service output': 'Houston, we got a problem here! Oh, wait. No. It\'s just a test.',
                'Service state duration': '00h 00min 10s'
            },
            'host': {
                'Hostname': 'Test_Host',
                'Host state': 'TEST',
                'Host state duration': '00h 00h 20s'
            }
        }

        host_service_var = {
            'Hostname': 'alignak',
            'Host address': '127.0.0.1',
            'Notification type': 'TEST',
            'Date': 'Now, test'
        }
    else:
        host_service_var.update(notification_object_var[opts.notification_object])

    logging.debug('notification_object_var: %s', notification_object_var)
    logging.debug('host_service_var: %s', host_service_var)

    if not host_service_var or not host_service_var['Hostname']:
        logging.error('You must define at least some host/service information (-c) or specify test mode (-t)')
        sys.exit(6)

    # check required arguments
    if not opts.receivers:
        logging.error('You must define at least one mail recipient using -r')
        sys.exit(5)
    else:
        contactemail = opts.receivers

    if opts.detailleddesc:
        host_service_var['Detailled description'] = opts.detailleddesc.decode(sys.stdin.encoding)
    if opts.impact:
        host_service_var['Impact'] = opts.impact.decode(sys.stdin.encoding)
    if opts.fixaction:
        host_service_var['Fix actions'] = opts.fixaction.decode(sys.stdin.encoding)

    receivers = make_receivers_list(opts.receivers)

    logging.debug('Create mail skeleton')
    mail = create_mail(opts.format)
    logging.debug('Create %s mail content' % (opts.format))
    if opts.format == 'html':
        mail = create_html_message(mail)
    elif opts.format == 'txt':
        mail = create_txt_message(mail)

    try:
        # Use SMTP or sendmail to send the mail ...
        if opts.smtp != 'None':
            logging.debug('Connecting to %s smtp server' % (opts.smtp))
            smtp = smtplib.SMTP(opts.smtp)
            if opts.smtplogin != '':
                smtp.login(opts.smtplogin, opts.smtppassword)
            logging.debug('Send the mail')
            smtp.sendmail(get_user(), receivers, mail.as_string())
            logging.info("Mail sent successfuly")
        else:
            sendmail = '/usr/sbin/sendmail'
            logging.debug('Send the mail')
            p = os.popen('%s -t' % sendmail, 'w')
            logging.debug('Final mail: ' + mail.as_string())
            logging.debug('Send the mail')
            p.write(mail.as_string())
            status = p.close()
            if status is not None:
                logging.error("Sendmail returned %s" % status)
            else:
                logging.info("Mail sent successfuly")
    except Exception as e:
        logging.error("Error when sending mail: %s", str(e))
