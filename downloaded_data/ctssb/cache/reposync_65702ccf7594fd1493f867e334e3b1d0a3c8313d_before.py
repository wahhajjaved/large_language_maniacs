#!bin/python

import os, subprocess, json, logging, traceback, time, re
from pathlib import Path
from github import Github, GithubException
logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


class Project:
    def __init__(self, projRoot: Path):
        self.config = json.load(open(Path(__file__).parent / "config.json"))
        self.config['SSH_AUTH_SOCK'] = getSshAuthSock()

        self.gh = Github(self.config['githubToken']).get_user()
        self.projRoot = projRoot
        self.name = projRoot.name

    def darcsTime(self):
        j = os.path.join
        darcsPriv = j(self.config['darcsDir'], self.name, '_darcs')
        for n in ['inventory', 'hashed_inventory']:
            if os.path.exists(j(darcsPriv, n)):
                return os.path.getmtime(j(darcsPriv, n))
        raise ValueError("can't find a darcs time")

    def gitDir(self):
        gitDir = os.path.join(self.config['gitSyncDir'], self.name)
        try:
            os.mkdir(gitDir)
        except OSError: pass
        return gitDir

    def syncToLocalGit(self):
        darcsDir = os.path.join(self.config['darcsDir'], self.name)
        try:
            os.rmdir(os.path.join(darcsDir, 'darcs_testing_for_nfs'))
        except OSError: pass
        self.runGitCommand([self.config['darcsToGitCmd'], '--verbose', darcsDir])

    def runGitCommand(self, args, callKw={}):
        try:
            subprocess.check_call(args, cwd=self.gitDir(),
                                  env={'SSH_AUTH_SOCK': self.config['SSH_AUTH_SOCK'],
                                       'HOME': os.environ['HOME'], # darcs-to-git uses this
                                       }, **callKw)
        except:
            log.error("in %s" % self.gitDir())
            raise

    def makeGithubRepo(self):
        try:
            self.gh.create_repo(self.name)
        except GithubException as e:
            assert e.data['errors'][0]['message'].startswith('name already exists'), (e, self.name)
            return
        self.runGitCommand(['git', 'remote', 'add', 'origin',
                            'git@github.com:%s/%s.git' % (self.gh.login,
                                                          self.name)])

    def pushToGithub(self):
        self.runGitCommand(['git', 'push', 'origin', 'master'])

    def hgToGithub(self):
        subprocess.check_call(['hg', 'bookmark', '-r', 'default', 'main'],
                              cwd=self.projRoot)
        push = subprocess.run(['hg', 'push',
                               f'git+ssh://git@github.com/{self.gh.login}/{self.name}'
                               ],
                              check=False,
                              capture_output=True,
                              cwd=self.projRoot,
                              env={'SSH_AUTH_SOCK': self.config['SSH_AUTH_SOCK']})
        if not push.stdout.endswith(b'no changes found\n'):
            raise ValueError(f'hg push failed with {push.stdout!r}')

def getSshAuthSock():
    keychain = subprocess.check_output([
        "keychain", "--noask", "--quiet", "--eval", "id_rsa"]).decode('ascii')
    m = re.search(r'SSH_AUTH_SOCK=([^; \n]+)', keychain)
    if m is None:
        raise ValueError("couldn't find SSH_AUTH_SOCK in output "
                         "from keychain: %r" % keychain)
    return m.group(1)

if __name__ == '__main__':

    # to get this token:
    # curl -u drewp https://api.github.com/authorizations -d '{"scopes":["repo"]}'
    # --new:
    # from https://docs.github.com/en/developers/apps/building-oauth-apps/authorizing-oauth-apps#non-web-application-flow -> https://github.com/settings/tokens to make one

    for proj in os.listdir(config['darcsDir']):
        if not os.path.isdir(os.path.join(config['darcsDir'], proj)):
            continue
        try:
            p = Project(proj)

            if p.darcsTime() < time.time() - 86400*config['tooOldDays']:
                continue

            log.info("syncing %s", proj)
            p.syncToLocalGit()
            p.makeGithubRepo()
            p.pushToGithub()
        except Exception as e:
            traceback.print_exc()
