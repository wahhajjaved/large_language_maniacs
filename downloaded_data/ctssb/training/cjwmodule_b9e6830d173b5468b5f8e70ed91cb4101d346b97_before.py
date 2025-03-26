from cjwmodule.i18n import I18nMessage

__all__ = ["HttpError"]


def TODO_i18n(text: str) -> I18nMessage:
    return I18nMessage("TODO_i18n", {"text": text})


class HttpError(Exception):
    """
    An HTTP request did not complete.
    """

    @property
    def i18n_message(self) -> I18nMessage:
        return TODO_i18n(self.args[0])


class HttpErrorTimeout(HttpError):
    def __init__(self):
        return super().__init__("HTTP request timed out.")


class HttpErrorInvalidUrl(HttpError):
    def __init__(self):
        return super().__init__(
            "Invalid URL. Please supply a valid URL, starting with http:// or https://."
        )


class HttpErrorTooManyRedirects(HttpError):
    def __init__(self):
        return super().__init__(
            "HTTP server(s) redirected us too many times. Please try a different URL."
        )


class HttpErrorNotSuccess(HttpError):
    def __init__(self, response):
        self.response = response

    # override
    @property
    def i18n_message(self) -> I18nMessage:
        return TODO_i18n(
            "Error from server: HTTP %d %s"
            % (self.response.status_code, self.response.reason_phrase)
        )


class HttpErrorGeneric(HttpError):
    # override
    @property
    def i18n_message(self) -> I18nMessage:
        return TODO_i18n(
            "Error during HTTP request: %s" % type(self.__cause__).__name__
        )


HttpError.Timeout = HttpErrorTimeout
HttpError.Generic = HttpErrorGeneric
HttpError.InvalidUrl = HttpErrorInvalidUrl
HttpError.NotSuccess = HttpErrorNotSuccess
HttpError.TooManyRedirects = HttpErrorTooManyRedirects
