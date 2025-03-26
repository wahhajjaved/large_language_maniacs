# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'jmdelarosa@cnb.csic.es'
# *
# **************************************************************************
"""
This modules handles the System management
"""

import os

import pyworkflow as pw
import pyworkflow.utils as pwutils
from project import Project



class ProjectInfo(object):
    """Class to store some information about the project"""
    def __init__(self, projName, mTime):
        """At least it receives the Project Name and its modification time"""
        self.projName = projName
        self.mTime = mTime
        
    def getName(self):
        return self.projName
    
    def getModificationTime(self):
        return self.mTime
        
        
class Manager(object):
    """This class will handle the creation, modification
    and listing of projects."""
    def __init__(self):
        """For create a Project, the path is required"""
        pass
        
    def getProjectPath(self, projectName):
        """Return the project path given the name"""
        return os.path.join(pw.PROJECTS, projectName)
        
    def listProjects(self, sortByDate=True):
        """Return a list with all existing projects
        And some other project info
        If sortByData is True, recently modified projects will be first"""
        projList = []
        pwutils.path.makePath(pw.PROJECTS)
        for f in os.listdir(pw.PROJECTS):
            p = self.getProjectPath(f)
            if os.path.isdir(p):
                stat = os.stat(p)
                projList.append(ProjectInfo(f, stat.st_mtime))
                
        if sortByDate:
            projList.sort(key=lambda k: k.mTime, reverse=True)
        return projList
    
    def createProject(self, projectName, runsView=1, hostsConf=None, protocolsConf=None):
        """Create a new project.
        confs dict can contains customs .conf files 
        for: menus, protocols, or hosts
        """
        project = Project(self.getProjectPath(projectName))
        project.create(runsView=runsView, 
                       hostsConf=hostsConf, 
                       protocolsConf=protocolsConf)
        return project
    
    def loadProject(self, projId):
        """ Retrieve a project object, given its id. """
        project = Project(self.getProjectPath(projId))
        project.load()
        return project

    def deleteProject(self, projectName):
        pwutils.path.cleanPath(self.getProjectPath(projectName))

    def renameProject(self, oldName, newName):
        os.rename(self.getProjectPath(oldName), self.getProjectPath(newName))

    def hasProject(self, projectName):
        """Return True if exists a project with projectName"""
        for projInfo in self.listProjects():
            if projectName == projInfo.projName:
                return True
        return False
