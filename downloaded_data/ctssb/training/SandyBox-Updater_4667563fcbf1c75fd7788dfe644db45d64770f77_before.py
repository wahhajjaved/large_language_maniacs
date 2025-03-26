'''
SandyBox updater script
Updates the SandyBox controller from TheCoolTool (thecooltool.com)

Copyright 2014-2017 Alexander Roessler @ TheCoolTool

@package module
'''

import subprocess
import tempfile
import shutil
import urllib.request, urllib.error, urllib.parse
import sys
import os
import json
import http.client
import zipfile
import tarfile
import platform
import time
import threading
import errno
import traceback
import posixpath

# Global variables
tempPath = ''
basePath = '../../'
basePath = os.path.abspath(basePath)
aptOfflinePath = os.path.join(basePath, 'System/update/apt-offline/')
gitHubUser = 'thecooltool'
gitHubRepo = 'SandyBox-Updater'
gitHubBranch = 'v2'
gitHubUrl = 'https://raw.githubusercontent.com/%s/%s/%s/' % (gitHubUser, gitHubRepo, gitHubBranch)
sshExec = ''
scpExec = ''
scpHost = ''
softwareVersion = 1


def init(user='machinekit', password='machinekit', host='192.168.7.2', rsaKey='~/.ssh/sandy-box_rsa'):
    """ Initializes global variables for the specific system """
    global sshExec
    global scpExec
    global scpHost
    system = platform.system()
    rsaKey = os.path.expanduser(rsaKey)
    if system == 'Windows':
        sshExec = os.path.join(basePath, 'Windows\\Utils\\Xming\\plink.exe') + ' -pw %s -ssh -2 -X %s@%s' % (password, user, host)
        scpExec = os.path.join(basePath, 'Windows\\Utils\\Xming\\pscp.exe') + ' -pw %s' % (password)
    else:
        sshExec = 'ssh -i %s -oBatchMode=yes -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null %s@%s' % (rsaKey, user, host)
        scpExec = 'scp -i %s -oBatchMode=yes -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null' % (rsaKey)
    scpHost = '%s@%s' % (user, host)


def info(message):
    """ Displays a info message """
    sys.stdout.write(message)
    sys.stdout.flush()


def createTempPath():
    """ Creates a temporary path """
    global tempPath
    tempPath = tempfile.mkdtemp(prefix='sandy-box-updater')


def clearTempPath():
    """ Removes a temporary path """
    global tempPath

    if tempPath == '':
        return

    shutil.rmtree(tempPath)
    tempPath = ''


def exitScript(message=None):
    if message is not None:
        sys.stderr.write(message)
        sys.stderr.write('\n')

    sys.exit(1)


def countFiles(directory):
    files = []

    if os.path.isdir(directory):
        for path, dirs, filenames in os.walk(directory):
            files.extend(filenames)

    return len(files)


def makedirs(dest):
    if not os.path.exists(dest):
        os.makedirs(dest)


def moveFilesWithProgress(src, dest):
    numFiles = countFiles(src)

    print(("Moving directory {0} ...".format(os.path.basename(dest))))
    if numFiles > 0:
        makedirs(dest)

        numCopied = 0

        for path, dirs, filenames in os.walk(src):
            for directory in dirs:
                destDir = path.replace(src, dest)
                makedirs(os.path.join(destDir, directory))

            for sfile in filenames:
                srcFile = os.path.join(path, sfile)

                destFile = os.path.join(path.replace(src, dest), sfile)

                shutil.move(srcFile, destFile)

                numCopied += 1

                p = float(numCopied) / float(numFiles)
                status = r"{0}/{1}  [{2:.3%}]".format(numCopied, numFiles, p)
                status = status + chr(8) * (len(status) + 1)
                info(status)

        info('\n')


def removeFilesWithProgress(path):
    numFiles = countFiles(path)

    print(("Removing directory {0} ...".format(os.path.basename(path))))
    if numFiles > 0:
        numRemoved = 0

        for spath, dirs, filenames in os.walk(path, topdown=False):

            for sfile in filenames:
                filePath = os.path.join(spath, sfile)
                os.chmod(filePath, 777)  # remove any file flags
                os.remove(filePath)
                numRemoved += 1

                p = float(numRemoved) / float(numFiles)
                status = r"{0}/{1}  [{2:.3%}]".format(numRemoved, numFiles, p)
                status = status + chr(8) * (len(status) + 1)
                info(status)

            for sdir in dirs:
                os.rmdir(os.path.join(spath, sdir))

    info('\n')
    if os.path.exists(path):
        os.rmdir(path)  # remove the main directory


def formatSize(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def resolveHttpRedirect(url, depth=0):
    """ Recursively follow redirects until there isn't a location header """
    if depth > 10:
        raise Exception("Redirected " + depth + " times, giving up.")
    o = urllib.parse.urlparse(url, allow_fragments=True)
    conn = None
    if o.scheme == 'https':
        conn = http.client.HTTPSConnection(o.netloc)
    elif o.scheme == 'http':
        conn = http.client.HTTPConnection(o.netloc)
    else:
        return url
    path = o.path
    if o.query:
        path += '?' + o.query
    conn.request("HEAD", path)
    res = conn.getresponse()
    headers = dict(res.getheaders())
    if 'location' in headers and headers['location'] != url:
        return resolveHttpRedirect(headers['location'], depth + 1)
    else:
        return url


def downloadFile(url, filePath):
    url = resolveHttpRedirect(url)
    while True:
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'Mozilla/5.0')  # Spoof request to prevent caching
        request.add_header('Pragma', 'no-cache')
        u = urllib.request.build_opener().open(request)
        meta = u.info()
        contentLength = meta.get('content-length')
        if contentLength is not None:   # loop until request is valid
            break
    fileSize = int(contentLength)
    fileSizeStr = formatSize(fileSize)
    print(("Downloading {0} ...".format(os.path.basename(filePath))))

    f = open(filePath, 'wb')
    fileSizeDl = 0
    blockSize = 8192
    while True:
        buffer = u.read(blockSize)
        if not buffer:
            break

        fileSizeDl += len(buffer)
        fileSizeDlStr = formatSize(fileSizeDl)
        f.write(buffer)
        p = float(fileSizeDl) / fileSize
        status = r"{0}/{1}  [{2:.3%}]".format(fileSizeDlStr, fileSizeStr, p)
        status = status + chr(8) * (len(status) + 1)
        info(status)

    info('\n')
    f.close()


def updateScript():
    createTempPath()

    localFile = os.path.join(basePath, 'System/update/sha/update.sha')
    scriptPath = os.path.abspath(__file__)
    currentScript = os.path.splitext(scriptPath)[0] + '.py'  # fixes problem on Win64
    scriptName = os.path.basename(currentScript)
    remoteScript = gitHubUrl + scriptName
    localScript = os.path.join(tempPath, scriptName)

    info('Checking if updater is up to date ... \n')
    localSha = None
    remoteSha = getGitRepoSha(gitHubUser, gitHubRepo)

    if os.path.exists(localFile):
        with open(localFile) as f:
            localSha = f.read()
            f.close()

    updated = False
    if remoteSha != localSha:
        info('not\n')
        info('Updating update script ... \n')
        downloadFile(remoteScript, localScript)
        shutil.copyfile(localScript, currentScript)
        with open(localFile, 'w') as f:
            f.write(remoteSha)
            f.close()
        updated = True
        info('done\n')
    else:
        info('yes\n')

    clearTempPath()
    return updated


def processTimeout(p):
    if p.poll() is None:
        try:
            p.kill()
            info('Error: process taking too long to complete -- terminating\n')
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise


def runSshCommand(command, timeout=0.0):
    lines = ''
    retcode = 0
    timer = None
    fullCommand = sshExec.split(' ')
    fullCommand.append(command)

    p = subprocess.Popen(fullCommand,
                         stdout=subprocess.PIPE,
                         stdin=subprocess.PIPE,
                         stderr=subprocess.STDOUT)

    if timeout != 0.0:
        timer = threading.Timer(timeout, processTimeout, [p])
        timer.start()

    while(True):
        retcode = p.poll()  # returns None while subprocess is running

        line = p.stdout.readline().decode('utf-8')
        if 'If you trust this host, enter "y" to add the key to' in line:
            p.stdin.write(b'y\n')    # accept
        if 'The server\'s host key does not match the one PuTTY' in line:
            p.stdin.write(b'y\n')    # accept

        lines += line

        if(retcode is not None):
            break

    if timer is not None:
        timer.cancel()

    return lines, retcode


def testSshConnection():
    info('Testing ssh connection ... ')
    output, retcode = runSshCommand('echo testssh', 10.0)
    if 'testssh' in output:
        info('ok\n')
    else:
        info('failed\n')
        print(output)
        info('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n')
        info('Please check if your SandyBox is connected to the computer.\n')
        info('Make sure all drivers are installed and networking is working correctly.\n')
        exitScript()


def copyToHost(localFile, remoteFile):
    fullCommand = scpExec.split(' ')
    fullCommand.append(localFile)
    fullCommand.append(scpHost + ':' + remoteFile)

    info("Copying " + os.path.basename(localFile) + " to remote host ...")
    p = subprocess.Popen(fullCommand, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
    while(True):
        retcode = p.poll()  # returns None while subprocess is running
        line = p.stdout.readline().decode('utf-8')
        if 'If you trust this host, enter "y" to add the key to' in line:
            p.stdin.write(b'y\n')    # accept
        if 'The server\'s host key does not match the one PuTTY' in line:
            p.stdin.write(b'y\n')    # accept
        if(retcode is not None):
            break

    info(" done\n")
    return retcode


def copyFromHost(remoteFile, localFile):
    fullCommand = scpExec.split(' ')
    fullCommand.append(scpHost + ':' + remoteFile)
    fullCommand.append(localFile)

    info("Copying " + os.path.basename(localFile) + " from remote host ...")
    p = subprocess.Popen(fullCommand, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
    while(True):
        retcode = p.poll()  # returns None while subprocess is running
        line = p.stdout.readline().decode('utf-8')
        if 'If you trust this host, enter "y" to add the key to' in line:
            p.stdin.write(b'y\n')  # accept
        if 'The server\'s host key does not match the one PuTTY' in line:
            p.stdin.write(b'y\n')    # accept
        if(retcode is not None):
            break

    info(" done\n")
    return retcode


def checkHostPath(remotePath):
    output, retcode = runSshCommand('ls ' + remotePath + ' || echo doesnotexist')
    return not ('doesnotexist' in output)


def removeHostPath(remotePath):
    output, retcode = runSshCommand('rm -r -f ' + remotePath + ' || echo removefailed')
    return not ('removefailed' in output)


def moveHostPath(src, dst):
    output, retcode = runSshCommand('mv ' + src + ' ' + dst + ' || echo removefailed')
    return not ('removefailed' in output)


def makeHostPath(remotePath):
    output, retcode = runSshCommand('mkdir -p ' + remotePath + ' || echo mkdirfailed')
    return not ('mkdirfailed' in output)


def unzipOnHost(zipFile, remotePath):
    info('unzipping ' + os.path.basename(remotePath) + ' ... ')
    output, retcode = runSshCommand('unzip ' + zipFile + ' -d ' + remotePath + ' || echo unzipfailed')
    if 'unzipfailed' in output:
        info(' failed\n')
        return False
    else:
        info(' done\n')
        return True


def configureDpkg():
    info('Configuring dpkg ... ')
    output, retcode = runSshCommand('DEBIAN_FRONTEND=noninteractive sudo dpkg --configure -a --force-confold --force-confdef')
    if retcode != 0:
        exitScript(' failed\n')
        return
    else:
        info('done\n')


def checkPackage(name):
    info('Checking for package ' + name + ' ... ')
    output, retcode = runSshCommand('source /etc/profile; dpkg-query -l ' + name + ' || echo not_installed')
    if 'not_installed' in output:
        info('not installed\n')
        return False
    else:
        info('installed\n')
        return True


def installPackage(package, name):
    remotePackage = gitHubUrl + 'packages/' + package
    localPackage = os.path.join(tempPath, package)
    hostPackage = posixpath.join('/tmp', package)

    if not checkPackage(name):
        downloadFile(remotePackage, localPackage)
        copyToHost(localPackage, hostPackage)
        info('Intalling package ' + package + ' ... ')
        output, retcode = runSshCommand('source /etc/profile; sudo dpkg -i ' + hostPackage + ' || echo installerror')
        if 'installerror' in output:
            exitScript('installing package ' + package + ' failed')
        info('done\n')


def aptOfflineBase(command):
    sigName = 'apt-offline.sig'
    localSig = os.path.join(tempPath, sigName)
    hostSig = posixpath.join('/tmp', sigName)
    bundleName = 'bundle.zip'
    localBundle = os.path.join(tempPath, bundleName)
    hostBundle = posixpath.join('/tmp', bundleName)

    info('Updating repositories ...')
    output, retcode = runSshCommand('sudo apt-offline set ' + command + ' ' + hostSig + ' || echo updateerror')
    if 'updateerror' in output:
        exitScript(' failed')
    else:
        info(' done\n')

    if copyFromHost(hostSig, localSig) != 0:
        exitScript('copy failed')

    if os.path.getsize(localSig) == 0:
        info('Packages already up to date\n')
        return False

    if os.path.isfile(localBundle):
        os.remove(localBundle)

    command = sys.executable + ' apt-offline get --threads 2 --bundle ' + localBundle + ' ' + localSig
    command = command.split(' ')
    info('Downloading updates ...')
    p = subprocess.Popen(command, cwd=aptOfflinePath)
    while(True):
        retcode = p.poll()  # returns None while subprocess is running
        if(retcode is not None):
            break

    if retcode != 0:
        exitScript(' failed\n')
    else:
        info(' done\n')

    if copyToHost(localBundle, hostBundle) != 0:
        exitScript('copy failed')

    info('Installing repository update ... ')
    output, retcode = runSshCommand('sudo apt-offline install --skip-changelog --allow-unauthenticated --skip-bug-reports %s || echo installerror' % hostBundle)
    if 'installerror' in output:
        print(output)
        exitScript(' failed')
    else:
        info(' done\n')

    return True


def aptOfflineUpdate():
    aptOfflineBase('--update')


def aptOfflineUpgrade():
    info('Checking if upgrades are available ... ')
    output, _ = runSshCommand('DEBIAN_FRONTEND=noninteractive sudo apt-get upgrade -u -y')
    if '0 upgraded, 0 newly installed, 0 to remove' in output:
        info('no\n')
        return
    else:
        info('yes\n')

    aptOfflineBase('--upgrade')
    info('Upgrading packages ... ')
    output, _ = runSshCommand('DEBIAN_FRONTEND=noninteractive sudo apt-get upgrade -y -q || echo installerror')
    if 'installerror' in output:
        exitScript(' failed\n')
    else:
        info(' done\n')


def aptOfflineInstallPackages(names, force=False):
    namesList = names.split(' ')
    necessary = False
    if force:
        necessary = True
    else:
        for name in namesList:
            if not checkPackage(name):
                necessary = True
                break

    if not necessary:
        return

    if not aptOfflineBase('--install-packages %s --verbose' % names):  # verbose option is needed or it will fail
        return
    info('installing packages ... ')
    output, _ = runSshCommand('DEBIAN_FRONTEND=noninteractive sudo apt-get install -y %s || echo installerror' % names)
    if 'installerror' in output:
        exitScript(' failed\n')
    else:
        info(' done\n')


def aptOfflineRemovePackages(names):
    namesList = names.split(' ')
    necessary = False
    for name in namesList:
        if checkPackage(name):
            necessary = True
            break

    if not necessary:
        return

    info('removing packages ...')
    output, _ = runSshCommand('DEBIAN_FRONTEND=noninteractive sudo apt-get remove -y %s || echo installerror' % names)
    if 'installerror' in output:
        exitScript(' failed\n')
    else:
        info(' done\n')


def getGitRepoSha(user, repo, branch='master'):
    url = 'https://api.github.com/repos/%s/%s/git/refs/heads/%s' % (user, repo, branch)

    request = urllib.request.Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0')  # Spoof request to prevent caching
    request.add_header('Pragma', 'no-cache')
    try:
        u = urllib.request.build_opener().open(request)
    except urllib.error.HTTPError as e:
        info('Requesting Git SHA failed: %s\n' % e)
        info('This could be a result of GitHubs rate limitation.\n')
        exitScript('Please try again later.\n')

    data = b''
    blockSize = 8192
    while True:
        buffer = u.read(blockSize)
        if not buffer:
            break

        data += buffer

    repoObject = json.loads(data.decode('utf-8'))
    return repoObject['object']['sha']


def compareHostGitRepo(user, repo, path, branch='master'):
    remoteSha = getGitRepoSha(user, repo, branch)

    done = True
    output, retcode = runSshCommand('cd ' + path + ';git rev-parse HEAD || echo parseerror')
    if 'parseerror' in output:
        done = False

    if not done:    # remote is not git repo, try to read sha file
        shaFile = path + '/git.sha'  # os path join would fail on Windows
        output, retcode = runSshCommand('cat ' + shaFile + ' || echo parseerror')
        if 'parseerror' in output:
            return False

    outputlines = output.split('\n')
    if len(outputlines) > 1:
        hostSha = outputlines[-2]   # sha is on the semi-last line
    else:
        return False

    return remoteSha == hostSha


def compareLocalGitRepo(user, repo, path, branch='master'):
    remoteSha = getGitRepoSha(user, repo, branch)

    shaFile = os.path.join(path, 'git.sha')
    if os.path.exists(shaFile):
        with open(shaFile) as f:
            localSha = f.read().split('\n')[-1]  # last line in sha file
            f.close()

        return remoteSha == localSha
    else:
        return False


def downloadGitRepo(user, repo, path, branch='master'):
    url = 'https://github.com/%s/%s/zipball/%s' % (user, repo, branch)
    downloadFile(url, path)


def updateHostGitRepo(user, repo, path, commands, branch='master'):
    necessary = False
    fileName = repo + '.zip'
    localFile = os.path.join(tempPath, fileName)
    hostFile = posixpath.join('/tmp', fileName)
    shaFile = posixpath.join(path, 'git.sha')
    tmpPath = path + '-tmp'

    info('Checking if git repo ' + repo + ' is up to date ... ')
    if not checkHostPath(path):
        necessary = True

    if not necessary:
        necessary = not compareHostGitRepo(user, repo, path, branch)

    if necessary:
        info('not\n')

        downloadGitRepo(user, repo, localFile, branch)

        if copyToHost(localFile, hostFile) != 0:
            exitScript('copy failed')

        if not removeHostPath(path):
            exitScript('removing path failed')

        if not removeHostPath(tmpPath):
            exitScript('removing tmp path failed')

        if not unzipOnHost(hostFile, tmpPath):
            exitScript('unzip failed')

        if not moveHostPath(tmpPath + '/' + user + '-' + repo + '-*', path):
            exitScript('move failed')

        if not removeHostPath(tmpPath):
            exitScript('remove failed')

        output, retcode = runSshCommand('unzip -z ' + hostFile + ' >> ' + shaFile + ' || echo commanderror')
        if 'commanderror' in output:
            exitScript('sha dump failed')

        for command in commands:
            if command == '':
                continue
            info('executing ' + command + ' ... ')
            output, retcode = runSshCommand('source /etc/profile; cd ' + path + '; ' + command + ' || echo commanderror')
            if 'commanderror' in output:
                exitScript(' failed')
            else:
                info(' done\n')
    else:
        info('yes\n')


def updateLocalGitRepo(user, repo, path, branch='master'):
    necessary = False
    fileName = repo + '.zip'
    localFile = os.path.join(tempPath, fileName)
    shaFile = os.path.join(path, 'git.sha')
    tmpPath = os.path.join(tempPath, repo)

    info('Checking if git repo ' + repo + ' is up to date ... ')
    if not os.path.exists(path):
        necessary = True

    if not necessary:
        necessary = not compareLocalGitRepo(user, repo, path, branch)

    if necessary:
        info('not\n')

        downloadGitRepo(user, repo, localFile, branch)

        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

        if os.path.exists(tmpPath):
            shutil.rmtree(tmpPath)

        info('Extracting zip file  ... ')
        zipComment = ''
        with zipfile.ZipFile(localFile, 'r') as zip:
            zip.extractall(tmpPath)
            zipComment = zip.comment
            zip.close()
        info('done\n')

        info('Moving files ... ')
        # Remove old dirs and files
        if os.path.exists(path):
            if os.path.isdir(path):
                removeFilesWithProgress(path)
            else:
                os.remove(path)
        os.makedirs(path)

        # get repo dir
        for item in os.listdir(tmpPath):
            repoDir = os.path.join(tmpPath, item)
            if os.path.isdir(repoDir):
                break

        # move files
        for item in os.listdir(repoDir):
            itemPath = os.path.join(repoDir, item)
            targetPath = os.path.join(path, item)

            # Moving with workaround for problem on Windows
            if os.path.isdir(itemPath):
                retries = 0
                while True:
                    try:
                        retries += 1
                        moveFilesWithProgress(itemPath, targetPath)
                        break
                    except OSError as e:
                        if retries < 3:  # Trying 3 times
                            time.sleep(1)
                        else:
                            raise e       # Then raise exception
            else:
                try:
                    shutil.move(itemPath, targetPath)
                except OSError:
                    info('Warning! Cannot move file ' + item + '\n')  # virus scanner?
        shutil.rmtree(tmpPath)  # cleanup temp tree
        info('done\n')

        info('Writing sha file ... ')
        with open(shaFile, 'w') as f:
            f.write(zipComment)
            f.close()
        info('done\n')
    else:
        info('yes\n')


def updateFat(dirName, fileCode, shaCode):
    necessary = False
    localShaFile = os.path.join(tempPath, dirName + '.sha')
    localTarFile = os.path.join(tempPath, dirName + '.tar.bz2')
    tarShaFile = os.path.join(basePath, 'System/update/sha/' + dirName + '.sha')
    remoteTarUrl = 'https://wolke.effet.info/index.php/s/' + fileCode + '/download'
    remoteShaUrl = 'https://wolke.effet.info/index.php/s/' + shaCode + '/download'

    # check local sha
    info('Checking if ' + dirName + ' on FAT partition is up to date ... \n')
    downloadFile(remoteShaUrl, localShaFile)
    with open(localShaFile) as f:
        remoteSha = f.read()
        f.close()

    if os.path.exists(tarShaFile):
        with open(tarShaFile) as f:
            localSha = f.read()
            f.close()

        if localSha != remoteSha:
            necessary = True
    else:
        necessary = True

    if necessary:
        info('not\n')

        downloadFile(remoteTarUrl, localTarFile)

        tarTmpPath = os.path.join(tempPath, 'fat')

        info('Extracting compressed file  ... ')
        if os.path.exists(tarTmpPath):
            shutil.rmtree(tarTmpPath)
        os.makedirs(tarTmpPath)
        with tarfile.open(localTarFile, 'r:bz2') as tar:
            tar.extractall(tarTmpPath)
            tar.close()
        info('done\n')

        info('Moving files ... \n')
        for item in os.listdir(tarTmpPath):
            itemPath = os.path.join(tarTmpPath, item)
            targetPath = os.path.join(basePath, item)

            # Remove old dirs and files
            if os.path.exists(targetPath):
                if os.path.isdir(targetPath):
                    removeFilesWithProgress(targetPath)
                else:
                    os.remove(targetPath)

            # Moving with workaround for problem on Windows
            if os.path.isdir(itemPath):
                retries = 0
                while True:
                    try:
                        retries += 1
                        moveFilesWithProgress(itemPath, targetPath)
                        break
                    except OSError as e:
                        if retries < 3:  # Trying 3 times
                            time.sleep(1)
                        else:
                            raise e       # Then raise exception
            else:
                try:
                    shutil.move(itemPath, targetPath)
                except OSError:
                    info('Warning! Cannot move file ' + item + '\n')  # virus scanner?
        shutil.rmtree(tarTmpPath)
        info('done\n')

        info('Copying sha file ... ')
        shutil.copyfile(localShaFile, tarShaFile)
        info('done\n')
    else:
        info('yes\n')


def installFile(fileName, remotePath, executable=False, sudo=True):
    localPath = os.path.join(tempPath, fileName)
    tmpRemotePath = posixpath.join('/tmp', fileName)
    fileUrl = '%s/files/%s' % (gitHubUrl, fileName)

    info('Installing %s.\n' % fileName)
    downloadFile(fileUrl, localPath)
    copyToHost(localPath, tmpRemotePath)
    cmd = ''
    if executable:
        cmd += 'chmod +x %s; ' % tmpRemotePath
    if sudo:
        cmd += 'sudo '
    cmd += 'mv %s %s' % (tmpRemotePath, remotePath)
    output, retcode = runSshCommand(cmd)
    if retcode != 0:
        exitScript('Command failed: ' + output)


def proceedMessage():
    info('This script will update the SandyBox system.\n')
    info('The update script will download a lot of data.\n')
    while True:
        info('Do you want to proceed? (y/n): ')
        proceed = sys.stdin.readline().strip()
        if proceed == 'n':
            sys.exit(1)
            return
        elif proceed == 'y':
            break
        else:
            info('wrong input, please try again\n')


def readSoftwareVersion():
    info('Reading software version... ')
    version = 0
    output, _ = runSshCommand('cat /etc/software_version || echo doesnotexist')
    if not ('doesnotexist' in output):
        outputlines = output.split('\n')
        if len(outputlines) > 1:
            version = int(outputlines[-2].strip())

    info('%i\n' % version)
    return version


def updateSoftwareVersion(version):
    info('Updating software verison to %i... ' % version)
    output, _ = runSshCommand('sudo su -c "echo %s > /etc/software_version" || echo updatefailed' % str(version))
    if ('updatefailed' in output):
        exitScript('failed')
    else:
        info('done\n')


def readDogtag():
    info('Reading dogtag... ')
    dogtag = 'Unknown'
    output, _ = runSshCommand('cat /etc/dogtag || echo doesnotexist')
    if not ('doesnotexist' in output):
        dogtag = output.split('\n')[-2].strip()

    info('%s\n' % dogtag)
    return dogtag


def checkExperimental():
    indicatorFile = os.path.join(basePath, 'System/update/experimental')
    experimental = os.path.isfile(indicatorFile)
    if experimental:
        info('WARNING: Experimental update sources activated\n')
        info('   Delete %s to activate stable update sources\n' % indicatorFile)
    return experimental


def checkWindowsProcessesBase(execs):
    cmd = 'WMIC PROCESS get Commandline'
    info('Checking running applications...\n')
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    for line in proc.stdout:
        for entry in execs:
            path = entry[1]
            application = entry[0]
            if '\\' in path:
                searchString = os.path.join(basePath, path)
            else:
                searchString = path
            if searchString in line:
                info('Please close ' + application + ' before updating\n')
                return False
    return True


def checkWindowsProcesses():
    execs = [['Notepad++', 'Windows\\Utils\\Notepad++\\notepad++.exe'],
             ['WinSCPPortable', 'Windows\\Utils\\WinSCPPortable\\WinSCPPortable++.exe'],
             ['Putty', 'Windows\\Utils\\Xming\\PAGEANT.EXE'],
             ['Putty', 'Windows\\Utils\\Xming\\plink.exe'],
             ['Putty', 'Windows\\Utils\\Xming\\PSCP.EXE'],
             ['Putty', 'Windows\\Utils\\Xming\\PSFTP.EXE'],
             ['Putty', 'Windows\\Utils\\Xming\\putty.exe'],
             ['Putty', 'Windows\\Utils\\Xming\\PUTTYGEN.EXE'],
             ['Xming', 'xkbcomp.exe'],
             ['Xming', 'Xming.exe']]

    while checkWindowsProcessesBase(execs) is False:
        while True:
            info('Check again? (y/n): ')
            proceed = sys.stdin.readline().strip()
            if proceed == 'n':
                sys.exit(1)
                return
            elif proceed == 'y':
                break
            else:
                info('wrong input, please try again\n')


def installMklauncher():
    fileName = 'mklauncher.service'
    servicePath = '/etc/systemd/system/%s' % fileName
    info('Checking if mklauncher service is installed...')
    _, retcode = runSshCommand('test -f %s' % servicePath)

    if retcode == 1:
        info('not\n')
        localPath = os.path.join(tempPath, fileName)
        remotePath = posixpath.join('/tmp', fileName)
        fileUrl = '%s/files/%s' % (gitHubUrl, fileName)
        info('Installing mklauncher service.\n')
        downloadFile(fileUrl, localPath)
        copyToHost(localPath, remotePath)
        command = 'sudo mv %s %s; ' % (remotePath, servicePath)
        command += 'sudo systemctl daemon-reload; '
        command += 'sudo systemctl enable mklauncher.service'
        output, retcode = runSshCommand(command)
        if retcode != 0:
            exitScript('Command failed: ' + output)
    else:
        info('yes\n')


def installRepositorySignature():
    info('Installing Machinekit repository signature...')
    installFile('trusted-keys', '/tmp/keys')
    _, retcode = runSshCommand('sudo apt-key add /tmp/keys && rm /tmp/keys')
    if retcode == 0:
        info('done\n')
    else:
        exitScript('failed')


def updateGroups():
    groups = ['netdev']
    for group in groups:
        info('Adding user to %s group... ' % group)
        _, retcode = runSshCommand('sudo usermod -a -G %s machinekit' % group)
        if retcode == 0:
            info('done\n')
        else:
            exitScript('failed')


def updateUuid():
    info('Updating SandyBox UUID... ')
    _, retcode = runSshCommand('UUID=`cat /proc/sys/kernel/random/uuid`; sudo sed -i \'s/^MKUUID=.*/MKUUID=\'"$UUID"\'/\' /etc/linuxcnc/machinekit.ini')
    if retcode == 0:
        info('done\n')
    else:
        exitScript('failed')


def updateDateTime():
    info('Updating datetime from host... ')
    timestamp = int(time.time())
    _, retcode = runSshCommand('sudo date -s @%i' % timestamp)
    if retcode == 0:
        info('done\n')
    else:
        exitScript('failed')


def main():
    init()

    if platform.system() == 'Windows':  # check open applications
        checkWindowsProcesses()

    createTempPath()

    try:
        # check if this update should use experimental sources
        experimental = checkExperimental()

        updateFat('Other', '78b5b1487275bf3370dd6b21f92ce6a1', '0f44627c04c56a7e55e590268a21329b')
        updateLocalGitRepo('thecooltool', 'SandyBox-Windows', os.path.join(basePath, 'Windows'), branch='v2')
        updateLocalGitRepo('thecooltool', 'SandyBox-Linux', os.path.join(basePath, 'Linux'), branch='v2')
        updateLocalGitRepo('thecooltool', 'SandyBox-Mac', os.path.join(basePath, 'Mac'), branch='v2')
        updateLocalGitRepo('thecooltool', 'SandyBox-Doc', os.path.join(basePath, 'Doc'), branch='v2')

        testSshConnection()

        updateDateTime()  # make sure the system time is correct
        version = readSoftwareVersion()

        configureDpkg()  # make sure dpkg status is sane

        if version < 1:
            if not makeHostPath('~/nc_files/share'):
                exitScript('failed to create nc_files/share directory')
            if not makeHostPath('~/bin'):
                exitScript('failed to create bin directory')
            installFile('powerbtn-acpi-support.sh', '/etc/acpi/powerbtn-acpi-support.sh', executable=True)
            installFile('machinekit.ini', '/etc/linuxcnc/machinekit.ini')
            installMklauncher()
            installFile('sshd_config', '/etc/ssh/sshd_config')
            installFile('70-persistent-net.rules', '/etc/udev/rules.d/70-persistent-net.rules')
            updateUuid()

        if not experimental:
            updateHostGitRepo('thecooltool', 'AP-Hotspot', '~/bin/AP-Hotspot', ['sudo make install'])
            updateHostGitRepo('thecooltool', 'querierd', '~/bin/querierd', ['sudo make install'])

            updateHostGitRepo('thecooltool', 'Cetus', '~/Cetus', [], branch='v2')
            updateHostGitRepo('thecooltool', 'Machineface', '~/Machineface', [], branch='v2')
            updateHostGitRepo('thecooltool', 'mjpeg-streamer', '~/bin/mjpeg-streamer',
                              ['make -C mjpg-streamer-experimental', 'sudo make -C mjpg-streamer-experimental install'])
            updateHostGitRepo('thecooltool', 'machinekit-configs', '~/machinekit-configs', [], branch='v2')
            updateHostGitRepo('thecooltool', 'example-gcode', '~/nc_files/examples', [])
        else:
            aptOfflineUpdate()
            aptOfflineInstallPackages('machinekit machinekit-rt-preempt', force=True)  # force update of Machinekit
            updateHostGitRepo('thecooltool', 'AP-Hotspot', '~/bin/AP-Hotspot', ['sudo make install'])
            updateHostGitRepo('thecooltool', 'querierd', '~/bin/querierd', ['sudo make install'])

            updateHostGitRepo('qtquickvcp', 'Cetus', '~/Cetus', [''])
            updateHostGitRepo('qtquickvcp', 'Machineface', '~/Machineface', [''])
            updateHostGitRepo('thecooltool', 'mjpeg-streamer', '~/bin/mjpeg-streamer',
                              ['make -C mjpg-streamer-experimental', 'sudo make -C mjpg-streamer-experimental install'])
            updateHostGitRepo('thecooltool', 'machinekit-configs', '~/repos/machinekit-configs', [], branch='develop')
            updateHostGitRepo('thecooltool', 'example-gcode', '~/nc_files/examples', [])

        if version != softwareVersion:
            updateSoftwareVersion(softwareVersion)
    except:
        print((traceback.format_exc()))
        info("Error during execution of update script.")
        sys.exit(1)
    else:
        info('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n')
        info('Update successfully finished!\n')
        info('You can now close the terminal window\n')
    finally:
        clearTempPath()
