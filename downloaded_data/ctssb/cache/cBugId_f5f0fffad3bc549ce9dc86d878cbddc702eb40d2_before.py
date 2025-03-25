from dxConfig import dxConfig;

def cCdbWrapper_fCdbStdErrThread(oCdbWrapper):
  sLine = "";
  while 1:
    try:
      sChar = oCdbWrapper.oCdbProcess.stderr.read(1);
    except IOError:
      sChar = "";
    if sChar == "\r":
      pass; # ignored.
    elif sChar in ("\n", ""):
      if sChar == "\n" or sLine:
        oCdbWrapper.asStdErrOutput.append(sLine);
        if oCdbWrapper.bGenerateReportHTML:
          sLineHTML = "<span class=\"CDBStdErr\">%s</span><br/>" % oCdbWrapper.fsHTMLEncode(sLine, uTabStop = 8);
          oCdbWrapper.sCdbIOHTML += sLineHTML;
          if oCdbWrapper.rImportantStdErrLines and oCdbWrapper.rImportantStdErrLines.match(sLine):
            oCdbWrapper.sImportantOutputHTML += sLineHTML;
        oCdbWrapper.fStdErrOutputCallback and oCdbWrapper.fStdErrOutputCallback(sLine);
        if dxConfig["bExecuteCommandsEmbeddedInStdErr"]:
          oCdbWrapper.fsQueueCommandsEmbeddedInOutput(oCdbWrapper, sLine);
      if sChar == "":
        break;
      sLine = "";
    else:
      sLine += sChar;
  oCdbWrapper.bCdbRunning = False;

