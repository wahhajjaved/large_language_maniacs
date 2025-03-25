

class LucidSdaConfiguration(object):
    """ Base configuration for Lucid SDA, not collection specific"""
    def __init__(self, baseUrl, httpAuth):
        self.baseUrl = baseUrl
        self.sdaUrl = baseUrl + "/sda/v1/client"
        self.lweBaseUrl = baseUrl + "/sda/v1/lucidworks"
        self.httpAuth = httpAuth

    @staticmethod
    def defaultConf():
        """ Instantiate the default configuration based on what's
            specified in config.py. Useful for some of the scripts
            executed from the shell (lsColls, etc)"""
        from config import lwbdUrl, userAndPass
        baseUrl = lwbdUrl
        lucidAuth = userAndPass
        return LucidSdaConfiguration(baseUrl,
                                     lucidAuth)

    @property
    def collectionBaseUrl(self):
        """ Base URL of the collection"""
        return self.sdaUrl + "/collections"

    @property
    def jobsUrl(self):
        """ Base URL of the jobs """
        return self.sdaUrl + "/jobs"

    @property
    def pingUrl(self):
        return self.baseUrl + "/sda/v1/ping"


class LucidCollConfiguration(LucidSdaConfiguration):
    """ Collection knowing configuration"""
    def __init__(self, collectionName, url, httpAuth):
        super(LucidCollConfiguration, self).__init__(url, httpAuth, None)
        self.collectionName = collectionName

    @staticmethod
    def fromBase(baseConf, collectionName):
        return LucidCollConfiguration(collectionName,
                                      url=baseConf.baseUrl,
                                      httpAuth=baseConf.httpAuth)

    @staticmethod
    def defaultConf(collectionName):
        baseConf = LucidSdaConfiguration.defaultConf()
        thisConf = LucidCollConfiguration.fromBase(baseConf, collectionName)
        return thisConf

    @property
    def searchUrl(self):
        """ URL of the paired collection on LucidSearch"""
        return self.lweBaseUrl + \
            "/collections/" + self.collectionName

    @property
    def fieldsUrl(self):
        """ URL of the collection's fields on LucidSearch"""
        return self.lweBaseUrl + \
            "/collections/" + self.collectionName + \
            "/fields"

    @property
    def dynamicFieldsUrl(self):
        """ URL of the collection's fields on LucidSearch"""
        return self.lweBaseUrl + \
            "/collections/" + self.collectionName + \
            "/dynamicfields"

    @property
    def etlWorkflowUrl(self):
        """ URL of the etl workflow"""
        return self.sdaUrl + "/workflows/_etl"

    @property
    def collectionUrl(self):
        return self.collectionBaseUrl + "/" + self.collectionName

    @property
    def docRetrievalUrl(self):
        return self.collectionUrl + "/documents/retrieval"

    @property
    def clickTrackingUrl(self):
        return self.lweBaseUrl + \
            "/collections/" + self.collectionName + \
            "/click"

    @property
    def settingsUrl(self):
        return self.lweBaseUrl + "/collections/" + self.collectionName + \
            "/settings"

    @property
    def analysisUrl(self):
        return self.collectionUrl + \
            "/analysis"

    @property
    def fieldTypesUrl(self):
        return self.lweBaseUrl + \
            "/collections/" + self.collectionName + \
            "/fieldtypes"


def checkRespCode(respCode, url, expectedResp=200,
                  errorMsg="No Error Message Passed"):
    if respCode != expectedResp:
        ioErrorMsg = "Unsuccesful HTTP Request: Resp Code %i "\
                     "received from %s.\nMSG: %s"
        raise IOError(ioErrorMsg %
                     (respCode, url, errorMsg))
