import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def action(enabled=True):
    def f_action(func):
        def func_wrapper(self, **kwargs):
            if func.__name__ in self.settings:
                if self.settings[func.__name__]:
                    logger.debug('Task [%s] is enabled.' % func.__name__)
                    return func(self, enabled=True, **kwargs)
                else:
                    logger.debug('Task [%s] is disabled.' % func.__name__)
            else:
                logger.debug('There is no [%s] in settings file, it will run with default settings.' % func.__name__)
                if enabled:
                    return func(self, **kwargs)
                logger.debug('Task [%s] is disabled.' % func.__name__)
        return func_wrapper
    return f_action
