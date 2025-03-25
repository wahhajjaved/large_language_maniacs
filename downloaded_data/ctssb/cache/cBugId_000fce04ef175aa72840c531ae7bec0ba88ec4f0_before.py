from dxBugIdConfig import dxBugIdConfig;
# Hide some functions at the top of the stack that are merely helper functions and not relevant to the bug:
# Some of these exceptions get thrown during heap allocations/frees, thus there are a number of related functions
# in this list, as the problem is not caused by them (but probably also not by their caller, but the caller may give
# a reasonably good indication what the application was doing on the heap that caused the exception).
asHiddenTopFrames = [
  "msvcrt.dll!malloc",
  "ntdll.dll!KiUserExceptionDispatcher",
  "ntdll.dll!LdrpValidateUserCallTarget",
  "ntdll.dll!LdrpValidateUserCallTargetBitMapCheck",
  "ntdll.dll!LdrpValidateUserCallTargetBitMapRet",
  "ntdll.dll!LdrpValidateUserCallTargetEH",
  "ntdll.dll!RtlAllocateHeap",
  "ntdll.dll!RtlDebugAllocateHeap",
  "ntdll.dll!RtlDeleteCriticalSection", # can throw CorruptList
  "ntdll.dll!RtlFailFast2",
  "ntdll.dll!RtlpAllocateHeap",
  "ntdll.dll!RtlpAllocateHeapInternal",
  "ntdll.dll!RtlpHandleInvalidUserCallTarget",
  "verifier.dll!AVrfDebugPageHeapAllocate",
  "verifier.dll!AVrfpDphFindAvailableMemory",
  "verifier.dll!AVrfpDphRemoveFromFreeList",
  "verifier.dll!FatalListEntryError",
  "verifier.dll!RemoveEntryList",
  "verifier.dll!RtlFailFast", # can throw CorruptList
  # Edge
  "EMODEL.dll!wil::details::ReportFailure",
  "EMODEL.dll!wil::details::ReportFailure_Hr",
  "EMODEL.dll!wil::details::in1diag3::FailFast_Hr",
];
# Source: winnt.h (codemachine.com/downloads/win81/winnt.h)
# I couldn't find much information on most of these exceptions, so this may be incorrect or at least incomplete.
dtsFastFailErrorInformation_by_uCode = {
  0:  ("LegacyGS",      "/GS detected that a stack cookie was modified",              "Potentially exploitable security issue"),
  1:  ("VTGuard",       "VTGuard detected an invalid virtual function table cookie",  "Potentially exploitable security issue"),
  2:  ("StackCookie",   "/GS detected that a stack cookie was modified",              "Potentially exploitable security issue"),
  3:  ("CorruptList",   "Safe unlinking detected a corrupted LIST_ENTRY",             "Potentially exploitable security issue"),
  4:  ("BadStack",      "FAST_FAIL_INCORRECT_STACK",                                  "Potentially exploitable security issue"),
  5:  ("InvalidArg",    "FAST_FAIL_INVALID_ARG",                                      "Potentially exploitable security issue"),
  6:  ("GSCookie",      "FAST_FAIL_GS_COOKIE_INIT",                                   "Potentially exploitable security issue"),
  # TODO: It may be possible to check if an AppExit is an R6025: this only happens on x86, the first frame should be
  # "application!abort" and the second frame should be a non-static call (e.g. CALL EAX) from the application.
  # However, I'm worried about false positives and this does not appear to happen often enough to warrant the expense
  # of creating code for it at the moment.
  7:  ("AppExit",       "Fatal application error, possibly a pure virtual function call (R6025)",
                                                                                      "Potentially exploitable security issue"),
  8:  ("RangeCheck",    "FAST_FAIL_RANGE_CHECK_FAILURE",                              "Potentially exploitable security issue"),
  9:  ("Registry",      "FAST_FAIL_UNSAFE_REGISTRY_ACCESS",                           "Potentially exploitable security issue"),
  10: ("GuardICall",    "Control flow guard detected a call to an invalid address",   "Potentially exploitable security issue"),
  11: ("GuardWrite",    "FAST_FAIL_GUARD_WRITE_CHECK_FAILURE",                        "Potentially exploitable security issue"),
  12: ("FiberSwitch",   "FAST_FAIL_INVALID_FIBER_SWITCH",                             "Potentially exploitable security issue"),
  13: ("SetContext",    "FAST_FAIL_INVALID_SET_OF_CONTEXT",                           "Potentially exploitable security issue"),
  14: ("RefCount",      "A reference counter was incremented beyond its maximum",     "Potentially exploitable security issue"),
  18: ("JumpBuffer",    "FAST_FAIL_INVALID_JUMP_BUFFER",                              "Potentially exploitable security issue"),
  19: ("MrData",        "FAST_FAIL_MRDATA_MODIFIED",                                  "Potentially exploitable security issue"),
  20: ("Cert",          "FAST_FAIL_CERTIFICATION_FAILURE",                            "Potentially exploitable security issue"),
  21: ("ExceptChain",   "FAST_FAIL_INVALID_EXCEPTION_CHAIN",                          "Potentially exploitable security issue"),
  22: ("Crypto",        "FAST_FAIL_CRYPTO_LIBRARY",                                   "Potentially exploitable security issue"),
  23: ("DllCallout",    "FAST_FAIL_INVALID_CALL_IN_DLL_CALLOUT"                       "Potentially exploitable security issue"),
  24: ("ImageBase",     "FAST_FAIL_INVALID_IMAGE_BASE",                               "Potentially exploitable security issue"),
  25: ("DLoadProt",     "FAST_FAIL_DLOAD_PROTECTION_FAILURE",                         "Potentially exploitable security issue"),
  26: ("ExtCall",       "FAST_FAIL_UNSAFE_EXTENSION_CALL",                            "Potentially exploitable security issue"),
};
auErrorCodesForWhichAStackDumpIsUseful = [
  0, #LegacyGS
  2, #StackCookie
  4, #BadStack
];

# Some fast fail exceptions may indicate other bugs:
ddtxBugTranslations_by_sFastFailCodeId = {
  "AppExit": {
    "PureCall": (
      "Pure virtual function call (R6025)",
      "This is a potentially exploitable security issue",
      [
        [ # MSVCRT
          "*!abort",
          "*!_purecall",
        ],
        [
          "*!abort",
          "*!purecall",
        ],
      ],
    ),
    None: (
      None,
      None,
      [
        [ # Edge - these appear every now and then, I think they can safely be ignored.
          "EMODEL.dll!wil::details::ReportFailure",
          "EMODEL.dll!wil::details::ReportFailure_Hr",
          "EMODEL.dll!wil::details::in1diag3::FailFast_Hr",
          "EMODEL.dll!LCIEStartAsTabProcess",
        ],
      ],
    ),
  },
};


def cBugReport_foAnalyzeException_STATUS_STACK_BUFFER_OVERRUN(oBugReport, oCdbWrapper, oException):
  # Parameter[0] = fail fast code
  assert len(oException.auParameters) == 1, \
      "Unexpected number of fail fast exception parameters (%d vs 1)" % len(oException.auParameters);
  uFastFailCode = oException.auParameters[0];
  sFastFailCodeId, sFastFailCodeDescription, sSecurityImpact = dtsFastFailErrorInformation_by_uCode.get( \
      uFastFailCode, ("Unknown", "unknown code", "May be a security issue"));
  sOriginalBugTypeId = oBugReport.sBugTypeId;
  dtxBugTranslations = ddtxBugTranslations_by_sFastFailCodeId.get(sFastFailCodeId);
  if dtxBugTranslations:
    oBugReport = oBugReport.foTranslate(dtxBugTranslations);
  # If the bug was not translated, continue to treat it as a fast fail call:
  if oBugReport and oBugReport.sBugTypeId == sOriginalBugTypeId:
    oBugReport.sBugTypeId += ":%s" % sFastFailCodeId;
    if sFastFailCodeDescription.startswith("FAST_FAIL_"):
      oBugReport.sBugDescription = "A critical issue was detected (code %X, fail fast code %d: %s)" % \
          (oException.uCode, uFastFailCode, sFastFailCodeDescription);
    else:
      oBugReport.sBugDescription = sFastFailCodeDescription;
    oBugReport.sSecurityImpact = sSecurityImpact;
    oBugReport.oStack.fHideTopFrames(asHiddenTopFrames);
  if uFastFailCode in auErrorCodesForWhichAStackDumpIsUseful:
    uStackPointer = oCdbWrapper.fuGetValue("@$csp");
    if not oCdbWrapper.bCdbRunning: return;
    uPointerSize = oCdbWrapper.fuGetValue("@$ptrsize");
    if not oCdbWrapper.bCdbRunning: return None;
    # TODO: Call !teb, parse "StackLimit:", trim stack memory dump if needed.
    oBugReport.atxMemoryDumps.append(("Stack", uStackPointer, dxBugIdConfig["uStackDumpFrames"] * uPointerSize));
    oBugReport.atxMemoryRemarks.append(("Stack pointer", uStackPointer, uPointerSize));
    
  return oBugReport;
