from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import ugettext
from django.core.exceptions import ValidationError

#from .base import BaseBackend
if "pinax.notifications" in settings.INSTALLED_APPS:
    #from pinax.notifications import models as notification
    from pinax.notifications.backends.base import BaseBackend
    from django.core.mail.backends.smtp import EmailBackend as CoreEmailBackend
    from django.core.mail.message import EmailMultiAlternatives
else:
    notification = None
    CoreEmailBackend = None


class EmailBackend(BaseBackend):
    spam_sensitivity = 2

    def can_send(self, user, notice_type, scoping):
        can_send = super(EmailBackend, self).can_send(user, notice_type, scoping)
        if can_send and user.email:
            return True
        return False

    def deliver(self, recipient, sender, notice_type, extra_context):
        # TODO: require this to be passed in extra_context

        context = self.default_context()
        context.update({
            "recipient": recipient,
            "sender": sender,
            "notice": ugettext(notice_type.display),
        })
        context.update(extra_context)

        from_email = settings.DEFAULT_FROM_EMAIL
        connection = None
        if hasattr(context, 'context_agent') and context['context_agent']:
            from_email = context['context_agent'].email
            if not from_email:
                raise ValidationError("The project sending this notice is missing an email address! agent:"+str(context['context_agent']))

            obj = context['context_agent'].project.custom_smtp()
            if obj and obj['host']:
                try:
                    connection = CoreEmailBackend(host=obj['host'], port=obj['port'], username=obj['username'], password=obj['password'], use_tls=obj['use_tls'])
                    #from_email = obj['username']
                except:
                    raise
            else:
                pass #raise ValidationError("There's no custom email object (or no 'host') for project: "+str(project))
        else:
            raise ValidationError("There's no context_agent related this notice?")

        messages = self.get_formatted_messages((
            "short.txt",
            "full.txt"
        ), notice_type.label, context)

        context.update({
            "message": messages["short.txt"],
        })
        subject = "".join(render_to_string("pinax/notifications/email_subject.txt", context).splitlines())

        context.update({
            "message": messages["full.txt"]
        })
        body = render_to_string("pinax/notifications/email_body.txt", context)

        #print 'sending email from: '+from_email
        # EmailMultiAlternatives(subject='', body='', from_email=None, to=None, bcc=None, connection=None, attachments=None,
        #                        headers=None, alternatives=None, cc=None, reply_to=None)

        email = EmailMultiAlternatives(subject, body, from_email=from_email, to=[recipient.email], reply_to=[from_email], connection=connection)
        #import pdb; pdb.set_trace()
        email.send()

        #send_mail(subject, body, from_email, [recipient.email], connection=connection)

        if connection:
            connection.close()

        #def send_mail(subject, message, from_email, recipient_list,
        #      fail_silently=False, auth_user=None, auth_password=None,
        #      connection=None, html_message=None)
