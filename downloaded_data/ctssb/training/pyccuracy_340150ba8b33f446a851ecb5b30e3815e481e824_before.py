#!/usr/bin/env python
# -*- coding: utf-8 -*
 
u"""Pyccuracy - BDD Acceptance testing

Example usage
=============
 
    python pyccuracy.py
 
:author: `Bernardo Heynemann <mailto:heynemann@gmail.com>`__
"""
 
# Pylint checks
# "line to long" pylint: disable-msg=C0301
# "Used * or ** magic" pylint: disable-msg=W0142
 
__revision__ = "$Id$"
__docformat__ = 'restructuredtext en'
 
import os, sys, optparse 
from pyccuracy.pyccuracy_core import PyccuracyCore
 
def main():
    """ Main function - parses args and runs action """
    parser = optparse.OptionParser(usage="%prog or type %prog -h (--help) for help", description=__doc__, version="%prog" + __revision__)
    parser.add_option("-p", "--pattern", dest="pattern", default="*.acc", help="File pattern. Defines which files will get executed [default: %%default].")
    parser.add_option("-l", "--language", dest="language", default="en-us", help="Language. Defines which language the dictionary will be loaded with  [default: %%default].")
    parser.add_option("-d", "--dir", dest="dir", default=os.curdir, help="Tests directory. Defines where the tests to be executed are [default: %%default]. Note: this is recursive, so all the tests under the current directory get executed.")
    parser.add_option("-u", "--url", dest="url", default=None, help="Base URL. Defines a base url against which the tests will get executed. For more details check the documentation [default: %%default].")
    
    #reporter
    parser.add_option("-R", "--report", dest="write_report", default="true", help="Should write report. Defines if Pyccuracy should write an html report after each run [default: %%default].")
    parser.add_option("-D", "--reportdir", dest="report_dir", default=os.curdir, help="Report directory. Defines the directory to write the report in [default: %%default].")
    parser.add_option("-F", "--reportfile", dest="report_file_name", default="report.html", help="Report file. Defines the file name to write the report with [default: %%default].")
     
    (options, args) = parser.parse_args()

    pyc = PyccuracyCore()
    pyc.run_tests(file_pattern=options.pattern, 
                  tests_dir=options.dir, 
                  base_url=options.url, 
                  default_culture=options.language,
                  write_report = options.write_report.lower() == "true",
                  report_file_dir = options.report_file_dir,
                  report_file_name = options.report_file_name)
 
if __name__ == "__main__":
    main()
