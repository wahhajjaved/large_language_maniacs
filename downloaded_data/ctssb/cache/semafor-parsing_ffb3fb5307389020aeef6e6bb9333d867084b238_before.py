from __future__ import absolute_import

from semafor.master import settings
from semafor.master.worker.celery import app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

salt_bootstrap = '''#!/bin/bash

# Install saltstack
add-apt-repository ppa:saltstack/salt -y
apt-get update -y
apt-get install salt-minion -y
apt-get install salt-master -y
apt-get upgrade -y

# Set salt master location and start minion
sed -i 's/#master: salt/master: {0}/' /etc/salt/minion
salt-minion -d
'''


@app.task
def create_instances(n=1, sleep=10):
    '''
    Creates and provisions the minions instances
    Returns
    -------
    minion_ips : list of strings,
        each value is the private_dns_name of the instance
        with this values is possible to call methods using salt
    '''
    import boto
    import time
    import subprocess

    # Create EC2 instances
    logger.info('Creating EC2 instances')
    logger.info('1/4: Initializing EC2 instances')
    user_data = salt_bootstrap.format(settings.SALT_MASTER_PUBLIC_ADDRESS)
    conn = boto.connect_ec2(settings.AWS_ACCESS_ID, settings.AWS_SECRET_KEY)
    reservation = conn.run_instances(min_count=n, max_count=n, instance_type='m2.xlarge',
                                     image_id='ami-a73264ce', key_name='my_aws',
                                     placement='us-east-1a', user_data=user_data)
    instances = reservation.instances
    logger.info('1/4: Instances IDs:')
    logger.info(instances)

    logger.info('1/4: Waiting until all instances are running')
    running = []
    while len(running) < n:
        time.sleep(sleep)
        for instance in instances:
            minion_ip = instance.private_dns_name
            instance.update()
            if instance.state == u'running':
                if minion_ip not in running:
                    running.append(minion_ip)
                    logger.info('1/4: %i/%i instances running (new=%s)' % (len(running), n, minion_ip))
    logger.info('1/4: All instances running')
    minion_ips = [str(instance.private_dns_name) for instance in instances]
    logger.info('1/4: Minion IPs:')
    logger.info(minion_ips)

    # Instances are created wait until salt is boostraped and are connected to the master (this)
    logger.info('2/4: Waiting until all salt-minions are ready')
    ready = []
    while len(ready) < n:
        time.sleep(sleep)
        for instance in instances:
            minion_ip = instance.private_dns_name
            p = subprocess.Popen(['sudo', 'salt-key', '-L'], stdout=subprocess.PIPE)
            out, err = p.communicate()
            if instance.private_dns_name in out.split('\n'):
                if minion_ip not in ready:
                    ready.append(minion_ip)
                    logger.info('2/4: %i/%i salt-minions ready (new=%s)' % (len(ready), n, minion_ip))
    logger.info('2/4: Salt minions are ready')
    logger.info('2/4: Accepting salt minions')
    for i, instance in enumerate(instances):
        minion_ip = instance.private_dns_name
        logger.info('2/4: Accepting minion %i(%s)' % (i, minion_ip))
        call = ['sudo', 'salt-key', '-a', minion_ip, '-y']
        logger.info('2/4: CMD: %s' % ' '.join(call))
        p = subprocess.Popen(call, stdout=subprocess.PIPE)
        out, err = p.communicate()
        logger.info('2/4: Minion %i(%s) accepted: OUTPUT[%s] - ERRORS[%s]' % (i + 1, minion_ip, out, err))
    logger.info('2/4: Salt minions connected to master')

    return minion_ips


@app.task
def provision_minions(minion_ips, provision_timeout=900):
    import time
    import salt.client
    client = salt.client.LocalClient()

    logger.info('3/4: Minion ips are:')
    logger.info(minion_ips)

    logger.info('3/4: Provisioning EC2 instances using salt.sls semafor-minion')
    time.sleep(20)
    ret = client.cmd(minion_ips, 'state.sls', ['semafor-minion'], timeout=provision_timeout, expr_form='list')
    ret = client.cmd(minion_ips, 'state.sls', ['semafor-minion'], timeout=provision_timeout, expr_form='list')
    if not ret:
        logger.info('3/4: Salt provisioning timed out, maybe is still running...')
    for i, minion_ip in enumerate(ret):
        minion_states = ret[minion_ip]
        worked = True
        for state in minion_states:
            _worked = minion_states[state]['result']
            if not _worked:
                logger.info('3/4: Salt minion %i(%s) provisioning of [%s] FAILED' % (i + 1, minion_ip, state))
            worked = worked and _worked
        if worked:
            logger.info('3/4: Salt minion %i(%s) provisioning of EVERYTHING went OK' % (i + 1, minion_ip))


@app.task
def semafor_parse(urls, n_instances=None):
    '''
    Parameters
    ----------
    urls: str,
        a list of urls
    n_instances : int, optional(default=None)
        A number of instances to create and provision. If None
        just calls the celery workers and is going to use any
        existent workers
    '''
    # import salt.client
    from semafor.minion.worker.tasks import run_semafor

    if not n_instances:
        # 1. Create instances
        minion_ips = create_instances(n=n_instances)
        provision_minions(minion_ips)

        # 2 Ping minions
        client = salt.client.LocalClient()
        ret = client.cmd(minion_ips, 'test.ping', expr_form='list')
        for i, minion_ip in enumerate(ret):
            logger.info('Ping minion %i[%s]: %s' % (i + 1, minion_ip, ret[minion_ip]))

        # 3 Start celery workers
        cmd = 'sh /home/ubuntu/semafor/app/semafor/minion/start_worker.sh %s' % settings.SALT_MASTER_PUBLIC_ADDRESS
        ret = client.cmd(minion_ips, 'cmd.run', [cmd], expr_form='list', username='ubuntu')
        for i, minion_ip in enumerate(ret):
            logger.info('Celery worker minion %i[%s]: %s' % (i + 1, minion_ip, ret[minion_ip]))

    # Call celery workers
    start = 0
    tasks = []
    docs_per_chunk = len(urls) // n_instances
    for i in range(n_instances):
        ends = start + docs_per_chunk if i < n_instances - 1 else len(urls)

        task = run_semafor.delay(urls[start:ends],
                                 settings.READABILITY_TOKEN,
                                 settings.AWS_ACCESS_ID,
                                 settings.AWS_SECRET_KEY,
                                 settings.S3_PATH,
                                 settings.LUIGI_CENTRAL_SCHEDULER)
        tasks.append(task)
        start = ends

    logger.info('Celery worker minion are working, waiting for them :)')
    print tasks
    #return [task.get() for task in tasks]

