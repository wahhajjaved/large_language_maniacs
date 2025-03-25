import multiprocessing as mp
import logging, os, sys
import tempfile, datetime, time
progressLoaded = True
try:
    from utils.utilities import initializeProgressBar
except:
    progressLoaded = False

class worker(mp.Process):
    """
    @brief worker class that a dequeues a task from an input queue, perform a specified
    computation, and store the results until the input queue is empty
    """
    
    def __init__(self, task_queue, result_queue, except_event, pbar=None):
        
        # initialize a new Process for each worker
        mp.Process.__init__(self)
        
        self.exit = mp.Event()
        
        # save the task and results queue
        self.task_queue   = task_queue 
        self.result_queue = result_queue 
        
        # handle the progress bar
        if pbar is not None:
            
            self.pbar = pbar
        else:
            self.pbar = None


        # handle an exception
        self.exception = except_event
            
        return

    def run(self):
        """
        @brief start the worker class doing the tasks until there
        are none left
        """
        i = 0
        # pull tasks until there are none left and we don't exit
        while not self.exception.is_set() and self.exit.is_set():
            
            # dequeue the next task
            next_task = self.task_queue.get()
            
            # task == None means we should exit
            if next_task is None:
                self.exit.set()
            
            # try to update the progress bar
            if self.pbar is not None:
                try: 
                    self.pbar.update(next_task.num+1)
                except:
                    self.exception.set()
                    raise
                    
            # try to do the work
            try:  
                answer = next_task()
                self.result_queue.put(answer)
            # set the exception event so main process knows to exit, and then raise the exception
            except:
                self.exception.set()
                raise
            
            i += 1
        
        print 'returning from worker...'   
        return 0
    
class task(object):
    """
    @brief a class representing a 'task' where a specified computation
    is performed
    """
    
    def __init__(self, function, *args, **kwargs):
        
        self.func = function
        self.args = args
        self.num = kwargs.get('num', 0)
        
        
    def __call__(self):
        
        # call the function with the arguments
        ans = self.func(*self.args)
    
        return ans



class mp_master(object):
    """
    @brief a class to control a multiprocessing job 
    """
    
    def __init__(self, nprocs, njobs, progress=True, log=True):
        """
        @brief initialize the input/output queues and make the workers
        """
        
        # set up the queues
        self.results = mp.Queue()
        self.tasks = mp.Queue()
        
        self.log = log
        if self.log:
        
            # redirect stderr to a file
            self.temp_stderr = tempfile.TemporaryFile()
            sys.stderr = self.temp_stderr
        
            # make a unique file name for std out
            fileName, extension = os.path.splitext(os.path.basename(sys.argv[0]))
            timeStamp = time.gmtime(time.time())
            formatString = "%Y-%m-%d-%H-%M-%S"
            timeStamp = time.strftime(formatString, timeStamp)
            self.stdout = open(os.getcwd() + os.sep + "%s.%s.log" %(fileName, timeStamp), 'w')
            sys.stdout = self.stdout
        
            # set up the logger to log to sys.stderr
            self.logger = mp.log_to_stderr()
            self.logger.setLevel(logging.INFO)
        
        # if we want a progress bar
        if progress and progressLoaded:
            bar = initializeProgressBar(njobs, fd=sys.__stderr__)
        else:
            bar = None
        
        # create an exception event
        self.exception = mp.Event()
         
        # start a worker for each cpu available
        print 'creating %d workers' % nprocs
        self.workers = [ worker(self.tasks, self.results, self.exception, pbar=bar) for i in range(nprocs) ]
        
        return
    
    def enqueue(self, task):
        """
        @brief enqueue a task onto the tasks queue
        """
        
        self.tasks.put(task)
        
        return
        
    def run(self):
        """
        @brief start the workers and do the work
        """
        
        # make sure to catch exceptions
        try: 
            # start the work
            for w in self.workers:
                w.start()
            
            # add a poison pill for each worker
            for i in range(len(self.workers)):
                self.tasks.put(None)
                
            # wait for all processes to finish
            # for w in self.workers:
            #     w.join()
            
            # if exception, raise
            if self.exception.is_set():
                raise
        except:
            
            # close all the workers gracefully
            for w in self.workers:
               w.terminate()
               w.join()
        finally: 
            
            # append the temp stderr to stdout file
            if self.log:
                self.stdout.write('%s\n' %('-'*100))
                self.temp_stderr.seek(0)
                self.stdout.write(self.temp_stderr.read())
                self.stdout.write('%s\n' %('-'*100))
            
            # summary
            self.info()
        
        return
        
    def dequeue(self):
        """
        @brief dequeue the results, if available, else None
        """
        
        return self.results.get()

    def more_results(self):
        """
        @brief return True if there are more results to dequeue
        """
        
        return not self.results.empty()
    
    def info(self):
        """
        @brief summarize process info
        """
        
        # print out exit codes
        for w in self.workers:
            sys.stdout.write("exit code for Process '%s' is %s\n" % (w.name, w.exitcode))
            
        # print out finish time
        now = datetime.datetime.now()
        sys.stdout.write("job finished at %s\n\n" %str(now))
        
        return
        
    
