import logging
from datetime import datetime, timedelta

from rx.observable import Observable, ObservableMeta
from rx.anonymousobservable import AnonymousObservable
from rx.subjects import Subject
from rx.disposables import Disposable, CompositeDisposable, \
    SingleAssignmentDisposable, SerialDisposable, RefCountDisposable
from rx.concurrency import TimeoutScheduler, timeout_scheduler, Scheduler

log = logging.getLogger("Rx")

# Rx Utils
def add_ref(xs, r):
    def subscribe(observer):
        return CompositeDisposable(r.disposable, xs.subscribe(observer))

    return AnonymousObservable(subscribe)

class ObservableTime(Observable, metaclass=ObservableMeta):

    @classmethod
    def observable_timer_timespan_and_period(cls, duetime, period, scheduler):
        log.debug("ObservableTime.observable_timer_timespan_and_period()")
        
        if duetime == period:
            def subscribe(observer):
                def action(count):
                    observer.on_next(count)
                    count += 1
                    return count

                return scheduler.schedule_periodic(period, action, 0)
            return AnonymousObservable(subscribe)

        def deferred():
            return cls.observable_timer_date_and_period(scheduler.now() + duetime, period, scheduler)
        return Observable.defer(deferred)
    
    @classmethod
    def interval(cls, period, scheduler=None):
        """Returns an observable sequence that produces a value after each period.
        1 - res = rx.Observable.interval(1000)
        2 - res = rx.Observable.interval(1000, rx.Scheduler.timeout)
        
        Keyword arguments:
        period -- Period for producing the values in the resulting sequence 
            (specified as an integer denoting milliseconds).
        scheduler -- [Optional] Scheduler to run the timer on. If not specified,
            rx.Scheduler.timeout is used.
        
        Returns an observable sequence that produces a value after each period.
        """
        
        scheduler = scheduler or TimeoutScheduler()
        return cls.observable_timer_timespan_and_period(period, period, scheduler)

    @staticmethod
    def observable_timer_date(duetime, scheduler):
        def subscribe(observer):
            def action(scheduler, state):
                observer.on_next(0)
                observer.on_completed()
            
            return scheduler.schedule_absolute(duetime, action);
        return AnonymousObservable(subscribe)

    @staticmethod
    def observable_timer_date_and_period(duetime, period, scheduler):
        p = Scheduler.normalize(period)

        def subscribe(observer):
            count = 0
            d = duetime

            def action(scheduler, state):
                nonlocal d, count
                if p > 0:
                    now = scheduler.now()
                    d = d + p
                    if d <= now:
                        d = now + p
                
                observer.on_next(count)
                count += 1
                self(d)
            
            return scheduler.schedule_recursive(d, action)
        return AnonymousObservable(subscribe)

    @staticmethod
    def observable_timer_timespan(duetime, scheduler):
        log.debug("observable_timer_timespan()")
        d = Scheduler.normalize(duetime)

        def subscribe(observer):
            def action(scheduler, state):
                log.debug("observable_timer_timespan:subscribe:action()")
                observer.on_next(0)
                observer.on_completed()
        
            return scheduler.schedule_relative(d, action)
        return AnonymousObservable(subscribe)

    @staticmethod
    def observable_timer_timespan_and_period(duetime, period, scheduler):
        if duetime == period:
            def subscribe(observer):
                def action(count):
                    observer.on_next(count)
                    return count + 1
                
                return scheduler.schedule_periodic(period, action, state=0)
            return AnonymousObservable(subscribe)

        def defer():
            return observable_timer_date_and_period(scheduler.now() + duetime, period, scheduler)
        return Observable.defer(defer)

    @classmethod
    def timer(cls, duetime, period=None, scheduler=None):
        """Returns an observable sequence that produces a value after duetime 
        has elapsed and then after each period.
        
        1 - res = Observable.timer(new Date());
        2 - res = Observable.timer(new Date(), 1000);
        3 - res = Observable.timer(new Date(), Scheduler.timeout);
        4 - res = Observable.timer(new Date(), 1000, Rx.Scheduler.timeout);
        
        5 - res = Observable.timer(5000);
        6 - res = Observable.timer(5000, 1000);
        7 - res = Observable.timer(5000, Scheduler.timeout);
        8 - res = Observable.timer(5000, 1000, Scheduler.timeout);
        
        Keyword arguments:
        duetime -- Absolute (specified as a Date object) or relative time 
            (specified as an integer denoting milliseconds) at which to produce
            the first value.</param>
        period -- [Optional] Period to produce subsequent values (specified as 
            an integer denoting milliseconds), or the scheduler to run the 
            timer on. If not specified, the resulting timer is not recurring.
        scheduler -- [Optional] Scheduler to run the timer on. If not 
            specified, the timeout scheduler is used.
        
        Returns an observable sequence that produces a value after due time has
        elapsed and then each period.
        """
        log.debug("Observable.timer(duetime=%s, period=%s)" % (duetime, period))
        
        scheduler = scheduler or timeout_scheduler
        
        if isinstance(duetime, datetime) and period is None:
            return cls.observable_timer_date(duetime, scheduler);
        
        if isinstance(duetime, datetime) and period:
            return cls.observable_timer_date_and_period(duetime, period, scheduler);
        
        if period is None:
            return cls.observable_timer_timespan(duetime, scheduler)
        
        return cls.observable_timer_timespan_and_period(duetime, period, scheduler)

    def observable_delay_timespan(self, duetime, scheduler):
        source = self
        
        def subscribe(observer):
            cancelable = SerialDisposable()
            exception = None
            active = False
            running = False
            q = []

            def on_next(notification):
                log.debug("observable_delay_timespan:subscribe:on_next()")
                nonlocal q, active, cancelable, exception, running
                should_run = False
                d = None
                
                if notification["value"].kind == 'E':
                    q = []
                    q.append(notification)
                    exception = notification["value"].exception
                    should_run = not running
                else:
                    q.append(dict(value=notification["value"], timestamp=notification["timestamp"] + duetime))
                    should_run = not active
                    active = True
                
                if should_run:
                    if exception:
                        log.error("*** Exception: %s" % exception)
                        observer.on_error(exception)
                    else:
                        d = SingleAssignmentDisposable()
                        cancelable.disposable = d

                        def action(self):
                            nonlocal q, active, running
                            if exception:
                                log.error("observable_delay_timespan:subscribe:on_next:action(), exception: %s" % exception)
                                return
                            
                            running = True
                            while True:
                                result = None
                                if len(q) and q[0]["timestamp"] <= scheduler.now():
                                    result = q.pop(0)["value"]
                                
                                if result:
                                    result.accept(observer)
                                
                                if not result:
                                    break
                            
                            should_recurse = False
                            recurse_duetime = 0
                            if len(q) > 0:
                                should_recurse = True
                                recurse_duetime = max(timedelta(0), q[0]["timestamp"] - scheduler.now())
                            else:
                                active = False
                            
                            e = exception
                            running = False
                            if e:
                                observer.on_error(e)
                            elif should_recurse:
                                self(recurse_duetime)

                        d.disposable = scheduler.schedule_recursive_with_relative(duetime, action)
            subscription = source.materialize().timestamp(scheduler).subscribe(on_next)
            return CompositeDisposable(subscription, cancelable)
        return AnonymousObservable(subscribe)

    def observable_delay_date(self, duetime, scheduler):
        def defer():
            timespan = duetime - scheduler.now()
            return self.observable_delay_timespan(timespan, scheduler)
        
        return Observable.defer(defer)

    def delay(self, duetime, scheduler=None):
        """Time shifts the observable sequence by duetime. The relative time 
        intervals between the values are preserved.
        
        1 - res = Rx.Observable.delay(datetime())
        2 - res = Rx.Observable.delay(datetime(), Scheduler.timeout)
        
        3 - res = Rx.Observable.delay(5000)
        4 - res = Rx.Observable.delay(5000, 1000, Scheduler.timeout)
        
        Keyword arguments:
        duetime -- Absolute (specified as a datetime object) or relative time 
            (specified as an integer denoting milliseconds) by which to shift 
            the observable sequence.
        scheduler -- [Optional] Scheduler to run the delay timers on. If not 
            specified, the timeout scheduler is used.
        
        Returns time-shifted sequence.
        """
        scheduler = scheduler or timeout_scheduler
        if isinstance(duetime, datetime):
            observable = self.observable_delay_date(duetime, scheduler)
        else:
            duetime = duetime if isinstance(duetime, timedelta) else timedelta(milliseconds=duetime)
            observable = self.observable_delay_timespan(duetime, scheduler)

        return observable

    def throttle(self, duetime, scheduler):
        scheduler = scheduler or timeout_scheduler
        source = self

        def subscribe(observer):
            cancelable = SerialDisposable()
            has_value = False
            value = None
            _id = 0
            
            def on_next(x):
                nonlocal _id, value, has_value, cancelable
                
                has_value = True
                value = x
                _id += 1
                current_id = _id
                d = SingleAssignmentDisposable()
                cancelable.disposable = d

                def action(scheduler, state=None):
                    nonlocal has_value
                    if has_value and _id == current_id:
                        observer.on_next(value)   
                    has_value = False
                
                d.disposable = scheduler.schedule_relative(duetime, action)

            def on_error(exception):
                nonlocal _id, has_value, cancelable

                cancelable.dispose()
                observer.on_error(exception)
                has_value = False
                _id += 1

            def on_completed():
                nonlocal cancelable, has_value, _id

                cancelable.dispose()
                if has_value:
                    observer.on_next(value)
                
                observer.on_completed()
                has_value = False
                _id += 1
            
            subscription = source.subscribe(on_next, on_error, on_completed) 
            return CompositeDisposable(subscription, cancelable)
        return AnonymousObservable(subscribe)

    def throttle_with_selector(self, throttle_duration_selector):
        """Ignores values from an observable sequence which are followed by 
        another value within a computed throttle duration.
     
        1 - res = source.delay_with_selector(function (x) { return Rx.Scheduler.timer(x + x); }); 
     
        Keyword arguments:
        throttle_duration_selector -- Selector function to retrieve a sequence 
            indicating the throttle duration for each given element.
        
        Returns the throttled sequence.
        """
        source = self

        def subscribe(observer):
            cancelable = SerialDisposable()
            has_value = False
            value = None
            _id = 0

            def on_next(x):
                nonlocal value, has_value, _id

                throttle = None
                try:
                    throttle = throttle_duration_selector(x)
                except Exception as e:
                    observer.on_error(e)
                    return
                
                has_value = True
                value = x
                _id += 1
                current_id = _id
                d = SingleAssignmentDisposable()
                cancelable.disposable = d

                def on_next(x):
                    nonlocal has_value
                    if has_value and _id == current_id:
                        observer.on_next(value)
                    
                    has_value = False
                    d.dispose()
                
                def on_completed():
                    nonlocal has_value
                    if has_value and _id == current_id:
                        observer.on_next(value)
                    
                    has_value = False
                    d.dispose()
                
                d.disposable = throttle.subscribe(on_next, observer.on_error, on_completed)
            
            def on_error(e):
                nonlocal has_value, _id
                
                cancelable.dispose()
                observer.on_error(e)
                has_value = False
                _id += 1
            
            def on_completed():
                nonlocal has_value, _id

                cancelable.dispose()
                if has_value:
                    observer.on_next(value)
                
                observer.on_completed()
                has_value = False
                _id += 1

            subscription = source.subscribe(on_next, on_error, on_completed)
            return CompositeDisposable(subscription, cancelable)
        return AnonymousObservable(subscribe)

    def window_with_time(self, timespan, timeshift=None, scheduler=None):
        source = self
        
        if timeshift is None:
            timeshift = timespan
        
        scheduler = scheduler or timeout_scheduler
        
        def subscribe(observer):
            timerD = SerialDisposable()
            next_shift = timeshift
            next_span = timespan
            total_time = 0
            q = []
            
            group_disposable = CompositeDisposable(timerD)
            ref_count_disposable = RefCountDisposable(group_disposable)
            
            def create_timer():
                nonlocal q, total_time, next_span, next_shift

                m = SingleAssignmentDisposable()
                timerD.disposable = m
                is_span = False
                is_shift = False

                if next_span == next_shift:
                    is_span = True
                    is_shift = True
                elif next_span < next_shift:
                    is_span = True
                else:
                    is_shift = True
                
                new_total_time = next_span if is_span else next_shift
                ts = new_total_time - total_time
                total_time = new_total_time
                if is_span:
                    next_span += timeshift
                
                if is_shift:
                    next_shift += timeshift
                
                def action(scheduler, state=None):
                    s = None
                    
                    if is_shift:
                        s = Subject()
                        q.append(s)
                        observer.on_next(add_ref(s, ref_count_disposable))
                    
                    if is_span:
                        s = q.pop(0)
                        s.on_completed()
                    
                    create_timer()
                m.disposable = scheduler.schedule_relative(ts, action)
            
            q.append(Subject())
            observer.on_next(add_ref(q[0], ref_count_disposable))
            create_timer()
            
            def on_next(x):
                for s in q:
                    s.on_next(x)
            
            def on_error(e):
                for s in q:
                    s.on_error(e)
                
                observer.on_error(e)
            
            def on_completed():
                for s in q:
                    s.on_completed()
                
                observer.on_completed()
            
            group_disposable.add(source.subscribe(on_next, on_error, on_completed))
            return ref_count_disposable
        return AnonymousObservable(subscribe)

    def window_with_time_or_count(self, timespan, count, scheduler=None):
        source = self
        scheduler = scheduler or timeout_scheduler

        def subscribe(observer):
            n = 0
            s = None
            timerD = SerialDisposable()
            window_id = 0
            group_disposable = CompositeDisposable(timerD)
            ref_count_disposable = RefCountDisposable(group_disposable)
            
            def create_timer(id):
                m = SingleAssignmentDisposable()
                timerD.disposable = m

                def action(scheduler, state):
                    nonlocal n, s, window_id
                    if id != window_id:
                        return
                    
                    n = 0
                    window_id += 1
                    new_id = window_id
                    s.on_completed()
                    s = Subject()
                    observer.on_next(add_ref(s, ref_count_disposable))
                    create_timer(new_id)
        
                m.disposable = scheduler.schedule_relative(timespan, action)
            
            s = Subject()
            observer.on_next(add_ref(s, ref_count_disposable))
            create_timer(0)
            
            def on_next(x):
                nonlocal s, n, window_id
                new_id = 0
                new_window = False
                s.on_next(x)
                n += 1
                if n == count:
                    new_window = True
                    n = 0
                    window_id += 1
                    new_id = window_id
                    s.on_completed()
                    s = Subject()
                    observer.on_next(add_ref(s, ref_count_disposable))
                
                if new_window:
                    create_timer(new_id)

            def on_error(e):
                s.on_error(e)
                observer.on_error(e)

            def on_completed():
                s.on_completed()
                observer.on_completed()
            
            group_disposable.add(source.subscribe(on_next, on_error, on_completed))
            return ref_count_disposable    
        return AnonymousObservable(subscribe)
    

    def buffer_with_time(self, timespan, timeshift=None, scheduler=None):
        """Projects each element of an observable sequence into zero or more 
        buffers which are produced based on timing information.
        
        1 - res = xs.bufferWithTime(1000 /*, scheduler */); // non-overlapping segments of 1 second
        2 - res = xs.bufferWithTime(1000, 500 /*, scheduler */); // segments of 1 second with time shift 0.5 seconds
        
        Keyword arguments:
        timespan -- Length of each buffer (specified as an integer denoting 
            milliseconds).
        timeshift -- [Optional] Interval between creation of consecutive 
            buffers (specified as an integer denoting milliseconds), or an 
            optional scheduler parameter. If not specified, the time shift 
            corresponds to the timespan parameter, resulting in non-overlapping
            adjacent buffers.
        scheduler -- [Optional] Scheduler to run buffer timers on. If not 
            specified, the timeout scheduler is used.
        
        Returns an observable sequence of buffers.
        """
        if not timeshift:
            timeshift = timespan
        
        scheduler = scheduler or timeout_scheduler
        
        return self.window_with_time(timespan, timeshift, scheduler) \
            .select_many(lambda x: x.to_array())
        

    def buffer_with_time_or_count(self, timespan, count, scheduler):
        """Projects each element of an observable sequence into a buffer that 
        is completed when either it's full or a given amount of time has 
        elapsed.
        
        1 - res = source.bufferWithTimeOrCount(5000, 50); # 5s or 50 items in an array
        2 - res = source.bufferWithTimeOrCount(5000, 50, Scheduler.timeout); # 5s or 50 items in an array
        
        Keyword arguments:
        timespan -- Maximum time length of a buffer.
        count -- Maximum element count of a buffer.
        scheduler -- [Optional] Scheduler to run bufferin timers on. If not 
            specified, the timeout scheduler is used.
        
        Returns an observable sequence of buffers.
        """
        scheduler = scheduler or timeout_scheduler
        return self.window_with_time_or_count(timespan, count, scheduler) \
            .select_many(lambda x: x.to_array())
    
    def time_interval(self, scheduler):
        """Records the time interval between consecutive values in an 
        observable sequence.
    
        1 - res = source.time_interval();
        2 - res = source.time_interval(Scheduler.timeout)
    
        Keyword arguments:
        scheduler -- [Optional] Scheduler used to compute time intervals. If 
            not specified, the timeout scheduler is used.
    
        Return An observable sequence with time interval information on values.
        """
        source = self
        scheduler = scheduler or timeout_scheduler

        def defer():
            last = scheduler.now()

            def selector(x):
                now = scheduler.now() 
                span = now - last
                last = now
                return dict(value=x, interval=span)
                
            return source.select(selector)
        return Observable.defer(defer)

    def timestamp(self, scheduler=None):
        """Records the timestamp for each value in an observable sequence.
      
        1 - res = source.timestamp(); // produces { value: x, timestamp: ts }
        2 - res = source.timestamp(Rx.Scheduler.timeout);
       
        scheduler -- [Optional] Scheduler used to compute timestamps. If not 
            specified, the timeout scheduler is used.
    
        Returns an observable sequence with timestamp information on values.
        """
        scheduler = scheduler or timeout_scheduler

        def projection(x):
            return {
                "value": x,
                "timestamp": scheduler.now()
            }
        return self.select(projection)

