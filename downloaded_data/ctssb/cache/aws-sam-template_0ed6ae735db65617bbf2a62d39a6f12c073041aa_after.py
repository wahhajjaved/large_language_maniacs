"""
*  [2019] Zettant Incorporated
*  All Rights Reserved.
*
* NOTICE:  All information contained herein is, and remains
* the property of Zettant Incorporated and its suppliers,
* if any.  The intellectual and technical concepts contained
* herein are proprietary to Zettant Incorporated and its
* suppliers and may be covered by Japan. and Foreign Patents,
* patents in process, and are protected by trade secret or
* copyright law. Dissemination of this information or
* reproduction of this material is strictly forbidden unless
* prior written permission is obtained from Zettant Incorporated.
"""

import sys
import os
import boto3
import json
from argparse import ArgumentParser


def parser():
    usage = 'python {} [-f filepath] [-e dev|prod] [-l LambdaFunctionName in env.json] [-a VAL_name] [-v value] [-d VAL_name] [--help]'.format(__file__)
    argparser = ArgumentParser(usage=usage)
    argparser.add_argument('-f', '--filepath', type=str, default="./env.json", help='file path of env.json')
    argparser.add_argument('-e', '--env', type=str, help='env name (dev/prod)')
    argparser.add_argument('-l', '--lambda_function', type=str, help='Lambda function name in env.json')
    argparser.add_argument('-a', '--add', type=str, help='add Environment valuable with this name')
    argparser.add_argument('-d', '--delete', type=str, help='del Environment valuable with this name')
    argparser.add_argument('-v', '--value', type=str, help='Environment valuable to add')
    argparser.add_argument('-s', '--show', action='store_true', help='show configuration of the lambda')
    args = argparser.parse_args()
    return args


def _get_lambda_name(env, name, filepath="env.json"):
    if not os.path.exists(filepath):
        print("# no such file")
        return None

    with open(filepath, "r") as f:
        dat = f.read()
    envjson = json.loads(dat)
    try:
        lmb = envjson[env]['lambda'][name]
    except:
        print("# no such function_name")
        return None

    return envjson[env]["profile_name"], lmb.split(":")[-1]


def get_function_configuration(env, name, filepath="env.json"):
    profile_name, lambda_name = _get_lambda_name(env, name, filepath)
    session = boto3.Session(profile_name=profile_name)
    response = session.client('lambda').get_function_configuration(FunctionName=lambda_name)
    return response["Environment"]["Variables"]


def set_configuration(env, name, variables, filepath="env.json"):
    profile_name, lambda_name = _get_lambda_name(env, name, filepath)
    session = boto3.Session(profile_name=profile_name)
    response = session.client('lambda').update_function_configuration(
        FunctionName=lambda_name,
        Environment={"Variables": variables}
    )
    return response


if __name__ == '__main__':
    argresult = parser()
    if argresult.env is None or argresult.lambda_function is None:
        print("# -e and -l are mandatory!")
        sys.exit(1)

    env_values = get_function_configuration(argresult.env, argresult.lambda_function, argresult.filepath)
    if argresult.show:
        if env_values is not None:
            import pprint
            pprint.pprint(env_values)
        sys.exit(0)

    if argresult.delete:
        if argresult.delete not in env_values:
            print("# no such environment valuable is registered")
            sys.exit(1)
        del env_values[argresult.delete]

    if argresult.add:
        if argresult.value is None or argresult.value == "":
            print("# -v is required for -a (addition)")
            sys.exit(1)
        env_values[argresult.add] = argresult.value

    resp = set_configuration(argresult.env, argresult.lambda_function, env_values, argresult.filepath)
    print("# result =", resp['LastUpdateStatus'])

    env_values = get_function_configuration(argresult.env, argresult.lambda_function, argresult.filepath)
    import pprint
    pprint.pprint(env_values)
