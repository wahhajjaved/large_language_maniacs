import couch.util.Util as util

class Stream(object):
   type = None
   httpVersion = None
   headers = {}
   body = None
   error = None
   errorData = {}
   def __init__(self, headers={}, body=None):
      self.headers = headers
      self.body = body
      # self.error = None
      # self.errorData = {}

   def __str__(self):
      return self.toString()

   def setBody(self, body=None):
      if self.__class__.__name__ == "Stream":
         raise Exception("You should re-define [<OBJECT>].setBody(self, body=None) method!")

   def getBody(self):
      return self.body

   def getBodyData(self, key=None):
      bodyData = {}
      if self.getHeader("Content-Type") == "application/json":
         bodyData = util.jsonDecode(self.body or "")
         if key != None:
            return util.dig(key, bodyData)
      return bodyData

   def setHeader(self, key, value=None):
      if value == None:
         if key in self.headers:
            del self.headers[key]
      else:
         self.headers[key] = value

   def getHeader(self, key):
      if key in self.headers:
         return self.headers[key]

   def getHeaderAll(self):
      return self.headers

   def setError(self, body=None):
      body = util.jsonDecode(body or self.body or "") or {}
      if "error" in body and "reason" in body:
         self.error = "Stream Error >> error: \"%s\", reason: \"%s\"" % \
            (body["error"], body["reason"])
         self.errorData["error"] = str(body["error"])
         self.errorData["reason"] = str(body["reason"])

   def getError(self):
      return self.error

   def getErrorValue(self, key):
      if key in self.errorData:
         return self.errorData[key]

   def toString(self, firstLine):
      ret = firstLine
      for key, value in self.headers.items():
         if value != None:
            if key == "0":
               continue
            ret += "%s: %s\r\n" % (key, value)
      ret += "\r\n"
      ret += self.getBody() or ""
      return ret

Stream.TYPE_REQUEST  = 1
Stream.TYPE_RESPONSE = 2
