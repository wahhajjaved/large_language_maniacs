# vim: tabstop=4 shiftwidth=4 softtabstop=4
from fabric.api import *
from fabric.contrib.console import confirm
from time import sleep

def initialize():
    '''Initialize the Pantheon system.'''
    _initialize_support_account()
    _initialize_aptitude()
    _initialize_bcfg2()
    _initialize_drush()
    _initialize_pantheon()
    _initialize_solr()
    _initialize_hudson()
    _initialize_pressflow()

def init():
    '''Alias of "initialize"'''
    initialize()

def _initialize_support_account():
    '''Generate a public/private key pair for root.'''
    local('mkdir -p ~/.ssh')
    with cd('~/.ssh'):
        with settings(warn_only=True):
            local('[ -f id_rsa ] || ssh-keygen -trsa -b1024 -f id_rsa -N ""')

    '''Set up the Pantheon support account with sudo and the proper keys.'''
    sudoers = local('cat /etc/sudoers')
    if '%sudo ALL=(ALL) NOPASSWD: ALL' not in sudoers:
        local('echo "%sudo ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers')
    if 'pantheon' not in local('cat /etc/passwd'):
        local('useradd pantheon --base-dir=/var --comment="Pantheon Support"'
            ' --create-home --groups=www-data,sudo --shell=/bin/bash')
    with cd('~pantheon'):
        local('mkdir -p .ssh')
        local('chmod 700 .ssh')
        local('cp /opt/pantheon/fabric/authorized_keys .ssh/')
        local('cat ~/.ssh/id_rsa.pub > .ssh/authorized_keys')
        local('chmod 600 .ssh/authorized_keys')
        local('chown -R pantheon: .ssh')

def _initialize_aptitude():
    with cd('/opt/pantheon/fabric'):
        sudo('cp pantheon.list /etc/apt/sources.list.d/')
        sudo('cp lucid /etc/apt/preferences.d/')
        sudo('apt-key add gpgkeys.txt')
    sudo('echo \'APT::Install-Recommends "0";\' >>  /etc/apt/apt.conf')
    sudo('apt-get update')
    sudo('apt-get -y dist-upgrade')

def _initialize_bcfg2():
    sudo('apt-get install -y bcfg2-server gamin python-gamin python-genshi')
    with cd('/opt/pantheon/fabric'):
        sudo('cp bcfg2.conf /etc/')
    sudo('rm -f /etc/bcfg2.key bcfg2.crt')
    run('openssl req -batch -x509 -nodes -subj "/C=US/ST=California/L=San Francisco/CN=localhost" -days 1000 -newkey rsa:2048 -keyout /tmp/bcfg2.key -noout')
    sudo('cp /tmp/bcfg2.key /etc/')
    run('openssl req -batch -new  -subj "/C=US/ST=California/L=San Francisco/CN=localhost" -key /etc/bcfg2.key | openssl x509 -req -days 1000 -signkey /tmp/bcfg2.key -out /tmp/bcfg2.crt')
    sudo('cp /tmp/bcfg2.crt /etc/')
    sudo('chmod 0600 /etc/bcfg2.key')
    sudo('[ -h /var/lib/bcfg2 ] || rmdir /var/lib/bcfg2')
    sudo('ln -sf /opt/pantheon/bcfg2 /var/lib/')
    sudo('cp /opt/pantheon/fabric/clients.xml /var/lib/bcfg2/Metadata/')
    sudo('sed -i "s/^plugins = .*$/plugins = Bundler,Cfg,Metadata,Packages,Probes,Rules,TGenshi\\nfilemonitor = gamin/" /etc/bcfg2.conf')
    sudo('/etc/init.d/bcfg2-server restart')
    server_running = False
    warn('Waiting for bcfg2 server to start')
    while not server_running:
        with settings(hide('warnings'), warn_only=True):
            server_running = (sudo('netstat -atn | grep :6789')).rstrip('\n')
        sleep(5)
    sudo('/usr/sbin/bcfg2 -vqed') # @TODO: Add "-p 'pantheon-aws'" for EC2 and "-p 'pantheon-aws-ebs for EBS'"

def _initialize_drush():
    sudo('[ ! -d drush ] || rm -rf drush')
    run('wget http://ftp.drupal.org/files/projects/drush-All-versions-3.0.tar.gz')
    run('tar xvzf drush-All-versions-3.0.tar.gz')
    sudo('chmod 555 drush/drush')
    sudo('chown -R root: drush')
    sudo('rm -rf /opt/drush && mv drush /opt/')
    sudo('ln -sf /opt/drush/drush /usr/local/bin/drush')
    sudo('drush dl drush_make')

def _initialize_pantheon():
    sudo('rm -rf /var/www')
    sudo('drush make --working-copy /etc/pantheon/pantheon.make /var/www/pantheon_dev/')

def _initialize_solr():
    sudo('[ ! -d apache-solr-1.4.1 ] || rm -rf apache-solr-1.4.1')
    run('wget http://apache.osuosl.org/lucene/solr/1.4.1/apache-solr-1.4.1.tgz')
    run('tar xvzf apache-solr-1.4.1.tgz')
    sudo('mkdir -p /var/solr')
    sudo('mv apache-solr-1.4.1/dist/apache-solr-1.4.1.war /var/solr/solr.war')
    sudo('cp -R apache-solr-1.4.1/example/solr /opt/pantheon/fabric/templates/')
    sudo('cp /var/www/pantheon_dev/sites/all/modules/apachesolr/schema.xml /opt/pantheon/fabric/templates/solr/conf/')
    sudo('cp /var/www/pantheon_dev/sites/all/modules/apachesolr/solrconfig.xml /opt/pantheon/fabric/templates/solr/conf/')
    sudo('rm -rf apache-solr-1.4.1')
    sudo('rm apache-solr-1.4.1.tgz')
    sudo('cp -R /opt/pantheon/templates/solr /var/solr/pantheon_dev')
    sudo('cp -a /var/solr/pantheon_dev /var/solr/pantheon_test')
    sudo('cp -a /var/solr/pantheon_dev /var/solr/pantheon_live')
    sudo('chown -R tomcat6:root /var/solr/')

def _initialize_hudson():
    sudoers = local('cat /etc/sudoers')
    hudson_sudoer = ('hudson ALL = NOPASSWD: /usr/local/bin/drush,'
                     ' /etc/pantheon/init.sh, /usr/bin/fab, /usr/sbin/bcfg2')
    if 'hudson ALL = NOPASSWD:' not in sudoers:
        sudo('echo "%s" >> /etc/sudoers' % hudson_sudoer)
    sudo('usermod -a -G shadow hudson')
    sudo('/etc/init.d/hudson restart')

def _initialize_pressflow():
    sudo('mkdir -p /var/www/pantheon_dev/sites/default/files')
    sudo('touch /var/www/pantheon_dev/sites/default/files/gitignore')
    sudo('cp /var/www/pantheon_dev/sites/default/default.settings.php /var/www/pantheon_dev/sites/default/settings.php')
    sudo('cat /opt/pantheon/fabric/templates/newsite.settings.php >> /var/www/pantheon_dev/sites/default/settings.php')
    sudo('mkdir /var/www/pantheon_live')
    with cd('/var/www/pantheon_dev'):
        sudo('git init')
        sudo('git add .')
        sudo('git commit -m "initial branch commit"')
        sudo('git tag v1.0')
    sudo('git clone /var/www/pantheon_dev /var/www/pantheon_test')
    with cd('/var/www/pantheon_test'):
        sudo('git checkout v1.0')
        sudo('git archive master | sudo tar -x -C /var/www/pantheon_live')
    sudo('sed -i "s/pantheon_dev/pantheon_test/g" /var/www/pantheon_test/sites/default/settings.php /var/www/pantheon_test/profiles/pantheon/pantheon.profile')
    sudo('sed -i "s/pantheon_dev/pantheon_live/g" /var/www/pantheon_live/sites/default/settings.php /var/www/pantheon_live/profiles/pantheon/pantheon.profile')
    sudo('chown -R root:www-data /var/www/*')
    sudo('chown www-data:www-data /var/www/*/sites/default/settings.php')
    sudo('chmod 660 /var/www/*/sites/default/settings.php')
    sudo('chmod 775 /var/www/*/sites/default/files')
