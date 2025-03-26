#!/usr/local/bin/python3

from pprint import pprint
from boto import ec2
from boto.exception import EC2ResponseError
from queue import Queue
import socket, sys, os, threading, time, logging, argparse

# Config vars.
ascender_address = "127.0.0.1"
ascender_port = 6030
query_threads = 8
ascend_threads = 2
# General vars / objects.
q_query = Queue()
q_ascend = Queue()

# Logging config.
log = logging.getLogger()
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter(fmt='%(asctime)s | %(levelname)s | %(message)s'))
log.addHandler(handler)
log.setLevel(logging.INFO)

# Break if not set.
for i in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
    try:
        os.environ[i]
    except KeyError:
        log.error("Environment variable %s must be set" % i)
        sys.exit(1)
# Assign.
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']

# Args.
parser = argparse.ArgumentParser(description='Queries AWS info and writes to Ascender.\
    Requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables to be set\
    for the respective AWS account to query.')
parser.add_argument('--regions', required=True, type=str,
    help='Comma delimited list of regions to query. \
    Example: --regions="us-west-2,us-west-1". \
    Query all available regions with --regions="all"')
args = parser.parse_args()


def stringify(input):
    """Iterates over dict and converts k/v pairs to strings (excluding ints)."""
    if isinstance(input, dict):
        return dict((stringify(key), stringify(value)) for key, value in input.items())
    elif isinstance(input, list):
        return [stringify(element) for element in input]
    elif type(input) == int:
        return input
    else:
        return str(input)

def ascend():
    """Sends message to Ascender."""
    while True:
        msg = q_ascend.get()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ascender_address, ascender_port))
        s.sendall(bytes(msg, 'UTF-8'))
        while 1:
            resp = s.recv(256)
            if resp != b'':
                continue
                #print("%s" % resp.decode("utf-8").rstrip())
            else:
                resp += s.recv(256)
                break
        s.close()
        q_ascend.task_done()

def query_region():
    """Pulls EC2 and EBS metadata from region and combines/filters."""
    # Pull region from queue and handle.
    while True:
        region = q_query.get()
        log.info("%s - querying" % region)
        t_start = time.time()
        done = False
        try:
            ec2conn = ec2.connect_to_region(region,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        except:
            q_query.task_done()
            break

        # Get EBS data.
        try:
            vols = ec2conn.get_all_volumes()
        except:
            q_query.task_done()
            break

        # Create array with volume dictionaries.
        volumes = []
        for i in vols:
            volumes.append(stringify(i.__dict__))

        for i in volumes:
            # Set type for Langolier.
            i['@type'] = "aws-ebs"

            # Format for Ascender.
            msg = str(i).replace("\'", "\"")
            # Write to Ascender.
            q_ascend.put(msg)

        # Get EC2 instances.
        try:
            reservations = ec2conn.get_all_instances()
        except:
            q_query.task_done()
            break
        instances = [i for r in reservations for i in r.instances]

        # Create dict for volume lookup by id to associate with instances.
        volume = {}
        for i in vols:
            volume[i.id] = i.__dict__

        # Pull instance data.
        for i in instances:
            meta = i.__dict__
            # Set type for Langolier.
            meta['@type'] = "aws-ec2"
            # Find EBS volumes associated with instance and add to 'vols' key.
            meta['vols'] = {}
            for i in meta['block_device_mapping'].keys():
                meta['vols'][i] = volume[meta['block_device_mapping'][i].volume_id]
            # Add a 'storage_total' (sum of all associated EBS size attributes) key.
            meta['storage_total'] = 0
            for i in meta['vols'].keys():
                meta['storage_total'] += meta['vols'][i]['size']

            # Format for Ascender.
            msg = str(stringify(meta)).replace("\'", "\"")
            # Write to Ascender.
            q_ascend.put(msg)

        # Work done for region.
        t_delta = round(time.time() - t_start, 2)
        objects = len(volumes) + len(instances)
        log.info("%s - done: found %s objects in %s sec." % (region, objects, t_delta))
        q_query.task_done()


# Init query thread pool.
for i in range(query_threads):
    t = threading.Thread(target=query_region)
    t.daemon = True
    t.start()

# Init Ascender sending pool.
for i in range(ascend_threads):
    t = threading.Thread(target=ascend)
    t.daemon = True
    t.start()

def main():
    # Check if Ascender is reachable.
    s_test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((ascender_address, ascender_port))
    except:
        log.error("Ascender is not reachable at: %s:%d" % (ascender_address, ascender_port))
        sys.exit(1)
    # Sanity check regions arg.
    valid_regions = []
    for i in ec2.regions(): valid_regions.append((str(i).split(':')[1]))
    regions = args.regions.split(',')
    if regions[0] == "all":
        regions = valid_regions
    else:
        for i in regions:
            if i not in valid_regions:
                log.error('''Region invalid: '%s'. Valid regions: %s''' % (i, valid_regions))
                sys.exit(1)

    # Enqueue work.
    for r in regions: q_query.put(r)
    # Wait for pizza to cook.
    q_query.join()

if  __name__ =='__main__': main()
