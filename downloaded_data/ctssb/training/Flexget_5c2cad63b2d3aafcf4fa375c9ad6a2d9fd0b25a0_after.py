import logging
import datetime
from manager import ModuleWarning

__pychecker__ = 'unusednames=parser,feed'

log = logging.getLogger('interval')

class ModuleInterval:

    """
        Allows specifying minimum interval for feed execution.

        Format: [n] [minutes|hours|days|months]
        
        Example:
        
        interval: 7 days
    """

    def register(self, manager, parser):
        manager.register('interval')
        parser.add_option('--now', action='store_true', dest='interval_ignore', default=0,
                          help='Ignore interval')
        
    def validate(self, config):
        if not isinstance(config, str):
            return ['parameter must be a string']
        return []

    def feed_start(self, feed):
        if feed.manager.options.interval_ignore or feed.manager.options.learn:
            log.info('Ignoring feed %s interval' % feed.name)
            return
        last_time = feed.cache.storedefault('last_time', datetime.datetime.today())
        amount, unit = feed.config.get('interval').split(' ')
        log.debug('amount: %s unit: %s' % (repr(amount), repr(unit)))
        params = {unit:int(amount)}
        log.debug('params: %s' % repr(params))
        try:
            next_time = last_time + datetime.timedelta(**params)
        except TypeError:
            raise ModuleWarning('Invalid configuration', log)
        log.debug('next_time: %s' % repr(next_time))
        if datetime.datetime.today() < next_time:
            log.debug('interval not met')
            feed.verbose_progress('Interval %s not met on feed %s. Use --now to override.' % (feed.config.get('interval'), feed.name), log)
            feed.abort(silent=True)
        else:
            log.debug('interval passed')
            feed.cache.store('last_time', datetime.datetime.today())