#!/usr/bin/env python3
"""BuildHelper: abstract base class for various builders"""

# Copyright (c) 2014-2016 Timotheus Pokorra

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
# USA
#
import yaml
import os.path
from collections import deque
import Config

class BuildHelper:
  'abstract base class for BuildHelper implementations for the various Linux Distributions'

  def __init__(self, container, username, projectname, packagename):
    self.container = container
    self.fedora = 0
    self.suse_version = 0
    self.rhel = 0
    self.release = 0
    if container is not None:
      self.arch = container.arch
      self.release = container.release
      self.rhel = self.release
    self.username = username
    self.projectname = projectname
    self.packagename = packagename
    self.config = Config.LoadConfig()
    self.pathSrc=self.config['lbs']['GitSrcPath']+"/"+self.username

  def log(self, message):
    if self.container is not None:
      self.container.logger.print(message);

  def run(self, command):
    return self.container.executeInContainer(command)

  def PrepareMachineBeforeStart(self):
    print("not implemented")
    return True

  def PrepareMachineAfterStart(self):
    print("not implemented")
    return True

  def PrepareForBuilding(self):
    print("not implemented")
    return True

  def DownloadSources(self):
    # parse config.yml file and download the sources
    # unpacking and moving to the right place depends on the distro
    file = self.pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/config.yml"
    if os.path.isfile(file):
      stream = open(file, 'r')
      config = yaml.load(stream)
      for url in config['lbs']['source']['download']:
        filename="`basename " + url + "`"
        if isinstance(config['lbs']['source']['download'], dict):
          filename=url
          url=config['lbs']['source']['download'][url]
        self.run("mkdir -p /root/sources")
        if not self.run("curl -L " + url + " -o /root/sources/" + filename):
          return False
    return True

  def InstallRepositories(self, DownloadUrl):
    print("not implemented")
    return True

  def InstallRequiredPackages(self):
    print("not implemented")
    return True

  def BuildPackage(self, config):
    print("not implemented")
    return True

  def SetupEnvironment(self, branchname):
    path="lbs-" + self.projectname + "/" + self.packagename
    if not os.path.isdir(self.pathSrc + "/" + path):
      self.log("cannot find path " + path)
      return False
    setupfile=path + "/setup.sh"
    if os.path.isfile(self.pathSrc + "/" + setupfile):
      if not self.run("cd " + path + "; ./setup.sh " + branchname):
        return False
    return True

  def DisableOutgoingNetwork(self):
    if not self.run("iptables -P OUTPUT DROP && iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT && iptables -A OUTPUT -j DROP"):
      return False
    return True

  def GetWinInstructions(self, config, DownloadUrl, buildtarget, branchname):
    return None

  def GetSrcInstructions(self, config, DownloadUrl, buildtarget):
    return "not implemented"

  def GetRepoInstructions(self, config, DownloadUrl, buildtarget):
    return "not implemented"

  def CreateRepoFile(self, config):
    return "not implemented"
 
  def GetDependanciesAndProvides(self, config, lxcdistro, lxcrelease, lxcarch):
    print("not implemented")
    return False

  def CalculatePackageOrder(self, config, lxcdistro, lxcrelease, lxcarch):
    result = deque()
    self.release = lxcrelease
    self.arch = lxcarch
    userconfig=config['lbs']['Users'][self.username]
    projectconfig=userconfig['Projects'][self.projectname]
    if 'Packages' in projectconfig:
      packages = userconfig['Projects'][self.projectname]['Packages']
    else:
      packages = userconfig['Projects'][self.projectname]
    unsorted={}
    builddepends={}
    depends={}
    deliverables={}
    for package in packages:
      excludeDistro=False
      if packages[package] is not None and "ExcludeDistros" in packages[package]:
        for exclude in packages[package]['ExcludeDistros']:
          if (lxcdistro + "/" + lxcrelease + "/" + lxcarch).startswith(exclude):
            excludeDistro = True
      includeDistro=True
      if packages[package] is not None and "Distros" in packages[package]:
        includeDistro=False
        for incl in packages[package]['Distros']:
          if (lxcdistro + "/" + lxcrelease + "/" + lxcarch) == incl:
            includeDistro=True
      if includeDistro and not excludeDistro:
        self.packagename=package
        (builddepends[package],deliverables[package]) = self.GetDependanciesAndProvides()
        for p in deliverables[package]:
          unsorted[p] = 1
          depends[p] = deliverables[package][p]['requires']
        if not package in unsorted:
          unsorted[package] = 1
        # useful for debugging:
        if False:
          print( package + " builddepends on: ")
          for p in builddepends[package]:
            print("   " + p)
          print( package + " produces these packages: ")
          for p1 in deliverables[package]:
            for p in deliverables[package][p1]['provides']:
              print("   " + p + " which requires during installation:")
              for d in depends[p1]:
                print("      " + d)

    while len(unsorted) > 0:
      nextPackage = None
      for package in unsorted:
        if package in packages and nextPackage is None:
          missingRequirement=False
          # check that this package does not require a package that is in unsorted
          for dep in builddepends[package]:
            if dep in unsorted:
              missingRequirement=True
            if dep in depends:
              for dep2 in depends[dep]:
                if dep2 in unsorted:
                  missingRequirement=True
          if not missingRequirement:
            nextPackage=package
      if nextPackage == None:
        # problem: circular dependancy
        print ("circular dependancy, remaining packages: ")
        for p in unsorted:
          print(p)
        return None
      result.append(nextPackage)
      for p in deliverables[nextPackage]:
        if p in unsorted:
          del unsorted[p]
      if nextPackage in unsorted:
        del unsorted[nextPackage]

    return result
