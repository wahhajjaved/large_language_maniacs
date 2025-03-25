__author__ = 'David'
import time
import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DirectoryWatcherEventHandler(FileSystemEventHandler):
    def __init__(self, observer, global_info):
        self.observer = observer
        self.global_info = global_info

    def on_any_event(self, event):
        #Event Handler Ignores DirModifiedEvents
        if event.src_path == self.global_info.client_global_file_ignore:
            return
        if event.event_type == "modified" and event.is_directory == True:
            return
        if event.event_type == "moved" and event.is_directory == True:
            #Special Directory Moved Handling Subroutine
            return
        newEvent = str(event).replace(self.global_info.client_global_directory,"")
        newEvent = str(datetime.datetime.now('%Y-%m-%d %H:%M:%S.%f')) + newEvent
        self.global_info.client_global_event_queue.put(newEvent)
        print newEvent
        #print self.eventQueue
        #Future: Make Directory Event Queue Optimizer - Might actually be a different construct and will be called
        #when dispatcher is used


class DirectoryWatcher():
    def __init__(self, global_info):
        self.global_info = global_info

    def run(self):
        observer = Observer()
        event_handler = DirectoryWatcherEventHandler(observer, self.global_info)
        observer.schedule(event_handler, path=self.global_info.client_global_directory, recursive=True)
        print self.global_info.client_global_directory
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


