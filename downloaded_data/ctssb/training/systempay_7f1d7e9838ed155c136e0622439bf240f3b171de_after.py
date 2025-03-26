
class SignatureError(Exception):
    """
    Systempay signature check error
    """
    def __init__(self, message, response):
        super(SignatureError, self).__init__(message)

        self.response = response


class SystempayError(Exception):
    """
    Systempay Error
    """
    def __init__(self, message, error_code, extended_error_code, response):
        super(SystempayError, self).__init__(message)

        self.error_code = error_code
        self.extended_error_code = extended_error_code
        self.response = response
