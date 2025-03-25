#!/usr/bin/env python
# Copyright (C) 2012 Humbug, Inc.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
try:
    import simplejson
except ImportError:
    import json as simplejson
import re
import time
import subprocess
import optparse
import os
import datetime
import textwrap
import signal
import logging
import hashlib
import tempfile
import random
import select

class CountingBackoff(object):
    def __init__(self, maximum_retries=10):
        self.number_of_retries = 0
        self.maximum_retries = maximum_retries

    def keep_going(self):
        return self.number_of_retries < self.maximum_retries

    def succeed(self):
        self.number_of_retries = 0

    def fail(self):
        self.number_of_retries = min(self.number_of_retries + 1,
                                     self.maximum_retries)

class RandomExponentialBackoff(CountingBackoff):
    def fail(self):
        self.number_of_retries = min(self.number_of_retries + 1,
                                     self.maximum_retries)
        # Exponential growth with ratio sqrt(2); compute random delay
        # between x and 2x where x is growing exponentially
        delay_scale = int(2 ** (self.number_of_retries / 2.0 - 1)) + 1
        delay = delay_scale + random.randint(1, delay_scale)
        message = "Sleeping for %ss [max %s] before retrying." % (delay, delay_scale * 2)
        try:
            logger.warning(message)
        except NameError:
            print message
        time.sleep(delay)

DEFAULT_SITE = "https://humbughq.com"

class States:
    Startup, HumbugToZephyr, ZephyrToHumbug, ChildSending = range(4)
CURRENT_STATE = States.Startup

def to_humbug_username(zephyr_username):
    if "@" in zephyr_username:
        (user, realm) = zephyr_username.split("@")
    else:
        (user, realm) = (zephyr_username, "ATHENA.MIT.EDU")
    if realm.upper() == "ATHENA.MIT.EDU":
        return user.lower() + "@mit.edu"
    return user.lower() + "|" + realm.upper() + "@mit.edu"

def to_zephyr_username(humbug_username):
    (user, realm) = humbug_username.split("@")
    if "|" not in user:
        return user.lower() + "@ATHENA.MIT.EDU"
    match_user = re.match(r'([a-zA-Z0-9_]+)\|(.+)', user)
    if not match_user:
        raise Exception("Could not parse Zephyr realm for cross-realm user %s" % (humbug_username,))
    return match_user.group(1).lower() + "@" + match_user.group(2).upper()

# Checks whether the pair of adjacent lines would have been
# linewrapped together, had they been intended to be parts of the same
# paragraph.  Our check is whether if you move the first word on the
# 2nd line onto the first line, the resulting line is either (1)
# significantly shorter than the following line (which, if they were
# in the same paragraph, should have been wrapped in a way consistent
# with how the previous line was wrapped) or (2) shorter than 60
# characters (our assumed minimum linewrapping threshhold for Zephyr)
# or (3) the first word of the next line is longer than this entire
# line.
def different_paragraph(line, next_line):
    words = next_line.split()
    return (len(line + " " + words[0]) < len(next_line) * 0.8 or
            len(line + " " + words[0]) < 50 or
            len(line) < len(words[0]))

# Linewrapping algorithm based on:
# http://gcbenison.wordpress.com/2011/07/03/a-program-to-intelligently-remove-carriage-returns-so-you-can-paste-text-without-having-it-look-awful/
def unwrap_lines(body):
    lines = body.split("\n")
    result = ""
    previous_line = lines[0]
    for line in lines[1:]:
        line = line.rstrip()
        if (re.match(r'^\W', line, flags=re.UNICODE)
            and re.match(r'^\W', previous_line, flags=re.UNICODE)):
            result += previous_line + "\n"
        elif (line == "" or
            previous_line == "" or
            re.match(r'^\W', line, flags=re.UNICODE) or
            different_paragraph(previous_line, line)):
            # Use 2 newlines to separate sections so that we
            # trigger proper Markdown processing on things like
            # bulleted lists
            result += previous_line + "\n\n"
        else:
            result += previous_line + " "
        previous_line = line
    result += previous_line
    return result

def send_humbug(zeph):
    message = {}
    if options.forward_class_messages:
        message["forged"] = "yes"
    message['type'] = zeph['type']
    message['time'] = zeph['time']
    message['sender'] = to_humbug_username(zeph['sender'])
    if "subject" in zeph:
        # Truncate the subject to the current limit in Humbug.  No
        # need to do this for stream names, since we're only
        # subscribed to valid stream names.
        message["subject"] = zeph["subject"][:60]
    if zeph['type'] == 'stream':
        # Forward messages sent to -c foo -i bar to stream bar subject "instance"
        if zeph["stream"] == "message":
            message['to'] = zeph['subject'].lower()
            message['subject'] = "instance %s" % (zeph['subject'],)
        elif zeph["stream"] == "tabbott-test5":
            message['to'] = zeph['subject'].lower()
            message['subject'] = "test instance %s" % (zeph['subject'],)
        else:
            message["to"] = zeph["stream"]
    else:
        message["to"] = zeph["recipient"]
    message['content'] = unwrap_lines(zeph['content'])

    if options.test_mode and options.site == DEFAULT_SITE:
        logger.debug("Message is: %s" % (str(message),))
        return {'result': "success"}

    return humbug_client.send_message(message)

def send_error_humbug(error_msg):
    message = {"type": "private",
               "sender": humbug_account_email,
               "to": humbug_account_email,
               "content": error_msg,
               }
    humbug_client.send_message(message)

current_zephyr_subs = set()
def zephyr_bulk_subscribe(subs):
    try:
        zephyr._z.subAll(subs)
    except IOError:
        # Since we haven't added the subscription to
        # current_zephyr_subs yet, we can just return (so that we'll
        # continue processing normal messages) and we'll end up
        # retrying the next time the bot checks its subscriptions are
        # up to date.
        logger.exception("Error subscribing to streams (will retry automatically):")
        logger.warning("Streams were: %s" % ([cls for cls, instance, recipient in subs],))
        return
    try:
        actual_zephyr_subs = [cls for (cls, _, _) in zephyr._z.getSubscriptions()]
    except IOError:
        logger.exception("Error getting current Zephyr subscriptions")
        # Don't add anything to current_zephyr_subs so that we'll
        # retry the next time we check for streams to subscribe to
        # (within 15 seconds).
        return
    for (cls, instance, recipient) in subs:
        if cls not in actual_zephyr_subs:
            logger.error("Zephyr failed to subscribe us to %s; will retry" % (cls,))
            try:
                # We'll retry automatically when we next check for
                # streams to subscribe to (within 15 seconds), but
                # it's worth doing 1 retry immediately to avoid
                # missing 15 seconds of messages on the affected
                # classes
                zephyr._z.sub(cls, instance, recipient)
            except IOError:
                pass
        else:
            current_zephyr_subs.add(cls)

def update_subscriptions():
    try:
        f = file("/home/humbug/public_streams", "r")
        public_streams = simplejson.loads(f.read())
        f.close()
    except:
        logger.exception("Error reading public streams:")
        return

    classes_to_subscribe = set()
    for stream in public_streams:
        zephyr_class = stream.encode("utf-8")
        if (options.shard is not None and
            not hashlib.sha1(zephyr_class).hexdigest().startswith(options.shard)):
            # This stream is being handled by a different zephyr_mirror job.
            continue
        if zephyr_class in current_zephyr_subs:
            continue
        classes_to_subscribe.add((zephyr_class, "*", "*"))

    if len(classes_to_subscribe) > 0:
        zephyr_bulk_subscribe(list(classes_to_subscribe))

def maybe_kill_child():
    try:
        if child_pid is not None:
            os.kill(child_pid, signal.SIGTERM)
    except OSError:
        # We don't care if the child process no longer exists, so just log the error
        logger.exception("")

def maybe_restart_mirroring_script():
    if os.stat(os.path.join(options.root_path, "stamps", "restart_stamp")).st_mtime > start_time or \
            ((options.user == "tabbott" or options.user == "tabbott/extra") and
             os.stat(os.path.join(options.root_path, "stamps", "tabbott_stamp")).st_mtime > start_time):
        logger.warning("")
        logger.warning("zephyr mirroring script has been updated; restarting...")
        maybe_kill_child()
        try:
            zephyr._z.cancelSubs()
        except IOError:
            # We don't care whether we failed to cancel subs properly, but we should log it
            logger.exception("")
        while True:
            try:
                os.execvp(os.path.join(options.root_path, "user_root", "zephyr_mirror_backend.py"), sys.argv)
            except Exception:
                logger.exception("Error restarting mirroring script; trying again... Traceback:")
                time.sleep(1)

def process_loop(log):
    restart_check_count = 0
    last_check_time = time.time()
    while True:
        select.select([zephyr._z.getFD()], [], [], 15)
        try:
            notice = zephyr.receive(block=False)
        except Exception:
            logger.exception("Error checking for new zephyrs:")
            time.sleep(1)
            continue
        if notice is not None:
            try:
                process_notice(notice, log)
            except Exception:
                logger.exception("Error relaying zephyr:")
                time.sleep(2)

        if time.time() - last_check_time > 15:
            last_check_time = time.time()
            try:
                maybe_restart_mirroring_script()
                if restart_check_count > 0:
                    logger.info("Stopped getting errors checking whether restart is required.")
                    restart_check_count = 0
            except Exception:
                if restart_check_count < 5:
                    logger.exception("Error checking whether restart is required:")
                    restart_check_count += 1

            if options.forward_class_messages:
                try:
                    update_subscriptions()
                except Exception:
                    logger.exception("Error updating subscriptions from Humbug:")

def parse_zephyr_body(zephyr_data):
    try:
        (zsig, body) = zephyr_data.split("\x00", 1)
    except ValueError:
        (zsig, body) = ("", zephyr_data)
    return (zsig, body)

def process_notice(notice, log):
    (zsig, body) = parse_zephyr_body(notice.message)
    is_personal = False
    is_huddle = False

    if notice.opcode == "PING":
        # skip PING messages
        return

    zephyr_class = notice.cls.lower()

    if notice.recipient != "":
        is_personal = True
    # Drop messages not to the listed subscriptions
    if is_personal and not options.forward_personals:
        return
    if (zephyr_class not in current_zephyr_subs) and not is_personal:
        logger.debug("Skipping ... %s/%s/%s" %
                     (zephyr_class, notice.instance, is_personal))
        return
    if notice.format.startswith("Zephyr error: See") or notice.format.endswith("@(@color(blue))"):
        logger.debug("Skipping message we got from Humbug!")
        return

    if is_personal:
        if body.startswith("CC:"):
            is_huddle = True
            # Map "CC: sipbtest espuser" => "starnine@mit.edu,espuser@mit.edu"
            huddle_recipients = [to_humbug_username(x.strip()) for x in
                                 body.split("\n")[0][4:].split()]
            if notice.sender not in huddle_recipients:
                huddle_recipients.append(to_humbug_username(notice.sender))
            body = body.split("\n", 1)[1]

    zeph = { 'time'      : str(notice.time),
             'sender'    : notice.sender,
             'zsig'      : zsig,  # logged here but not used by app
             'content'   : body }
    if is_huddle:
        zeph['type'] = 'private'
        zeph['recipient'] = huddle_recipients
    elif is_personal:
        zeph['type'] = 'private'
        zeph['recipient'] = to_humbug_username(notice.recipient)
    else:
        zeph['type'] = 'stream'
        zeph['stream'] = zephyr_class
        if notice.instance.strip() != "":
            zeph['subject'] = notice.instance
        else:
            zeph["subject"] = '(instance "%s")' % (notice.instance,)

    # Add instances in for instanced personals
    if is_personal:
        if notice.cls.lower() != "message" and notice.instance.lower != "personal":
            heading = "[-c %s -i %s]\n" % (notice.cls, notice.instance)
        elif notice.cls.lower() != "message":
            heading = "[-c %s]\n" % (notice.cls,)
        elif notice.instance.lower() != "personal":
            heading = "[-i %s]\n" % (notice.instance,)
        else:
            heading = ""
        zeph["content"] = heading + zeph["content"]

    zeph = decode_unicode_byte_strings(zeph)

    logger.info("Received a message on %s/%s from %s..." %
                (zephyr_class, notice.instance, notice.sender))
    if log is not None:
        log.write(simplejson.dumps(zeph) + '\n')
        log.flush()

    if os.fork() == 0:
        global CURRENT_STATE
        CURRENT_STATE = States.ChildSending
        # Actually send the message in a child process, to avoid blocking.
        try:
            res = send_humbug(zeph)
            if res.get("result") != "success":
                logger.error("Error relaying zephyr:\n%s\n%s" % (zeph, res))
        except Exception:
            logger.exception("Error relaying zephyr:")
        finally:
            os._exit(0)

def decode_unicode_byte_strings(zeph):
    for field in zeph.keys():
        if isinstance(zeph[field], str):
            try:
                decoded = zeph[field].decode("utf-8")
            except Exception:
                decoded = zeph[field].decode("iso-8859-1")
            zeph[field] = decoded
    return zeph

def quit_failed_initialization(message):
    logger.error(message)
    maybe_kill_child()
    sys.exit(1)

def zephyr_init_autoretry():
    backoff = RandomExponentialBackoff()
    while backoff.keep_going():
        try:
            # zephyr.init() tries to clear old subscriptions, and thus
            # sometimes gets a SERVNAK from the server
            zephyr.init()
            backoff.succeed()
            return
        except IOError:
            logger.exception("Error initializing Zephyr library (retrying).  Traceback:")
            backoff.fail()

    quit_failed_initialization("Could not initialize Zephyr library, quitting!")

def zephyr_subscribe_autoretry(sub):
    backoff = RandomExponentialBackoff()
    while backoff.keep_going():
        try:
            zephyr.Subscriptions().add(sub)
            backoff.succeed()
            return
        except IOError:
            # Probably a SERVNAK from the zephyr server, but log the
            # traceback just in case it's something else
            logger.exception("Error subscribing to personals (retrying).  Traceback:")
            backoff.fail()

    quit_failed_initialization("Could not subscribe to personals, quitting!")

def zephyr_to_humbug(options):
    zephyr_init_autoretry()
    if options.forward_class_messages:
        update_subscriptions()
    if options.forward_personals:
        # Subscribe to personals; we really can't operate without
        # those subscriptions, so just retry until it works.
        zephyr_subscribe_autoretry(("message", "*", "%me%"))
        if subscribed_to_mail_messages():
            zephyr_subscribe_autoretry(("mail", "inbox", "%me%"))

    if options.resend_log_path is not None:
        with open(options.resend_log_path, 'r') as log:
            for ln in log:
                try:
                    zeph = simplejson.loads(ln)
                    # New messages added to the log shouldn't have any
                    # elements of type str (they should already all be
                    # unicode), but older messages in the log are
                    # still of type str, so convert them before we
                    # send the message
                    zeph = decode_unicode_byte_strings(zeph)
                    # Handle importing older zephyrs in the logs
                    # where it isn't called a "stream" yet
                    if "class" in zeph:
                        zeph["stream"] = zeph["class"]
                    if "instance" in zeph:
                        zeph["subject"] = zeph["instance"]
                    logger.info("sending saved message to %s from %s..." %
                                (zeph.get('stream', zeph.get('recipient')),
                                 zeph['sender']))
                    send_humbug(zeph)
                except Exception:
                    logger.exception("Could not send saved zephyr:")
                    time.sleep(2)

    logger.info("Successfully initialized; Starting receive loop.")

    if options.log_path is not None:
        with open(options.log_path, 'a') as log:
            process_loop(log)
    else:
        process_loop(None)

def send_zephyr(zwrite_args, content):
    p = subprocess.Popen(zwrite_args, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate(input=content.encode("utf-8"))
    if p.returncode:
        logger.error("zwrite command '%s' failed with return code %d:" % (
            " ".join(zwrite_args), p.returncode,))
        if stdout:
            logger.info("stdout: " + stdout)
    elif stderr:
        logger.warning("zwrite command '%s' printed the following warning:" % (
            " ".join(zwrite_args),))
    if stderr:
        logger.warning("stderr: " + stderr)
    return (p.returncode, stderr)

def send_authed_zephyr(zwrite_args, content):
    return send_zephyr(zwrite_args, content)

def send_unauthed_zephyr(zwrite_args, content):
    return send_zephyr(zwrite_args + ["-d"], content)

def forward_to_zephyr(message):
    wrapper = textwrap.TextWrapper(break_long_words=False, break_on_hyphens=False)
    wrapped_content = "\n".join("\n".join(wrapper.wrap(line))
            for line in message["content"].split("\n"))

    zwrite_args = ["zwrite", "-n", "-s", zsig_fullname, "-F", "Zephyr error: See http://zephyr.1ts.org/wiki/df"]
    if message['type'] == "stream":
        zephyr_class = message["display_recipient"]
        instance = message["subject"]

        match_whitespace_instance = re.match(r'^\(instance "(\s*)"\)$', instance)
        if match_whitespace_instance:
            # Forward messages sent to '(instance "WHITESPACE")' back to the
            # appropriate WHITESPACE instance for bidirectional mirroring
            instance = match_whitespace_instance.group(1)
        elif (instance == "instance %s" % (zephyr_class,) or
            instance == "test instance %s" % (zephyr_class,)):
            # Forward messages to e.g. -c -i white-magic back from the
            # place we forward them to
            if instance.startswith("test"):
                instance = zephyr_class
                zephyr_class = "tabbott-test5"
            else:
                instance = zephyr_class
                zephyr_class = "message"
        zwrite_args.extend(["-c", zephyr_class, "-i", instance])
        logger.info("Forwarding message to class %s, instance %s" % (zephyr_class, instance))
    elif message['type'] == "private":
        if len(message['display_recipient']) == 1:
            recipient = to_zephyr_username(message["display_recipient"][0]["email"])
            recipients = [recipient]
        elif len(message['display_recipient']) == 2:
            recipient = ""
            for r in message["display_recipient"]:
                if r["email"].lower() != humbug_account_email.lower():
                    recipient = to_zephyr_username(r["email"])
                    break
            recipients = [recipient]
        else:
            zwrite_args.extend(["-C"])
            # We drop the @ATHENA.MIT.EDU here because otherwise the
            # "CC: user1 user2 ..." output will be unnecessarily verbose.
            recipients = [to_zephyr_username(user["email"]).replace("@ATHENA.MIT.EDU", "")
                          for user in message["display_recipient"]]
        logger.info("Forwarding message to %s" % (recipients,))
        zwrite_args.extend(recipients)

    if options.test_mode:
        logger.debug("Would have forwarded: %s\n%s" %
                     (zwrite_args, wrapped_content.encode("utf-8")))
        return

    heading = "Hi there! This is an automated message from Humbug."
    support_closing = """If you have any questions, please be in touch through the \
Feedback tab or at support@humbughq.com."""

    (code, stderr) = send_authed_zephyr(zwrite_args, wrapped_content)
    if code == 0 and stderr == "":
        return
    elif code == 0:
        return send_error_humbug("""%s

Your last message was successfully mirrored to zephyr, but zwrite \
returned the following warning:

%s

%s""" % (heading, stderr, support_closing))
    elif code != 0 and (stderr.startswith("zwrite: Ticket expired while sending notice to ") or
                        stderr.startswith("zwrite: No credentials cache found while sending notice to ")):
        # Retry sending the message unauthenticated; if that works,
        # just notify the user that they need to renew their tickets
        (code, stderr) = send_unauthed_zephyr(zwrite_args, wrapped_content)
        if code == 0:
            return send_error_humbug("""%s

Your last message was forwarded from Humbug to Zephyr unauthenticated, \
because your Kerberos tickets have expired. It was sent successfully, \
but please renew your Kerberos tickets in the screen session where you \
are running the Humbug-Zephyr mirroring bot, so we can send \
authenticated Zephyr messages for you again.

%s""" % (heading, support_closing))

    # zwrite failed and it wasn't because of expired tickets: This is
    # probably because the recipient isn't subscribed to personals,
    # but regardless, we should just notify the user.
    return send_error_humbug("""%s

Your Humbug-Zephyr mirror bot was unable to forward that last message \
from Humbug to Zephyr. That means that while Humbug users (like you) \
received it, Zephyr users did not.  The error message from zwrite was:

%s

%s""" % (heading, stderr, support_closing))

def maybe_forward_to_zephyr(message):
    if (message["sender_email"] == humbug_account_email):
        if not ((message["type"] == "stream") or
                (message["type"] == "private" and
                 False not in [u["email"].lower().endswith("mit.edu") for u in
                               message["display_recipient"]])):
            # Don't try forward private messages with non-MIT users
            # to MIT Zephyr.
            return
        timestamp_now = datetime.datetime.now().strftime("%s")
        if float(message["timestamp"]) < float(timestamp_now) - 15:
            logger.warning("Skipping out of order message: %s < %s" %
                           (message["timestamp"], timestamp_now))
            return
        try:
            forward_to_zephyr(message)
        except Exception:
            # Don't let an exception forwarding one message crash the
            # whole process
            logger.exception("Error forwarding message:")

def humbug_to_zephyr(options):
    # Sync messages from zephyr to humbug
    logger.info("Starting syncing messages.")
    while True:
        try:
            humbug_client.call_on_each_message(maybe_forward_to_zephyr)
        except Exception:
            logger.exception("Error syncing messages:")
            time.sleep(1)

def subscribed_to_mail_messages():
    # In case we have lost our AFS tokens and those won't be able to
    # parse the Zephyr subs file, first try reading in result of this
    # query from the environment so we can avoid the filesystem read.
    stored_result = os.environ.get("HUMBUG_FORWARD_MAIL_ZEPHYRS")
    if stored_result is not None:
        return stored_result == "True"
    for (cls, instance, recipient) in parse_zephyr_subs(verbose=False):
        if (cls.lower() == "mail" and instance.lower() == "inbox"):
            os.environ["HUMBUG_FORWARD_MAIL_ZEPHYRS"] = "True"
            return True
    os.environ["HUMBUG_FORWARD_MAIL_ZEPHYRS"] = "False"
    return False

def add_humbug_subscriptions(verbose):
    zephyr_subscriptions = set()
    skipped = set()
    for (cls, instance, recipient) in parse_zephyr_subs(verbose=verbose):
        if cls.lower() == "message":
            if recipient != "*":
                # We already have a (message, *, you) subscription, so
                # these are redundant
                continue
            # We don't support subscribing to (message, *)
            if instance == "*":
                if recipient == "*":
                    skipped.add((cls, instance, recipient, "subscribing to all of class message is not supported."))
                continue
            # If you're on -i white-magic on zephyr, get on stream white-magic on humbug
            # instead of subscribing to stream "message" on humbug
            zephyr_subscriptions.add(instance)
            continue
        elif cls.lower() == "mail" and instance.lower() == "inbox":
            # We forward mail zephyrs, so no need to log a warning.
            continue
        elif len(cls) > 30:
            skipped.add((cls, instance, recipient, "Class longer than 30 characters"))
            continue
        elif instance != "*":
            skipped.add((cls, instance, recipient, "Unsupported non-* instance"))
            continue
        elif recipient != "*":
            skipped.add((cls, instance, recipient, "Unsupported non-* recipient."))
            continue
        zephyr_subscriptions.add(cls)

    if len(zephyr_subscriptions) != 0:
        res = humbug_client.add_subscriptions(list(zephyr_subscriptions))
        if res.get("result") != "success":
            logger.error("Error subscribing to streams:\n%s" % (res["msg"],))
            return

        already = res.get("already_subscribed")
        new = res.get("subscribed")
        if verbose:
            if already is not None and len(already) > 0:
                logger.info("\nAlready subscribed to: %s" % (", ".join(already.values()[0]),))
            if new is not None and len(new) > 0:
                logger.info("\nSuccessfully subscribed to: %s" % (", ".join(new.values()[0]),))

    if len(skipped) > 0:
        if verbose:
            logger.info("\n" + "\n".join(textwrap.wrap("""\
You have some lines in ~/.zephyr.subs that could not be
synced to your Humbug subscriptions because they do not
use "*" as both the instance and recipient and not one of
the special cases (e.g. personals and mail zephyrs) that
Humbug has a mechanism for forwarding.  Humbug does not
allow subscribing to only some subjects on a Humbug
stream, so this tool has not created a corresponding
Humbug subscription to these lines in ~/.zephyr.subs:
""")) + "\n")

    for (cls, instance, recipient, reason) in skipped:
        if verbose:
            if reason != "":
                logger.info("  [%s,%s,%s] (%s)" % (cls, instance, recipient, reason))
            else:
                logger.info("  [%s,%s,%s]" % (cls, instance, recipient))
    if len(skipped) > 0:
        if verbose:
            logger.info("\n" + "\n".join(textwrap.wrap("""\
If you wish to be subscribed to any Humbug streams related
to these .zephyrs.subs lines, please do so via the Humbug
web interface.
""")) + "\n")
    if verbose:
        logger.info("\nIMPORTANT: Please reload the Humbug app for these changes to take effect.\n")

def valid_stream_name(name):
    return name != ""

def parse_zephyr_subs(verbose=False):
    zephyr_subscriptions = set()
    subs_file = os.path.join(os.environ["HOME"], ".zephyr.subs")
    if not os.path.exists(subs_file):
        if verbose:
            logger.error("Couldn't find ~/.zephyr.subs!")
        return []

    for line in file(subs_file, "r").readlines():
        line = line.strip()
        if len(line) == 0:
            continue
        try:
            (cls, instance, recipient) = line.split(",")
            cls = cls.replace("%me%", options.user)
            instance = instance.replace("%me%", options.user)
            recipient = recipient.replace("%me%", options.user)
            if not valid_stream_name(cls):
                if verbose:
                    logger.error("Skipping subscription to unsupported class name: [%s]" % (line,))
                continue
        except Exception:
            if verbose:
                logger.error("Couldn't parse ~/.zephyr.subs line: [%s]" % (line,))
            continue
        zephyr_subscriptions.add((cls.strip(), instance.strip(), recipient.strip()))
    return zephyr_subscriptions

def fetch_fullname(username):
    try:
        proc = subprocess.Popen(['hesinfo', username, 'passwd'],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, _err_unused = proc.communicate()
        if proc.returncode == 0:
            return out.split(':')[4].split(',')[0]
    except Exception:
        logger.exception("Error getting fullname for %s:" % (username,))

    return username

def open_logger():
    if options.forward_class_messages:
        if options.test_mode:
            log_file = "/home/humbug/test-mirror-log"
        else:
            log_file = "/home/humbug/mirror-log"
    else:
        f = tempfile.NamedTemporaryFile(prefix="humbug-log.%s." % (options.user,),
                                        delete=False)
        log_file = f.name
        # Close the file descriptor, since the logging system will
        # reopen it anyway.
        f.close()
    logger = logging.getLogger(__name__)
    log_format = "%(asctime)s <initial>: %(message)s"
    formatter = logging.Formatter(log_format)
    logging.basicConfig(format=log_format)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

def configure_logger(logger, direction_name):
    if direction_name is None:
        log_format = "%(message)s"
    else:
        log_format = "%(asctime)s [" + direction_name + "] %(message)s"
    formatter = logging.Formatter(log_format)

    # Replace the formatters for the file and stdout loggers
    for handler in logger.handlers:
        handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

def parse_args():
    parser = optparse.OptionParser()
    parser.add_option('--forward-class-messages',
                      default=False,
                      help=optparse.SUPPRESS_HELP,
                      action='store_true')
    parser.add_option('--shard',
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--noshard',
                      default=False,
                      help=optparse.SUPPRESS_HELP,
                      action='store_true')
    parser.add_option('--resend-log',
                      dest='resend_log_path',
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--enable-log',
                      dest='log_path',
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--no-forward-personals',
                      dest='forward_personals',
                      help=optparse.SUPPRESS_HELP,
                      default=True,
                      action='store_false')
    parser.add_option('--no-forward-from-humbug',
                      default=True,
                      dest='forward_from_humbug',
                      help=optparse.SUPPRESS_HELP,
                      action='store_false')
    parser.add_option('--verbose',
                      default=False,
                      help=optparse.SUPPRESS_HELP,
                      action='store_true')
    parser.add_option('--sync-subscriptions',
                      default=False,
                      action='store_true')
    parser.add_option('--site',
                      default=DEFAULT_SITE,
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--user',
                      default=os.environ["USER"],
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--root-path',
                      default="/afs/athena.mit.edu/user/t/a/tabbott/for_friends",
                      help=optparse.SUPPRESS_HELP)
    parser.add_option('--test-mode',
                      default=False,
                      help=optparse.SUPPRESS_HELP,
                      action='store_true')
    parser.add_option('--api-key-file',
                      default=os.path.join(os.environ["HOME"], "Private", ".humbug-api-key"))
    return parser.parse_args()

def die_gracefully(signal, frame):
    if CURRENT_STATE == States.HumbugToZephyr or CURRENT_STATE == States.ChildSending:
        # this is a child process, so we want os._exit (no clean-up necessary)
        os._exit(1)

    if CURRENT_STATE == States.ZephyrToHumbug:
        try:
            # zephyr=>humbug processes may have added subs, so run cancelSubs
            zephyr._z.cancelSubs()
        except IOError:
            # We don't care whether we failed to cancel subs properly, but we should log it
            logger.exception("")

    sys.exit(1)

if __name__ == "__main__":
    # Set the SIGCHLD handler back to SIG_DFL to prevent these errors
    # when importing the "requests" module after being restarted using
    # the restart_stamp functionality:
    #
    # close failed in file object destructor:
    # IOError: [Errno 10] No child processes
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)

    signal.signal(signal.SIGINT, die_gracefully)

    (options, args) = parse_args()

    logger = open_logger()
    configure_logger(logger, "parent")

    # The 'api' directory needs to go first, so that 'import humbug' won't pick
    # up some other directory named 'humbug'.
    pyzephyr_lib_path = "python-zephyr/build/lib.linux-" + os.uname()[4] + "-2.6/"
    sys.path[:0] = [os.path.join(options.root_path, 'api'),
                    options.root_path,
                    os.path.join(options.root_path, "python-zephyr"),
                    os.path.join(options.root_path, pyzephyr_lib_path)]

    # In case this is an automated restart of the mirroring script,
    # and we have lost AFS tokens, first try reading the API key from
    # the environment so that we can skip doing a filesystem read.
    if os.environ.get("HUMBUG_API_KEY") is not None:
        api_key = os.environ.get("HUMBUG_API_KEY")
    else:
        if not os.path.exists(options.api_key_file):
            logger.error("\n" + "\n".join(textwrap.wrap("""\
Could not find API key file.
You need to either place your api key file at %s,
or specify the --api-key-file option.""" % (options.api_key_file,))))
            sys.exit(1)
        api_key = file(options.api_key_file).read().strip()
        # Store the API key in the environment so that our children
        # don't need to read it in
        os.environ["HUMBUG_API_KEY"] = api_key

    humbug_account_email = options.user + "@mit.edu"
    import humbug
    humbug_client = humbug.Client(
        email=humbug_account_email,
        api_key=api_key,
        verbose=True,
        client="zephyr_mirror",
        site=options.site)

    start_time = time.time()

    if options.sync_subscriptions:
        configure_logger(logger, None)  # make the output cleaner
        logger.info("Syncing your ~/.zephyr.subs to your Humbug Subscriptions!")
        add_humbug_subscriptions(True)
        sys.exit(0)

    # Kill all zephyr_mirror processes other than this one and its parent.
    if not options.test_mode:
        pgrep_query = "/usr/bin/python.*zephyr_mirror"
        if options.shard is not None:
            pgrep_query = "%s.*--shard=%s" % (pgrep_query, options.shard)
        proc = subprocess.Popen(['pgrep', '-U', os.environ["USER"], "-f", pgrep_query],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, _err_unused = proc.communicate()
        for pid in map(int, out.split()):
            if pid == os.getpid() or pid == os.getppid():
                continue

            # Another copy of zephyr_mirror.py!  Kill it.
            logger.info("Killing duplicate zephyr_mirror process %s" % (pid,))
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                # We don't care if the target process no longer exists, so just log the error
                logger.exception("")

    if options.shard is not None and set(options.shard) != set("a"):
        # The shard that is all "a"s is the one that handles personals
        # forwarding and humbug => zephyr forwarding
        options.forward_personals = False
        options.forward_from_humbug = False

    if options.forward_from_humbug:
        child_pid = os.fork()
        if child_pid == 0:
            CURRENT_STATE = States.HumbugToZephyr
            # Run the humbug => zephyr mirror in the child
            configure_logger(logger, "humbug=>zephyr")
            zsig_fullname = fetch_fullname(options.user)
            humbug_to_zephyr(options)
            sys.exit(0)
    else:
        child_pid = None
    CURRENT_STATE = States.ZephyrToHumbug

    import zephyr
    logger_name = "zephyr=>humbug"
    if options.shard is not None:
        logger_name += "(%s)" % (options.shard,)
    configure_logger(logger, logger_name)
    # Have the kernel reap children for when we fork off processes to send Humbugs
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    zephyr_to_humbug(options)
