#!/usr/bin/env python3
"""BuildHelper for CentOS: knows how to build packages for CentOS"""

# Copyright (c) 2014 Timotheus Pokorra

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
from BuildHelper import BuildHelper;
import os
import yaml

class BuildHelperCentos(BuildHelper):
  'build packages for CentOS'

  def __init__(self, container, pathInsideContainer, username, projectname, packagename):
    self.dist='centos'
    BuildHelper.__init__(self, container, pathInsideContainer, username, projectname, packagename)

  def PrepareMachineBeforeStart(self):
    return True

  def PrepareForBuilding(self):
    #self.run("yum clean headers dbcache rpmdb")
    if not self.run("yum -y update"):
      return False
    if not self.run("yum -y install tar createrepo"):
      return False
    # CentOS5: /root/rpmbuild should point to /usr/src/redhat
    if self.dist == "centos" and self.container.release == "5":
      self.run("mkdir -p /usr/src/redhat; ln -s /usr/src/redhat rpmbuild")
      self.run("yum -y install make")
    self.run("mkdir -p rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}")
    return True

  def GetSpecFilename(self):
    pathSrc="/var/lib/lbs/src/"+self.username
    if os.path.isdir(pathSrc + "/lbs-" + self.projectname + "/" + self.packagename):
      for file in os.listdir(pathSrc + "/lbs-" + self.projectname + "/" + self.packagename):
        if file.endswith(".spec") and self.packagename.startswith(file.split('.')[0]):
          return file
    return self.packagename + ".spec"

  def InstallRequiredPackages(self, LBSUrl):
    # first install required repos
    pathSrc="/var/lib/lbs/src/"+self.username
    configfile=pathSrc + "/lbs-" + self.projectname + "/config.yml"
    if os.path.isfile(configfile):
      stream = open(configfile, 'r')
      config = yaml.load(stream)
      if self.dist in config['lbs'] and str(self.container.release) in config['lbs'][self.dist]:
        repos = config['lbs'][self.dist][str(self.container.release)]['repos']
        for repo in repos:
          self.run("cd /etc/yum.repos.d/; curl -L " + repo + " -o `basename " + repo + "`")

    # install own repo as well if it exists
    repofile="/var/www/repos/" + self.username + "/" + self.projectname + "/" + self.dist + "/" + self.container.release + "/lbs-" + self.username + "-" + self.projectname + ".repo"
    if os.path.isfile(repofile):
      self.container.copytree(repofile,"/etc/yum.repos.d/")

    # now install required packages
    specfile=pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename()
    if os.path.isfile(specfile):
      for line in open(specfile):
        if line.lower().startswith("buildrequires: "):
          if line.count(",") > 0:
            packagesWithVersions=line[len("BuildRequires: "):].split(",")
          else:
            packagesWithVersions=line[len("BuildRequires: "):].split()
          packages=[]
          ignoreNext=False
          for word in packagesWithVersions:
            if not ignoreNext:
              # filter >= 3.0, only use package names
              if word[0] == '>' or word[0] == '<' or word[0] == '=':
                ignoreNext=True
              else:
                packages.append(word.strip())
            else:
              ignoreNext=False
          if not self.run("yum -y install rpm-build " + " ".join(packages)):
            return False
    return True

  def BuildPackage(self, LBSUrl):
    pathSrc="/var/lib/lbs/src/"+self.username
    specfile=pathSrc + "/lbs-" + self.projectname + "/" + self.packagename + "/" + self.GetSpecFilename()
    if os.path.isfile(specfile):
      self.run("cp lbs-" + self.projectname + "/" + self.packagename + "/" + self.packagename + ".spec rpmbuild/SPECS")

      # copy patches, and other files (eg. env.sh for mono-opt)
      self.run("cp lbs-" + self.projectname + "/" + self.packagename + "/* rpmbuild/SOURCES")

      # move the sources that have been downloaded according to instructions in config.yml. see BuildHelper::DownloadSources
      self.run("mv sources/* rpmbuild/SOURCES")

      # TODO: build counter for automatically increasing the release number?
      self.run("sed -i -e 's/Release: %{release}/Release: 99/g' rpmbuild/SPECS/" + self.packagename + ".spec")
      if not self.run("rpmbuild -ba rpmbuild/SPECS/" + self.packagename + ".spec"):
        return False

      # add result to repo
      self.run("mkdir -p ~/repo/src")
      self.run("cp ~/rpmbuild/SRPMS/*.src.rpm ~/repo/src")
      self.run("cp -R ~/rpmbuild/RPMS/* ~/repo")
      if not self.run("cd repo && createrepo ."):
        return False
      repoFileContent="[lbs-"+self.username + "-"+self.projectname +"]\n"
      repoFileContent+="name=LBS-"+self.username + "-"+self.projectname +"\n"
      repoFileContent+="baseurl=" + LBSUrl + "/repos/" + self.username + "/" + self.projectname + "/" + self.dist + "/" + self.container.release + "\n"
      repoFileContent+="enabled=1\n"
      repoFileContent+="gpgcheck=0\n"
      repofile="lbs-"+self.username + "-"+self.projectname +".repo"
      with open("/var/www/repos/" + self.username + "/" + self.projectname + "/" + self.dist + "/" + self.container.release + "/" + repofile, 'w') as f:
        f.write(repoFileContent)
    return True

  def GetRepoInstructions(self, LBSUrl, buildtarget):
    buildtarget = buildtarget.split("/")
    result = "cd /etc/yum.repos.d/\n"
    result += "wget " + LBSUrl + "/repos/" + self.username + "/" + self.projectname + "/" + buildtarget[0] + "/" + buildtarget[1] + "/lbs-"+self.username + "-"+self.projectname +".repo\n"
    # packagename: name of spec file, without .spec at the end
    result += "yum install " + self.GetSpecFilename()[:-5]
    return result
