import argparse
import sys

import boto

from postman import __version__


def out(msg, args):
    if args.verbose:
        sys.stdout.write("%s\n" % msg)
        sys.stdout.flush()


def cmd_send(args):
    ses = boto.connect_ses()
    out("Sending mail to: %s" % ", ".join(args.destinations), args)
    msg = sys.stdin.read()
    r = ses.send_raw_email(args.f, msg, args.destinations)
    if r.get("SendRawEmailResponse", {}).get("SendRawEmailResult", {}).get("MessageId"):
        out("OK", args)
    else:
        out("ERROR: %s" % r, args)


def cmd_verify(args):
    ses = boto.connect_ses()
    for email in args.email:
        ses.verify_email_address(email)
        out("Verification for %s sent." % email, args)


def cmd_list_verified(args):
    ses = boto.connect_ses()
    args.verbose = True
    
    addresses = ses.list_verified_email_addresses()
    addresses = addresses["ListVerifiedEmailAddressesResponse"]
    addresses = addresses["ListVerifiedEmailAddressesResult"]
    addresses = addresses["VerifiedEmailAddresses"]
    
    if not addresses:
        out("No addresses are verified on this account.", args)
        return
    
    for address in addresses:
        out(address, args)


def cmd_show_quota(args):
    ses = boto.connect_ses()
    args.verbose= True
    
    data = ses.get_send_quota()["GetSendQuotaResponse"]["GetSendQuotaResult"]
    out("Max 24 Hour Send: %s" % data["Max24HourSend"], args)
    out("Sent Last 24 Hours: %s" % data["SentLast24Hours"], args)
    out("Max Send Rate: %s" % data["MaxSendRate"], args)


def cmd_show_stats(args):
    ses = boto.connect_ses()
    args.verbose = True
    
    data = ses.get_send_statistics()
    data = data["GetSendStatisticsResponse"]["GetSendStatisticsResult"]
    for datum in data["SendDataPoints"]:
        out("Complaints: %s" % datum["Complaints"], args)
        out("Timestamp: %s" % datum["Timestamp"], args)
        out("DeliveryAttempts: %s" % datum["DeliveryAttempts"], args)
        out("Bounces: %s" % datum["Bounces"], args)
        out("Rejects: %s" % datum["Rejects"], args)
        out("", args)


def cmd_delete_verified(args):
    ses = boto.connect_ses()
    for email in args.email:
        ses.delete_verified_email_address(email_address=email)
        out("Deleted %s" % email, args)


def main():
    parser = argparse.ArgumentParser(prog="postman", description="send an email via Amazon SES")
    parser.add_argument("--version", action="version", version="%%(prog)s %s" % __version__)
    parser.add_argument("--verbose", action="store_true")
    
    command_parsers = parser.add_subparsers(dest="command")
    
    # cmd: send
    parser_send = command_parsers.add_parser("send")
    parser_send.add_argument("-f",
        help="the address to send the message from, must be validated")
    parser_send.add_argument("destinations", metavar="TO", type=str, nargs="+",
        help="a list of email addresses to deliver message to")
    
    # cmd: verify
    parser_send = command_parsers.add_parser("verify")
    parser_send.add_argument("email", nargs="+",
        help="an email address to verify for sending from")
    
    # cmd: list_verified
    command_parsers.add_parser("list_verified")
    
    # cmd: show_quota
    command_parsers.add_parser("show_quota")
    
    # cmd: show_stats
    command_parsers.add_parser("show_stats")
    
    # cmd: delete_verified
    parser_delete = command_parsers.add_parser("delete_verified")
    parser_delete.add_argument("email", nargs="+",
        help="verified email addresses that will be deleted from verification list")
    
    args = parser.parse_args()
    
    {
        "send": cmd_send,
        "verify": cmd_verify,
        "list_verified": cmd_list_verified,
        "show_quota": cmd_show_quota,
        "show_stats": cmd_show_stats,
        "delete_verified": cmd_delete_verified
    }[args.command](args)
