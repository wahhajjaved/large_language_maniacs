import threading, time

from datetime import datetime, timedelta
from ams_consumer.SharedSingleton import SharedSingleton
from ams_consumer.AmsConsumerConfig import AmsConsumerConfig

class ReportThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self, name='stat_report_thread')

    def run(self):
        singleton = SharedSingleton()
        while True:
            reportPeriod = singleton.getLastStatTime() + timedelta(seconds = singleton.getConfig().getOption(AmsConsumerConfig.GENERAL, 'ReportWritMsgEveryHours'))
            if(datetime.now() > reportPeriod):
                singleton.getLog().info(singleton.getLastStatTime().strftime('Since %Y-%m-%d %H:%M:%S messages consumed: %i') %
                     singleton.getMsgConsumed())
                singleton.resetCounters()

            if(singleton.getEventSigTerm().isSet()):
                singleton.getLog().info(singleton.getLastStatTime().strftime('Since %Y-%m-%d %H:%M:%S messages consumed: %i') %
                     singleton.getMsgConsumed())
                break

            if(singleton.getEventSigUsr1().isSet()):
                singleton.getLog().info(singleton.getLastStatTime().strftime('Since %Y-%m-%d %H:%M:%S messages consumed: %i') %
                     singleton.getMsgConsumed())
                singleton.getEventSigUsr1().clear()

            #singleton.getLog().info('tredovaca ljuta')
            time.sleep(1)


