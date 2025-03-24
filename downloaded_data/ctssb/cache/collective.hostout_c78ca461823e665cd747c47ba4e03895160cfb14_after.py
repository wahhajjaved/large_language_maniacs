import os

def createuser(buildout_user='buildout'):
    "Creates a user account to run the buildout in"
    #keyname="buildout_dsa.%s"%(buildout_host)
    #if not os.path.exists(keyname):
    if True:
        sudo('test -d ~$(buildout_user) || adduser $(buildout_user)')
        sudo('test -d ~$(buildout_user)/.ssh || mkdir ~$(buildout_user)/.ssh;')
        sudo('(chmod 700 ~$(buildout_user)/.ssh; touch ~$(buildout_user)/.ssh/authorized_keys)')
        sudo('chmod 600 ~$(buildout_user)/.ssh/authorized_keys')
        #run("rm -f /tmp/buildout_dsa")
        #run("ssh-keygen -t dsa -N '' -f /tmp/buildout_dsa")
        #run('rm ~$(buildout_user)/.ssh/buildout_dsa.pub')
        #try:
        #    download('/tmp/buildout_dsa','buildout_dsa')
        #    download('/tmp/buildout_dsa.pub','buildout_dsa.pub')
        #except:
        #    pass
        sudo('cp ~$(buildout_user)/.ssh/authorized_keys ~$(buildout_user)/.ssh/authorized_keys.bak')
        sudo('cat /tmp/buildout_dsa.pub >> ~$(buildout_user)/.ssh/authorized_keys')
    set(fab_key_filename=keyname)



def preparebuildout():
    "install buildout and its dependencies"
    #first need to ensure gcc installed
    #on suse sudo('/sbin/yast2 --install gcc')
    #eventually we want a more selfcontained solution. but for now this should work
    #run('export http_proxy=localhost:8123') # TODO get this from setting
    run('cd /tmp && test -f $(unified).tgz || wget $(unified_url)')
    run('test -d /tmp/$(unified) || (cd /tmp && tar -xvf /tmp/$(unified).tgz)')
    sudo('test -d $(buildout_dir) || (test -d /tmp/$(unified) && cd /tmp/$(unified) && sudo ./install.sh --target=$(install_dir) --instance=$(instance) --user=$(effectiveuser) --nobuildout standalone)')

#    try:
#        run('ls $(buildout_dir)/bootstrap.py')
#    except:
#        put('bootstrap.py','$(buildout_dir)')
#    try:
#        run('ls $(buildout_dir)/bin')
#    except:
#        run('cd $(buildout_dir); python bootstrap.py')

def installhostout():
    "deploy the package of changed cfg files"
    #need to send package. cycledown servers, install it, run buildout, cycle up servers
    
    local('test -f $(package_path)')
    #import pdb; pdb.set_trace()
    put('$(package_path)', '/tmp/$(hostout_package)')
    run('cd $(install_dir) && $(stop_cmd) || echo unable to stop application')
    #need a way to make sure ownership of files is ok
    sudo('tar --no-same-permissions --no-same-owner --overwrite --owner $(effectiveuser) -xvf /tmp/$(hostout_package) --directory=$(install_dir)')
    sudo('sh -c "cd $(install_dir) && bin/buildout -c hostout.cfg"')
#    run('cd $(install_dir) && $(reload_cmd)')
    run('cd $(install_dir) && $(start_cmd)')


def deploy(host,user='plone', password=None, identityfile=None, buildout_user='plone', remote_dir='buildout', dist_dir='dist', package='deploy_1'):
    "Prints hello."
    if password:
        set(fab_password=password)
    if identityfile:
        set(fab_key_filename=identityfile)
    set(
        fab_user=user,
        fab_hosts=[host],
        effectiveuser=buildout_user,
        buildout_dir=remote_dir,
        unified='Plone-3.2.1r3-UnifiedInstaller',
        unified_url='http://launchpad.net/plone/3.2/3.2.1/+download/Plone-3.2.1r3-UnifiedInstaller.tgz',
        install_dir=os.path.split(remote_dir)[0],
        instance=os.path.split(remote_dir)[1],
    )
    preparebuildout()
    set(
        buildout_user=user,
        buildout_dir=remote_dir,
        #fab_user='$(buildout_user)',
        fab_user=user,
        #fab_key_filename="buildout_dsa",
        dist_dir='dist',
        install_dir=remote_dir,
        hostout_package=package,
        package_path=os.path.abspath(os.path.join(dist_dir,package)),
        stop_cmd='bin/supervisorctl stop all',
        start_cmd='bin/supervisorctl start all',
        reload_cmd='bin/supervisorctl reload',
    )
    installhostout()
    
    
    