#!/usr/bin/python
"""
Arguments:

    queue       queue to consume messages from

if message['ciphertext'], TKLAMQ_SECRET will be used as decryption key
"""

import os
import sys

from crypto import decrypt
from amqp import __doc__ as env_doc
from amqp import connect

def usage():
    print >> sys.stderr, "Syntax: %s <queue>" % sys.argv[0]
    print >> sys.stderr, __doc__, env_doc
    sys.exit(1)

def fatal(s):
    print >> sys.stderr, "error: " + str(s)
    sys.exit(1)

def decrypt_callback(message_data, message):
    if message_data.has_key('ciphertext'):
        secret = os.getenv('TKLAMQ_SECRET', None)
        if not secret:
            fatal('TKLAMQ_SECRET not specified, cannot decrypt ciphertext')
        print decrypt(str(message_data['ciphertext']), secret)

    else:
        print message_data

    message.ack()

def main():
    if not len(sys.argv) == 2:
        usage()

    queue = sys.argv[1]
    
    conn = connect()
    conn.consume(queue, callback=decrypt_callback)

if __name__ == "__main__":
    main()

