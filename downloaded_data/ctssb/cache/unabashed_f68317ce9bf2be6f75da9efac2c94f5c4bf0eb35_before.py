#!/usr/bin/python
import cgi
import cgitb; cgitb.enable()  # for troubleshooting
from commands import getoutput
from ansi2html import ansi2html
from logHtml import *

# John Hakala, 2/25/17

def getLastLogMessages(lines, filter):
  logCopyName = "~johakala/logCopyer/log_copy.xml"
  incantation = "tail -%i %s | ~hcalpro/scripts/Handsaw.pl" % (lines, logCopyName)
  if filter is not None and filter in ["INFO", "WARN", "ERROR"]:
    incantation += " --FILTER=%s" % filter
  #incantation = "tail -%i /nfshome0/elaird/errors.txt" % lines
  return getoutput(incantation)
  
def formatMessages(messages):
  formattedMessages = "    <br><tt>\n    <br>"
  for line in messages.splitlines():
    formattedMessages += ansi2html(line, "xterm")
    formattedMessages+="\n    <br>"
  formattedMessages += "    </tt>"
  return formattedMessages

def getBody(numLines, filtLev):
  body =  "    <!-- begin body -->\n"
  if numLines is not None and (isinstance(numLines, int) or isinstance(numLines, str)):
    try: 
      nLines = int(numLines)
      if nLines > 0:
        body += "    Showing last %i lines of logcollector logs" % nLines
        body += formatMessages(getLastLogMessages(nLines, filtLev))
      else:
        body += "    the numberOfLines submitted seems to be a weird number: <tt> %s </tt>" % str(numLines)
    except ValueError:
        body += "    the numberOfLines submitted does not seem to be a number <tt> %s </tt>" % str(numLines)
  else:
    if numLines is None:
      body += "\n    <strong> you must select a number of lines to display.</strong>"
    else:
      body += "\n    <strong> something looks fishy about the number of lines requested: %r" % numLines
  body += "\n    <!-- body end -->"
  return body

form = cgi.FieldStorage()
numberOfLines =  form.getvalue('numberOfLines')
filterLevel =  form.getvalue('filter')

html =  getHeader()
html += getBody(numberOfLines, filterLevel)
html += getFooter()

print "Content-type: text/html"
print
print html
