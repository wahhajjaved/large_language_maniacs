#!/usr/bin/python3
# coding: utf-8

import os
import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.utils import formatdate
from time import sleep, time


def create_mail(mfrom, mto, subject='', message='', attachment_paths=[]):
    mailcontent = MIMEMultipart()
    mailcontent['From'] = mfrom
    mailcontent['To'] = mto
    mailcontent['Subject'] = subject
    mailcontent['Date'] = formatdate()
    if message:
        msg = MIMEText(message, 'plain', 'utf-8')
        mailcontent.attach(msg)
    attach2mail(mailcontent, attachment_paths)
    return mailcontent

def attach2mail(mailcontent, filepaths):
    for fname in filepaths:
        with open(fname, 'rb') as f:
            content = f.read()
        fname = fname.split('/')[-1]

        conttype, ignored = mimetypes.guess_type(fname)
        if conttype is None:
            conttype = 'application/octet-stream'
        maintype, subtype = conttype.split('/')

        if maintype == 'image':
            attachment = MIMEImage(content, subtype, filename=fname)
        elif maintype == 'text':
            attachment = MIMEText(content, subtype, 'utf-8')
        elif maintype == 'audio':
            attachment = MIMEAudio(content, subtype, filename=fname)
        else:
            attachment = MIMEApplication(content, subtype, filename=fname)

        attachment.add_header('Content-Disposition', 'attachment', filename=fname)
        mailcontent.attach(attachment)

def send_mail(mfrom, mpassword, mto, mserver, mport, mailcontent):
    mailer = smtplib.SMTP(mserver, mport)
    try:
        mailer.ehlo()
        mailer.starttls()
        mailer.ehlo()
        mailer.login(mfrom, mpassword)
        mailer.sendmail(mfrom, mto.split(','), mailcontent.as_string())
    finally:
        mailer.close()
        print('mail sent at ' + str(time()))


if __name__ == '__main__':
    mail = create_mail(mail_from='test_from@test', mail_to='mail_to@test',
                       subject='test subject', message='test message', attachment_paths=[])
    print(mail.as_string())
