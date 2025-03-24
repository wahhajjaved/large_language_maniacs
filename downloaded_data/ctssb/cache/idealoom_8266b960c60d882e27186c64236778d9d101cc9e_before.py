# coding=UTF-8
import email
import mailbox
import re
import smtplib
import os
from cgi import escape as html_escape
from collections import defaultdict
from email.header import decode_header as decode_email_header, Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from time import mktime

import jwzthreading
from bs4 import BeautifulSoup, Comment
from pyramid.threadlocal import get_current_registry
from datetime import datetime
from imaplib2 import IMAP4_SSL, IMAP4
import transaction
from sqlalchemy.orm import deferred
from sqlalchemy.orm import joinedload_all
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    Unicode,
    Binary,
    UnicodeText,
    Boolean,
)

from .generic import PostSource
from .post import ImportedPost
from .auth import EmailAccount
from assembl.tasks.imap import import_mails
from assembl.lib.sqla import mark_changed


class AbstractMailbox(PostSource):
    """
    A Mailbox refers to any source of Email, and
    whose messages should be imported and displayed as Posts.
    It must not be instanciated directly
    """
    __tablename__ = "mailbox"
    id = Column(Integer, ForeignKey(
        'post_source.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)

    folder = Column(UnicodeText, default=u"INBOX", nullable=False)

    last_imported_email_uid = Column(UnicodeText)
    subject_mangling_regex = Column(UnicodeText, nullable=True)
    subject_mangling_replacement = Column(UnicodeText, nullable=True)
    __compiled_subject_mangling_regex = None

    def _compile_subject_mangling_regex(self):
        if(self.subject_mangling_regex):
            self.__compiled_subject_mangling_regex =\
                re.compile(self.subject_mangling_regex)
        else:
            self.__compiled_subject_mangling_regex = None

    __mapper_args__ = {
        'polymorphic_identity': 'mailbox',
    }

    def mangle_mail_subject(self, subject):
        if self.__compiled_subject_mangling_regex is None:
            self._compile_subject_mangling_regex()

        if self.__compiled_subject_mangling_regex:
            if self.subject_mangling_replacement:
                repl = self.subject_mangling_replacement
            else:
                repl = ''
            (retval, num) =\
                self.__compiled_subject_mangling_regex.subn(repl, subject)
            return retval
        else:
            return subject

    VALID_TAGS = ['a',
                  'b',
                  'blockquote',
                  'code',
                  'del',
                  'dd',
                  'dl',
                  'dt',
                  'em',
                  #We do not allow Hx tax, whould cause layout problems (manageable however)
                  'i',
                  #We do not allow img tags, either the reference is a local file (which we don't support yet), our we could link to a bunch of outside scripts.
                  'li',
                  'ol',
                  'p',
                  'pre',
                  's',
                  'sup',
                  'sub',
                  'strike',
                  'table',
                  'td',
                  'th',
                  'tr',
                  'ul',
                  'br',
                  'hr',
                  ]
    VALID_ATTRIBUTES = ['href',#For hyperlinks
                        
                        'alt',#For accessiblity
                        'colspan', 'headers', 'abbr', 'scope', 'sorted'#For tables
                  ]
    @staticmethod
    def sanitize_html(html_value, valid_tags=VALID_TAGS, valid_attributes=VALID_ATTRIBUTES):
        """ Maybe we should have used Bleach (https://github.com/jsocol/bleach)
        """
        soup = BeautifulSoup(html_value)
        
        for tag in soup.find_all(True):
            if tag.name not in valid_tags:
                tag.hidden = True
            else: # it might have bad attributes
                for attr in tag.attrs.keys():
                    if attr not in valid_attributes:
                        del tag[attr]

        return soup.decode_contents()

    @staticmethod
    def strip_full_message_quoting_plaintext(message_body):
        """Assumes any encoding conversions have already been done 
        """
        #Most useful to develop this:
        #http://www.motobit.com/util/quoted-printable-decoder.asp
        debug = True;
        #To be considered matching, each line must match successive lines, in order
        quote_announcement_lines_regexes = {
            'generic_original_message':  {
                        'announceLinesRegexes': [re.compile("/-+\s*Original Message\s*-+/")],
                        'quotePrefixRegex': re.compile(r"^>\s|^>$")
                    },
            'gmail_fr_circa_2012':  {
                        'announceLinesRegexes': [re.compile(r"^Le .*, .*<.*@.*> a écrit :")],# 2012 Le 6 juin 2011 15:43, <nicolas.decordes@orange-ftgroup.com> a écrit :
                        'quotePrefixRegex': re.compile(r"^>\s|^>$")
                    },
            'gmail_en_circa_2014':  {
                        'announceLinesRegexes': [re.compile(r"^\d{4}-\d{2}-\d{2}.*<.*@.*>:")],# 2014-06-17 10:32 GMT-04:00 Benoit Grégoire <benoitg@coeus.ca>:
                        'quotePrefixRegex': re.compile(r"^>\s|^>$")
                    },
            'outlook_fr_circa_2012':  {
                        'announceLinesRegexes': [re.compile(r"^\d{4}-\d{2}-\d{2}.*<.*@.*>:")],# 2014-06-17 10:32 GMT-04:00 Benoit Grégoire <benoitg@coeus.ca>:
                        'quotePrefixRegex': re.compile(r"^>\s|^>$")
                    },
            'outlook_fr_multiline_circa_2012': {
                        'announceLinesRegexes': [re.compile(r"^_+$"), #________________________________
                                                re.compile(r"^\s*$"), #Only whitespace
                                                re.compile(r"^De :.*$"),
                                                re.compile(r"^Envoy.+ :.*$"),
                                                re.compile(r"^À :.*$"),
                                                re.compile(r"^Objet :.*$"),
                                                ],
                        'quotePrefixRegex': re.compile(r"^.*$")
                    },
            'outlook_en_multiline_circa_2012': {
                        'announceLinesRegexes': [re.compile(r"^_+$"), #________________________________
                                                re.compile(r"^\s*$"), #Only whitespace
                                                re.compile(r"^From:.*$"),
                                                re.compile(r"^Sent:.*$"),
                                                re.compile(r"^To:.*$"),
                                                re.compile(r"^Subject:.*$"),
                                                ],
                        'quotePrefixRegex': re.compile(r"^.*$")
                    },
            }
        def check_quote_announcement_lines_match(currentQuoteAnnounce, keysStillMatching, lineToMatch):
            
            if len(keysStillMatching) == 0:
                #Restart from scratch
                keysStillMatching = quote_announcement_lines_regexes.keys()
            nextIndexToMatch = len(currentQuoteAnnounce)
            keys = list(keysStillMatching)
            matchComplete = False
            for key in keys:
                if len(quote_announcement_lines_regexes[key]['announceLinesRegexes']) > nextIndexToMatch:
                    if quote_announcement_lines_regexes[key]['announceLinesRegexes'][nextIndexToMatch].match(lineToMatch):
                        if len(quote_announcement_lines_regexes[key]['announceLinesRegexes']) -1 == nextIndexToMatch:
                            matchComplete = key
                    else:
                        keysStillMatching.remove(key)
            if len(keysStillMatching)>0:
                currentQuoteAnnounce.append(lineToMatch)
            return matchComplete, keysStillMatching
        
        
        defaultQuotePrefixRegex=re.compile(r"^>\s|^>$")
        quote_prefix_regex=defaultQuotePrefixRegex
        whitespace_line_regex=re.compile(r"^\s*$")
        retval = []
        currentQuoteAnnounce = []
        keysStillMatching = []
        currentQuote = []
        currentWhiteSpace = []
        class LineState:
            Normal="Normal"
            PrefixedQuote='PrefixedQuote'
            PotentialQuoteAnnounce='PotentialQuoteAnnounce'
            QuoteAnnounceLastLine='QuoteAnnounceLastLine'
            AllWhiteSpace='AllWhiteSpace'
            
        line_state_before_transition = LineState.Normal
        previous_line_state = LineState.Normal
        line_state = LineState.Normal
        for line in message_body.splitlines():
            if line_state != previous_line_state:
                line_state_before_transition = previous_line_state
            previous_line_state = line_state
            
            (matchComplete, keysStillMatching) = check_quote_announcement_lines_match(currentQuoteAnnounce, keysStillMatching, line)
            if matchComplete:
                line_state = LineState.QuoteAnnounceLastLine
                quote_prefix_regex = quote_announcement_lines_regexes[keysStillMatching[0]]['quotePrefixRegex']
            elif len(keysStillMatching) > 0:
                line_state = LineState.PotentialQuoteAnnounce
            elif quote_prefix_regex.match(line):
                line_state = LineState.PrefixedQuote
            elif whitespace_line_regex.match(line):
                line_state = LineState.AllWhiteSpace
            else:
                line_state = LineState.Normal
            if line_state == LineState.Normal:
                if((previous_line_state != LineState.AllWhiteSpace) & len(currentWhiteSpace) > 0):
                    retval += currentWhiteSpace
                    currentWhiteSpace = []
                if(len(currentQuote) > 0):
                    retval += currentQuoteAnnounce
                    retval += currentQuote
                    currentQuote = []
                    currentQuoteAnnounce = []
                if(previous_line_state == LineState.AllWhiteSpace):
                    retval += currentWhiteSpace
                    currentWhiteSpace = []
                retval.append(line)
            elif line_state == LineState.PrefixedQuote:
                currentQuote.append(line)
            elif line_state == LineState.QuoteAnnounceLastLine:
                currentQuoteAnnounce = []
            elif line_state == LineState.AllWhiteSpace:
                currentWhiteSpace.append(line)
            if debug:
                print "%-30s %s" % (line_state, line)
        #if line_state == LineState.PrefixedQuote | (line_state == LineState.AllWhiteSpace & line_state_before_transition == LineState.PrefixedQuote)
            #We just let trailing quotes and whitespace die...
        return '\n'.join(retval)

    @staticmethod
    def strip_full_message_quoting_html(message_body):
        """Assumes any encoding conversions have already been done 
        """
        #Most useful to develop this:
        #http://www.motobit.com/util/quoted-printable-decoder.asp
        #http://www.freeformatter.com/html-formatter.html
        #http://www.freeformatter.com/xpath-tester.html#ad-output
        
        debug = True;
        from lxml import html, etree
        doc = html.fromstring(message_body)
        #Strip GMail quotes
        matches = doc.find_class('gmail_quote')
        if len(matches) > 0:
            if not matches[0].text or "---------- Forwarded message ----------" not in matches[0].text:
                matches[0].drop_tree()
                return html.tostring(doc)
            
        #Strip modern Apple Mail quotes
        find = etree.XPath(r"//child::blockquote[contains(@type,'cite')]/preceding-sibling::br[contains(@class,'Apple-interchange-newline')]/parent::node()/parent::node()")
        matches = find(doc)
        #print len(matches)
        #for index,match in enumerate(matches):
        #    print "Match: %d: %s " % (index, html.tostring(match))
        if len(matches) == 1:
            matches[0].drop_tree()
            return html.tostring(doc)
            

        #Strip old AppleMail quotes (french)
        regexpNS = "http://exslt.org/regular-expressions"
        ##Trying to match:  Le 6 juin 2011 à 11:02, Jean-Michel Cornu a écrit :
        find = etree.XPath(r"//child::div[re:test(text(), '^.*Le .*\d{4} .*:\d{2}, .* a .*crit :.*$', 'i')]/following-sibling::br[contains(@class,'Apple-interchange-newline')]/parent::node()",
                    namespaces={'re':regexpNS})
        matches = find(doc)
        if len(matches) == 1:
            matches[0].drop_tree()
            return html.tostring(doc)
        
        #Strip Outlook quotes (when outlook gives usable structure)
        find = etree.XPath(r"//body/child::blockquote/child::div[contains(@class,'OutlookMessageHeader')]/parent::node()")
        matches = find(doc)
        if len(matches) == 1:
            matches[0].drop_tree()
            return html.tostring(doc)
        
        #Strip Outlook quotes (when outlook gives NO usable structure)
        successiveStringsToMatch = [
                                        '|'.join(['^From:.*$','^De :.*$']),
                                        '|'.join(['^Sent:.*$','^Envoy.+ :.*$']),
                                        '|'.join(['^To:.*$','^.+:.*$']), #Trying to match À, but unicode is really problematic in lxml regex
                                        '|'.join(['^Subject:.*$','^Objet :.*$']),
                                    ]
        regexpNS = "http://exslt.org/regular-expressions"
        successiveStringsToMatchRegex = []
        for singleHeaderLanguageRegex in successiveStringsToMatch:
            successiveStringsToMatchRegex.append(r"descendant::*[re:test(text(), '"+singleHeaderLanguageRegex+"')]")

        regex = " and ".join(successiveStringsToMatchRegex)
        find = etree.XPath(r"//descendant::div["+regex+"]",
                            namespaces={'re':regexpNS})
        matches = find(doc)
        if len(matches) == 1:
            findQuoteBody = etree.XPath(r"//descendant::div["+regex+"]/following-sibling::*",
                            namespaces={'re':regexpNS})
            quoteBodyElements = findQuoteBody(doc)
            for quoteElement in quoteBodyElements:
                #This moves the text to the tail of matches[0]
                quoteElement.drop_tree()
            matches[0].tail = None
            matches[0].drop_tree()
            return html.tostring(doc)
        
        #Strip Thunderbird quotes
        mainXpathFragment = "//child::blockquote[contains(@type,'cite') and boolean(@cite)]"
        find = etree.XPath(mainXpathFragment+"/self::blockquote")
        matches = find(doc)
        if len(matches) == 1:
            matchQuoteAnnounce = doc.xpath(mainXpathFragment+"/preceding-sibling::*")
            if len(matchQuoteAnnounce) > 0:
                matchQuoteAnnounce[-1].tail = None
                matches[0].drop_tree()
                return html.tostring(doc)
            
        #Nothing was stripped...
        return html.tostring(doc)

    def parse_email(self, message_string, existing_email=None):
        parsed_email = email.message_from_string(message_string)
        body = None
        error_description = None
        
        def get_payload(message):
            """ Returns the first text/html body, and falls back to text/plain body """

            def process_part(part, default_charset, text_part, html_part):
                """ Returns the first text/plain body as a unicode object, and the first text/html body """
                if part.is_multipart():
                    for part in part.get_payload():
                        charset = part.get_content_charset(default_charset)
                        (text_part, html_part) = process_part(
                            part, charset, text_part, html_part)
                else:
                    charset = part.get_content_charset(default_charset)
                    decoded_part = part.get_payload(decode=True)
                    decoded_part = decoded_part.decode(charset, 'replace')
                    if part.get_content_type() == 'text/plain' and text_part is None:
                        text_part = decoded_part
                    elif part.get_content_type() == 'text/html' and html_part is None:
                        html_part = decoded_part
                return (text_part, html_part)

            html_part = None
            text_part = None
            default_charset = message.get_charset() or 'ISO-8859-1'
            (text_part, html_part) = process_part(message, default_charset, text_part, html_part)
            if html_part:
                return ('text/html',self.sanitize_html(AbstractMailbox.strip_full_message_quoting_html(html_part)))
            elif text_part:
                return ('text/plain', AbstractMailbox.strip_full_message_quoting_plaintext(text_part))
            else:
                return ('text/plain',u"Sorry, no assembl-supported mime type found in message parts")

        (mimeType, body) = get_payload(parsed_email)

        def email_header_to_unicode(header_string):
            decoded_header = decode_email_header(header_string)
            default_charset = 'ASCII'

            text = ''.join(
                [
                    unicode(t[0], t[1] or default_charset) for t in
                    decoded_header
                ]
            )

            return text

        new_message_id = parsed_email.get('Message-ID', None)
        if new_message_id:
            new_message_id = email_header_to_unicode(
                new_message_id)
        else:
            error_description = "Unable to parse the Message-ID for message string: \n%s" % message_string
            return (None, None, error_description)
        
        assert new_message_id;
        assert new_message_id != ''
        
        new_in_reply_to = parsed_email.get('In-Reply-To', None)
        if new_in_reply_to:
            new_in_reply_to = email_header_to_unicode(
                new_in_reply_to)

        sender = email_header_to_unicode(parsed_email.get('From'))
        sender_name, sender_email = parseaddr(sender)
        sender_email_account = EmailAccount.get_or_make_profile(self.db, sender_email, sender_name)
        creation_date = datetime.utcfromtimestamp(
            mktime(email.utils.parsedate(parsed_email['Date'])))
        subject = email_header_to_unicode(parsed_email['Subject'])
        recipients = email_header_to_unicode(parsed_email['To'])
        body = body.strip()
        # Try/except for a normal situation is an anti-pattern,
        # but sqlalchemy doesn't have a function that returns
        # 0, 1 result or an exception
        try:
            email_object = self.db.query(Email).filter(
                Email.source_post_id == new_message_id,
                Email.discussion_id == self.discussion_id,
                Email.source == self
            ).one()
            if existing_email and existing_email != email_object:
                raise ValueError("The existing object isn't the same as the one found by message id")
            email_object.recipients = recipients
            email_object.sender = sender
            email_object.subject = subject
            email_object.creation_date = creation_date
            email_object.source_post_id = new_message_id
            email_object.in_reply_to = new_in_reply_to
            email_object.body = body
            email_object.body_mime_type = mimeType
            email_object.full_message = message_string
        except NoResultFound:
            email_object = Email(
                discussion=self.discussion,
                recipients=recipients,
                sender=sender,
                subject=subject,
                creation_date=creation_date,
                source_post_id=new_message_id,
                in_reply_to=new_in_reply_to,
                body=body,
                body_mime_type = mimeType,
                full_message=message_string
            )
        except MultipleResultsFound:
            """ TO find duplicates (this should no longer happen, but in case it ever does...
            
SELECT * FROM post WHERE id in (SELECT MAX(post.id) as max_post_id FROM imported_post JOIN post ON (post.id=imported_post.id) GROUP BY message_id, source_id HAVING COUNT(post.id)>1)

To kill them:


USE assembl;
UPDATE  post p
SET     parent_id = (
SELECT new_post_parent.id AS new_post_parent_id
FROM post AS post_to_correct
JOIN post AS bad_post_parent ON (post_to_correct.parent_id = bad_post_parent.id)
JOIN post AS new_post_parent ON (new_post_parent.message_id = bad_post_parent.message_id AND new_post_parent.id <> bad_post_parent.id)
WHERE post_to_correct.parent_id IN (
  SELECT MAX(post.id) as max_post_id 
  FROM imported_post 
  JOIN post ON (post.id=imported_post.id) 
  GROUP BY message_id, source_id
  HAVING COUNT(post.id)>1
  )
AND p.id = post_to_correct.id
)

USE assembl;
DELETE
FROM post WHERE post.id IN (SELECT MAX(post.id) as max_post_id FROM imported_post JOIN post ON (post.id=imported_post.id) GROUP BY message_id, source_id HAVING COUNT(post.id)>1)

"""
            raise MultipleResultsFound("ID %s has duplicates in source %d"%(new_message_id,self.id))
        email_object.creator = sender_email_account.profile
        email_object.source = self
        email_object = self.db.merge(email_object)
        return (email_object, parsed_email, error_description)
        
    """
    emails have to be a complete set
    """
    @staticmethod
    def thread_mails(emails):
        #print('Threading...')
        emails_for_threading = []
        for mail in emails:
            email_for_threading = jwzthreading.make_message(email.message_from_string(mail.full_message))
            #Store our emailsubject, jwzthreading does not decode subject itself
            email_for_threading.subject = mail.subject
            #Store our email object pointer instead of the raw message text
            email_for_threading.message = mail
            emails_for_threading.append(email_for_threading)

        threaded_emails = jwzthreading.thread(emails_for_threading)

        # Output
        L = threaded_emails.items()
        L.sort()
        for subj, container in L:
            jwzthreading.print_container(container, 0, True)
            
        def update_threading(threaded_emails, parent=None, debug=False):
            if debug:
                print "\n\nEntering update_threading() for %s mails:" % len(threaded_emails)
            for container in threaded_emails:
                if debug:
                    #jwzthreading.print_container(container)
                    print("\nProcessing:  " + repr(container.message.subject) + " " + repr(container.message.message_id)+ " " + repr(container.message.message.id))
                    print "container: " + (repr(container))
                    print "parent: " + repr(container.parent)
                    print "children: " + repr(container.children)

                

                if(container.message):
                    current_parent = container.message.message.parent
                    if(current_parent):
                        db_parent_message_id = current_parent.message_id
                    else:
                        db_parent_message_id = None

                    if parent:
                        if parent.message:
                            #jwzthreading strips the <>, re-add them
                            algorithm_parent_message_id = unicode("<"+parent.message.message_id+">")
                        else:
                            if debug:
                                print "Parent was a dummy container, we may need \
                                     to handle this case better, as we just \
                                     potentially lost sibbling relationships"
                            algorithm_parent_message_id = None
                    else:
                        algorithm_parent_message_id = None
                    if debug:
                        print("Current parent from database: " + repr(db_parent_message_id))
                        print("Current parent from algorithm: " + repr(algorithm_parent_message_id))
                        print("References: " + repr(container.message.references))
                    if algorithm_parent_message_id != db_parent_message_id:
                        if current_parent == None or isinstance(current_parent, Email):
                            if debug:
                                print("UPDATING PARENT for :" + repr(container.message.message.message_id))
                            new_parent = parent.message.message if algorithm_parent_message_id else None
                            if debug:
                                print repr(new_parent)
                            container.message.message.set_parent(new_parent)
                        else:
                            if debug:
                                print "Skipped reparenting:  the current parent \
                                isn't an email, the threading algorithm only \
                                considers mails"
                    update_threading(container.children, container, debug=debug)
                else:
                    if debug: 
                        print "Current message ID: None, was a dummy container"
                    update_threading(container.children, parent, debug=debug)
                
        update_threading(threaded_emails.values(), debug=False)

    def reprocess_content(self):
        """ Allows re-parsing all content as if it were imported for the first time
            but without re-hitting the source, or changing the object ids.
            Call when a code change would change the representation in the database
            """
        emails = self.db.query(Email).filter(
                Email.source_id == self.id,
                ).options(joinedload_all(Email.parent))
        session = self.db
        for email in emails:
            #session = Email.db
            #session.add(email)
            (email_object, dummy, error) = self.parse_email(email.full_message, email)
            #session.add(email_object)
            session.commit()
            #session.remove()

        with transaction.manager:
            self.thread_mails(emails)
        
    def import_content(self, only_new=True):
        #Mailbox.do_import_content(self, only_new)
        import_mails.delay(self.id, only_new)



    def send_post(self, post):
        #TODO benoitg
        print "TODO: Mail::send_post():  Actually queue message"
        #self.send_mail(sender=post.creator, message_body=post.body, subject=post.subject)
        
    def send_mail(
        self,
        sender,
        message_body,
        html_body=None,
        subject='[Assembl]'
    ):
        """
        Send an email from the given sender to the configured recipient(s) of
        emails for this mailbox.
        """

        sent_from = ' '.join([
            "%(sender_name)s on Assembl" % {
                "sender_name": sender.display_name()
            },
            "<%(sender_email)s>" % {
                "sender_email": sender.get_preferred_email(),
            }
        ])

        if type(message_body) == 'str':
            message_body = message_body.decode('utf-8')

        recipients = self.get_send_address()

        message = MIMEMultipart('alternative')
        message['Subject'] = Header(subject, 'utf-8')
        message['From'] = sent_from

        message['To'] = recipients

        plain_text_body = message_body
        html_body = html_body or message_body

        # TODO: The plain text and html parts of the email should be different,
        # but we'll see what we can get from the front-end.

        plain_text_part = MIMEText(
            plain_text_body.encode('utf-8'),
            'plain',
            'utf-8'
        )

        html_part = MIMEText(
            html_body.encode('utf-8'),
            'html',
            'utf-8'
        )

        message.attach(plain_text_part)
        message.attach(html_part)

        smtp_connection = smtplib.SMTP(
            get_current_registry().settings['mail.host']
        )

        smtp_connection.sendmail(
            sent_from,
            recipients,
            message.as_string()
        )

        smtp_connection.quit()

    def __repr__(self):
        return "<Mailbox %s>" % repr(self.name)

class IMAPMailbox(AbstractMailbox):
    """
    A IMAPMailbox refers to an Email inbox that can be accessed with IMAP.
    """
    __tablename__ = "source_imapmailbox"
    id = Column(Integer, ForeignKey(
        'mailbox.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)

    host = Column(String(1024), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(UnicodeText, nullable=False)
    #Note:  If using STARTTLS, this should be set to false
    use_ssl = Column(Boolean, default=True)
    password = Column(UnicodeText, nullable=False)
    
    __mapper_args__ = {
        'polymorphic_identity': 'source_mailinglist',
    }
    @staticmethod
    def do_import_content(mbox, only_new=True):
        mbox = mbox.db.merge(mbox)
        mbox.db.add(mbox)
        if mbox.use_ssl:
            mailbox = IMAP4_SSL(host=mbox.host.encode('utf-8'), port=mbox.port)
        else:
            mailbox = IMAP4(host=mbox.host.encode('utf-8'), port=mbox.port)
        if 'STARTTLS' in mailbox.capabilities:
            #Always use starttls if server supports it
            mailbox.starttls()
        mailbox.login(mbox.username, mbox.password)
        mailbox.select(mbox.folder)

        command = "ALL"

        if only_new and mbox.last_imported_email_uid:
            command = "(UID %s:*)" % mbox.last_imported_email_uid

        search_status, search_result = mailbox.uid('search', None, command)

        email_ids = search_result[0].split()

        if only_new and mbox.last_imported_email_uid:
            # discard the first message, it should be the last imported email.
            del email_ids[0]

        def import_email(mailbox_obj, email_id):
            session = mailbox_obj.db()
            status, message_data = mailbox.uid('fetch', email_id, "(RFC822)")
            for response_part in message_data:
                if isinstance(response_part, tuple):
                    message_string = response_part[1]

            (email_object, dummy, error) = mailbox_obj.parse_email(message_string)
            if error:
                raise Exception(error)
            session.add(email_object)
            mailbox_obj.last_imported_email_uid = \
                email_ids[len(email_ids)-1]
            transaction.commit()
            mailbox_obj = AbstractMailbox.get(id=mailbox_obj.id)

        if len(email_ids):
            new_emails = [import_email(mbox, email_id) for email_id in email_ids]

        discussion_id = mbox.discussion_id
        mailbox.close()
        mailbox.logout()
        mark_changed()
        transaction.commit()

        with transaction.manager:
            if len(email_ids):
                #We imported mails, we need to re-thread
                emails = Email.db().query(Email).filter(
                    Email.discussion_id == discussion_id,
                    ).options(joinedload_all(Email.parent))

                AbstractMailbox.thread_mails(emails)
                mark_changed()

    _address_match_re = re.compile(
        r'[\w\-][\w\-\.]+@[\w\-][\w\-\.]+[a-zA-Z]{1,4}'
    )

    def most_common_recipient_address(self):
        """
        Find the most common recipient address of the contents of this emaila
        address. This address can, in most use-cases can be considered the
        mailing list address.
        """

        recipients = self.db.query(
            Email.recipients,
        ).filter(
            Email.source_id == self.id,
        )

        addresses = defaultdict(int)

        for (recipients, ) in recipients:
            for address in self._address_match_re.findall(recipients):
                addresses[address] += 1

        if addresses:
            addresses = addresses.items()
            addresses.sort(key=lambda (address, count): count)
            return addresses[-1][0]

    def get_send_address(self):
        """
        Get the email address to send a message to the discussion
        """
        return self.most_common_recipient_address()

    def serializable(self):
        serializable_source = super(AbstractMailbox, self).serializable()

        serializable_source.update({
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "use_ssl": self.use_ssl,
            "folder": self.folder,
            "most_common_recipient_address":
            self.most_common_recipient_address()
        })

        return serializable_source

class MailingList(IMAPMailbox):
    """
    A mailbox with mailing list semantics
    (single post address, subjetc mangling, etc.)
    """
    __tablename__ = "source_mailinglist"
    id = Column(Integer, ForeignKey(
        'source_imapmailbox.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)

    post_email_address = Column(UnicodeText, nullable=True)

    __mapper_args__ = {
        'polymorphic_identity': 'source_mailinglist',
    }

    def get_send_address(self):
        """
        Get the email address to send a message to the discussion
        """
        return self.post_email()


class AbstractFilesystemMailbox(AbstractMailbox):
    """
    A Mailbox refers to an Email inbox that is stored the server's filesystem.
    """
    __tablename__ = "source_filesystemmailbox"
    id = Column(Integer, ForeignKey(
        'mailbox.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)

    filesystem_path = Column(Unicode(), nullable=False)
    
    __mapper_args__ = {
        'polymorphic_identity': 'source_filesystemmailbox',
    }

class MaildirMailbox(AbstractFilesystemMailbox):
    """
    A Mailbox refers to an Email inbox that is stored as maildir on the server.
    """
    __tablename__ = "source_maildirmailbox"
    id = Column(Integer, ForeignKey(
        'source_filesystemmailbox.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)
    
    __mapper_args__ = {
        'polymorphic_identity': 'source_maildirmailbox',
    }
    @staticmethod
    def do_import_content(abstract_mbox, only_new=True):
        abstract_mbox = abstract_mbox.db.merge(abstract_mbox)
        abstract_mbox.db.add(abstract_mbox)
        discussion_id = abstract_mbox.discussion_id
        
        if not os.path.isdir(abstract_mbox.filesystem_path):
            raise "There is no directory at %s" % abstract_mbox.filesystem_path
        else:
            cur_folder_path = os.path.join(abstract_mbox.filesystem_path, 'cur')
            cur_folder_present = os.path.isdir(cur_folder_path)
            new_folder_path = os.path.join(abstract_mbox.filesystem_path, 'new')
            new_folder_present = os.path.isdir(new_folder_path)
            tmp_folder_path = os.path.join(abstract_mbox.filesystem_path, 'tmp')
            tmp_folder_present = os.path.isdir(tmp_folder_path)
            
            if not (cur_folder_present | new_folder_present | tmp_folder_present):
                raise "Directory at %s is NOT a maildir" % abstract_mbox.filesystem_path
            else:
                #Fix the maildir in case some folders are missing
                #For instance, git cannot store empty folder
                if not cur_folder_present:
                    os.mkdir(cur_folder_path)
                if not new_folder_present:
                    os.mkdir(new_folder_path)
                if not tmp_folder_present:
                    os.mkdir(tmp_folder_path)

        mbox = mailbox.Maildir(abstract_mbox.filesystem_path, factory=None, create=False)
        mails = mbox.values()
        #import pdb; pdb.set_trace()
        def import_email(abstract_mbox, message_data):
            session = abstract_mbox.db()
            message_string = message_data.as_string()

            (email_object, dummy, error) = abstract_mbox.parse_email(message_string)
            if error:
                raise Exception(error)
            session.add(email_object)
            transaction.commit()
            abstract_mbox = AbstractMailbox.get(id=abstract_mbox.id)
       
        if len(mails):
            [import_email(abstract_mbox, message_data) for message_data in mails]
            
            #We imported mails, we need to re-thread
            emails = Email.db().query(Email).filter(
                    Email.discussion_id == discussion_id,
                    ).options(joinedload_all(Email.parent))

            AbstractMailbox.thread_mails(emails)
            transaction.commit()

class Email(ImportedPost):
    """
    An Email refers to an email message that was imported from an AbstractMailbox.
    """
    __tablename__ = "email"

    id = Column(Integer, ForeignKey(
        'imported_post.id',
        ondelete='CASCADE',
        onupdate='CASCADE'
    ), primary_key=True)

    # in virtuoso, varchar is 1024 bytes and sizeof(wchar)==4, so varchar is 256 chars
    recipients = deferred(Column(UnicodeText, nullable=False), group='raw_details')
    sender = deferred(Column(Unicode(), nullable=False), group='raw_details')

    full_message = deferred(Column(Binary), group='raw_details')

    in_reply_to = Column(Unicode())

    __mapper_args__ = {
        'polymorphic_identity': 'email',
    }

    def __init__(self, *args, **kwargs):
        super(Email, self).__init__(*args, **kwargs)

    def REWRITEMEreply(self, sender, response_body):
        """
        Send a response to this email.

        `sender` is a user instance.
        `response` is a string.
        """

        sent_from = ' '.join([
            "%(sender_name)s on Assembl" % {
                "sender_name": sender.display_name()
            },
            "<%(sender_email)s>" % {
                "sender_email": sender.get_preferred_email(),
            }
        ])

        if type(response_body) == 'str':
            response_body = response_body.decode('utf-8')

        recipients = self.recipients

        message = MIMEMultipart('alternative')
        message['Subject'] = Header(self.subject, 'utf-8')
        message['From'] = sent_from

        message['To'] = self.recipients
        message.add_header('In-Reply-To', self.message_id)

        plain_text_body = response_body
        html_body = response_body

        # TODO: The plain text and html parts of the email should be different,
        # but we'll see what we can get from the front-end.

        plain_text_part = MIMEText(
            plain_text_body.encode('utf-8'),
            'plain',
            'utf-8'
        )

        html_part = MIMEText(
            html_body.encode('utf-8'),
            'html',
            'utf-8'
        )

        message.attach(plain_text_part)
        message.attach(html_part)

        smtp_connection = smtplib.SMTP(
            get_current_registry().settings['mail.host']
        )

        smtp_connection.sendmail(
            sent_from,
            recipients,
            message.as_string()
        )

        smtp_connection.quit()

    def __repr__(self):
        return "<Email '%s to %s'>" % (
            self.sender.encode('utf-8'),
            self.recipients.encode('utf-8')
        )

    def get_title(self):
        return self.source.mangle_mail_subject(self.subject)
