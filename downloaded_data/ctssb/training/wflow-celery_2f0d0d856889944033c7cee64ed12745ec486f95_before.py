import json
import argparse
import logging
import os
import importlib
import wflowbackend.backendtasks as backendtasks
import wflowbackend.messaging as messaging
from flask import Flask, request, jsonify
log = logging.getLogger('process_server')

wflowlog = logging.getLogger('WFLOWSERVICELOG')

app = Flask('process_server')

def get_context():
    return json.load(open(app.config['context_file']))


def get_status():
    statusfile = app.config['status_file']
    try:
        with open(statusfile) as f:
            log.info('reading status')
            return json.load(f)
    except IOError:
        with open(statusfile,'w') as f:
            log.info('initial setup of statusfile %s', statusfile)
            data = {'success': False, 'ready': False}
            json.dump(data, f)
            return data

def set_status(ready = None, success = None):
    status_data = get_status()

    if ready: status_data['ready'] = ready
    if success: status_data['success'] = success

    statusfile = app.config['status_file']
    with open(statusfile,'w') as f:
        json.dump(status_data, f)
        return jsonify({'set_status': True})

@app.route('/readyz')
def readyz():
    return jsonify({})

@app.route('/context')
def context():
    return jsonify(get_context())

def setup_once():

    ctx = backendtasks.acquire_context(app.config['wflowid'])
    CONTEXTFILE = '.wflow_context'
    STATUSFILE = '.wflow_status'
    app.config['context_file'] = os.path.join(ctx['workdir'],CONTEXTFILE)
    app.config['status_file'] = os.path.join(ctx['workdir'],STATUSFILE)

    if os.path.exists(ctx['workdir']): #if we're setup, ignore
        wflowlog.info('workdir exists interactive session possibly reactivated -- not setting up')
        return

    wflowlog.info('setting up once')

    setupfunc = getattr(backendtasks,app.config['setupfunc'])
    setupfunc(ctx)

    log.info('declaring context and status files at %s %s',
             app.config['context_file'], app.config['status_file'])

    with open(app.config['context_file'],'w') as f:
        json.dump(ctx,f)

    try:
        pluginmodule,entrypoint = ctx['entry_point'].split(':')
        wflowlog.info('setting up entry point %s',ctx['entry_point'])
        m = importlib.import_module(pluginmodule)
        entry = getattr(m,entrypoint)
    except AttributeError:
        wflowlog.error('could not get entrypoint: %s',ctx['entry_point'])
        raise
    entry(ctx)

    log.info('one-time setup done')

@app.route('/finalize')
def finalize():
    ctx = get_context()
    try:
        log.info('finalizing')
        successfunc = getattr(backendtasks,app.config['successfunc'])
        successfunc(ctx)
        log.info('successfunc done')
    except:
        wflowlog.exception('something went wrong :(!')
    finally:
        teardownfunc = getattr(backendtasks,app.config['teardownfunc'])
        teardownfunc(ctx)
    return jsonify({'status': 'ok'})

@app.route('/status', methods = ['GET','POST'])
def status():
    if request.method == 'POST':
        set_status(request.json.get('success'), request.json.get('ready'))
        return jsonify({'set_status': True})
    else:
        return jsonify(get_status())


def main():
    logging.basicConfig(level = logging.INFO)
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('setupfunc', metavar='setupfunc', help='setup function')
    parser.add_argument('successfunc', metavar='successfunc', help='sucess exit function')
    parser.add_argument('teardownfunc', metavar='teardownfunc', help='exit/cleanup function (always called)')
    parser.add_argument('wflowid', metavar='wflowid', help='workflow id')
    parser.add_argument('--stream-logs', dest='stream_logs',  action="store_true", help='stream logging')

    args = parser.parse_args()
    app.config['wflowid'] = args.wflowid
    app.config['setupfunc'] = args.setupfunc
    app.config['successfunc'] = args.successfunc
    app.config['teardownfunc'] = args.teardownfunc
    log.info('starting server')

    messaging.setupLogging(args.wflowid, add_redis = args.stream_logs)

    wflowlog.info('setting up interactive session.')
    setup_once()
    wflowlog.info('interactive workflow started.')


    app.run(host='0.0.0.0', port=5000)
