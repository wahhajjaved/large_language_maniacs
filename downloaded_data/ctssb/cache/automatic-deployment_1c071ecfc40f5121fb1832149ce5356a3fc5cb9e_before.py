import json
from copy import deepcopy

from fabric.api import lcd, local, env, execute
from os import path
import sys


class Repository:
  def __init__(self, id, repository, commit, cloneFolder, dependencies):
    self.id = id
    self.repository = repository
    self.commit = commit
    self.cloneFolder = cloneFolder
    self.dependencies = dependencies

  def __str__(self):
    return "({}, {}, {}, {})".format(self.id, self.repository, self.commit, self.cloneFolder)


clonedRepositories = {}

cloneIndex = 1


def recursiveClone(repository, commit, inKeys=None):
  if inKeys is None:
    inKeys = {}
  clonedFolderName = clone(repository, commit, inKeys)

  with lcd(clonedFolderName):
    dependencies = getDependencies()

  for dependency in dependencies:
    outDependencies = dict(inKeys, **dependency)
    recursiveClone(dependency['repository'], dependency['commit'], outDependencies)


def clone(repository, commit, dependencies):
  global cloneIndex

  print("Getting repo {} to process...".format(repository))
  if repository in clonedRepositories:
    if not commit == clonedRepositories[repository].commit:
      raise Exception(
        'Commits not equal for same dependency! {}/{} =/= {}/{}'.format(repository, commit, repository,
                                                                        clonedRepositories[
                                                                          repository].commit))
    print("Dependency already exist, adjusting the id...")
    clonedRepositories[repository].id = cloneIndex
    cloneFolder = clonedRepositories[repository].cloneFolder

  else:
    cloneFolder = 'repo' + str(cloneIndex)

    local('git clone ' + repository + ' -b ' + commit + ' ' + cloneFolder)
    clonedRepositories[repository] = Repository(cloneIndex, repository, commit, cloneFolder, dependencies)

  cloneIndex += 1

  return cloneFolder


def getDependencies():
  with lcd('deploy'):
    currentPwd = local('pwd', capture=True)
    with open(path.join(currentPwd, 'deploy.json')) as deployConfFile:
      deployConf = json.load(deployConfFile)

  return deployConf['dependencies']


def main(configPath):
  errors = {}
  with open(configPath) as envFile:
    envData = json.load(envFile)
    for key, val in envData.items():
      env[key] = val

  local('mkdir -p ' + env.tmpFolder)
  with lcd(env.tmpFolder):
    recursiveClone(env["source-repository"], env["source-commit"])
    print("Checking canRun functions...")
    for repoTuple in sorted(clonedRepositories.items(), key=lambda x: x[1].id, reverse=True):
      oldEnv = deepcopy(env)
      repo = repoTuple[1]
      for key, value in repo.dependencies.items():
        env[key] = value
      env['source-repository'] = repo.repository
      env['source-commit'] = repo.commit
      try:
        with lcd(path.join(repo.cloneFolder, 'deploy')):
          sys.path.append(local('pwd', capture=True))
          import deploy
          if 'canRun' not in dir(deploy):
            print("No function canRun for deploy script in {}!".format(repo.repository))
          else:
            print("Function canRun exist for deploy script in {}!".format(repo.repository))
            from deploy import canRun
            try:
              ret_value = execute(canRun)
            except Exception as e:
              print(e)
              ret_value = {'all': False}

            for host, value in ret_value.items():
              if value:
                print("Deploy can run!")
              else:
                raise EnvironmentError(
                  "Can not continue, missing requirements for deploy script in {}! Aborting...".format(
                    repo.repository))
          sys.path.remove(local('pwd', capture=True))
      except ImportError:
        print("No module deploy for {}!".format(repo.repository))
        pass
      except EnvironmentError:
        local('rm -rf ../{}'.format(env.tmpFolder))
        raise
      finally:
        del sys.modules['deploy']
        env.clear()
        for key, value in oldEnv.items():
          env[key] = value
    print("Check done!")
    print("Running deploy functions...")
    for repoTuple in sorted(clonedRepositories.items(), key=lambda x: x[1].id, reverse=True):
      oldEnv = deepcopy(env)
      repo = repoTuple[1]
      for key, value in repo.dependencies.items():
        env[key] = value
      env['source-repository'] = repo.repository
      env['source-commit'] = repo.commit
      try:
        with lcd(repo.cloneFolder):
          with lcd('deploy'):
            sys.path.append(local('pwd', capture=True))
            from deploy import runDeploy
            sys.path.remove(local('pwd', capture=True))
            print("Running Deploy for {}".format(repo.repository))
            error = execute(runDeploy)
            for host, returnValue in error.items():
              if returnValue is None:
                continue
              if host not in errors:
                errors[host] = {}
              errors[host][repo.repository] = returnValue
              
        del sys.modules['deploy']
        env.clear()
        for key, value in oldEnv.items():
          env[key] = value
      except Exception:
        raise
      finally:
        local('rm -rf ' + repo.cloneFolder)
    print("Run done!")
    if len(errors) is not 0:
      print("Got following errors:")
      for host, errorItem in errors.items():
        print(host)
        for repo, errorArray in errorItem.items():
          print(f"\t{repo}")
          for error in errorArray:
            print(f"\t\t- {error}")
