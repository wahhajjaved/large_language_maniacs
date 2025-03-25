import threading
import bisect
import time
import util

# TODO: use deque and insertion sort
class TimedQueue:
    def __init__(self):
        self.__queue = []
        self.__element_to_times = {}
        self.__time_to_elements = {}
    def __len__(self):
        return len(self.__queue)
    def put(self, element, time):
        util.dict_get_set(self.__element_to_times, element, []).append(time)
        util.dict_get_set(self.__time_to_elements, time, []).append(element)
        bisect.insort(self.__queue, time)
        return True
    def pop(self, time):
        if len(self.__queue) <= 0: return None
        if time < self.__queue[0]: return None
        time = self.__queue[0]
        element = self.__removeTime(time)
        del self.__queue[0]
        return (element, time)
    def contains(self, element):
        return element in self.__element_to_times
    def next(self):
        if not self.__queue: return None
        return self.__queue[0]
    def __removeTime(self, time):
        elements = self.__time_to_elements.get(time)
        if len(elements) <= 0: return None
        element = elements[0]
        self.__removeElement(element)
        return element
    def __removeElement(self, element):
        times = self.__element_to_times.get(element)
        if times == None or len(times) <= 0: return None
        time = times.pop(0)
        if len(times) > 0: del self.__element_to_times[element]
        elements = self.__time_to_elements[time]
        elements.remove(element)
        if len(elements) > 0: del self.__time_to_elements[time]
        return time
    def removeFirst(self, element):
        time = self.__removeElement(element)
        if time == None: return False
        index = bisect.bisect(self.__queue, time)
        del self.__queue[index - 1]
        return True

class SyncedQueue(TimedQueue):
    def __init__(self, time=time.time):
        TimedQueue.__init__(self)
        self.__condition = threading.Condition()
        self.__time = time
    def __len__(self):
        self.__condition.acquire()
        result = TimedQueue.__len__(self)
        self.__condition.release()
        return result
    def put(self, element, time):
        self.__condition.acquire()
        result = TimedQueue.put(self, element, time)
        if result: self.__condition.notifyAll()
        self.__condition.release()
        return result
    def pop(self):
        self.__condition.acquire()
        result = None
        while True:
            if len(self) <= 0:
                self.__condition.wait()
                continue
            time = self.__time()
            result = TimedQueue.pop(self, time)
            if result: break
            self.__condition.wait(self.next() - time)
        self.__condition.release()
        return result
    def next(self):
        self.__condition.acquire()
        result = TimedQueue.next(self)
        self.__condition.release()
        return result
    def contains(self, element):
        self.__condition.acquire()
        result = TimedQueue.contains(self, element)
        self.__condition.release()
        return result
    def removeFirst(self, element):
        self.__condition.acquire()
        result = TimedQueue.removeFirst(self, element)
        self.__condition.release()
        return result
