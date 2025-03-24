import os
import re
import json
import argparse

from pybbox.client import BBoxClient, RPCError

def guess_json(p):
    if p in ('null', 'true', 'false'):
        p = json.loads(p)
    elif p.startswith('{') or p.startswith('['):
        p = json.loads(p)
    elif p.startswith('"'):
        p = json.loads(p)
    elif p.isdigit() or re.match(r'\-?\d+$', p):
        p = int(p)
    elif re.match(r'\-?\d*(\.\d+)?$', p):
        p = float(p)
    return p

def main(prog='bbox-rpc'):
    parser = argparse.ArgumentParser(
        prog=prog)

    parser.add_argument('srv_method',
                        type=str,
                        help='bbox service name::method')

    parser.add_argument('params',
                        type=str,
                        nargs='*',
                        help='bbox calling arguments')

    parser.add_argument('--connect',
                        type=str,
                        help='server to connect to, fallback to $BBOX_RPC_CONNECT')

    parser.add_argument('--pp',
                        type=bool,
                        default=True,
                        help='pretty print result')

    parser.add_argument('--retry',
                        type=int,
                        default=1,
                        help='retry on failure')

    parser.add_argument('--cert',
                        type=str,
                        help='client auth cert, fallback to $BBOX_RPC_CERT')

    args = parser.parse_args()

    srv, method = args.srv_method.split('::')
    params = [guess_json(p) for p in args.params]

    connect = args.connect or os.getenv('BBOX_RPC_CONNECT')
    assert connect, 'connect cannot be void'

    cert = args.cert or os.getenv('BBOX_RPC_CERT')
    client = BBoxClient(connect, cert=cert)
    try:
        r = client.request(srv, method, *params, retry=args.retry)
        if args.pp:
            print(json.dumps(r, indent=2, sort_keys=True))
        else:
            print(json.dumps(r))
    except RPCError as e:
        print(e.code)
        print(e.message)
