#!/usr/bin/env python
import argparse
import os
import datetime
import boto.ec2
from botohelper import BotoHelper
from prettytable import PrettyTable
import loghelper as log

# initiate botohelper connection
bh = BotoHelper(os.environ.get('AWS_ACCESS_KEY_ID'), os.environ.get('AWS_SECRET_ACCESS_KEY'))
# boto.ec2 connection
conn = boto.ec2.EC2Connection()
# log helper library
log = log.logHelper("./aws-snapshots.log", useConsole=False)

# Arguments here provide simple configuration of day/week retention periods
parser = argparse.ArgumentParser(description='Delete your private snapshots in your AWS region')
parser.add_argument('-n', '--dry-run', action='store_true', dest='dry_run', default=False,
                    help="Perform a dry run")
parser.add_argument('-d', '--days', dest='days', nargs=1, type=int,
                    help="Retain 'x' days of snapshots", required=True)
parser.add_argument('-w', '--weeks', dest='weeks', nargs=1, type=int,
                    help="Retain 'x' weeks of snapshots", required=True)
args = parser.parse_args()


def main():
    # Define PrettyTable columns
    pt = PrettyTable(['Source Volume', 'Created', 'Snapshot Description', 'Status'])
    # Slide it on over to the left
    pt.align['Instance Name'] = "l"
    pt.padding_width = 1
    # Get all the snapshots owned by the current AWS account
    log.info("***** Connecting to Amazon EC2 *****")
    snapshots = conn.get_all_snapshots(owner="self")
    for snapshot in snapshots:
        # Get the current time
        current_time = datetime.datetime.now()
        # Get the timestamp when the snapshot was created
        start_time = datetime.datetime.strptime(snapshot.start_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        # If the snapshot creation time is older than 'x' weeks/days, delete it
        if start_time < current_time - datetime.timedelta(weeks=args.weeks[0], days=args.days[0]):
            try:
                log.info("Attempting to delete snapshot '%s'" % (snapshot.volume_id))
                del_snap = conn.delete_snapshot(snapshot.id, dry_run=args.dry_run)
                log.info("SUCCESS: The snapshot was deleted successfully.")
            except boto.exception.EC2ResponseError, ex:
                if ex.status == 403:
                    log.error("FORBIDDEN: " + ex.error_message)
                    del_snap = ex.reason.upper() + ": " + "Access denied."
                else:
                    del_snap = 'ERROR: ' + ex.error_message
            finally:
                del_snap = str(del_snap)
            # Shove that data into a new table row
            pt.add_row([snapshot.volume_id, snapshot.start_time, snapshot.description, del_snap])
    # Print the compiled table
    print pt

if __name__ == '__main__':
    main()
