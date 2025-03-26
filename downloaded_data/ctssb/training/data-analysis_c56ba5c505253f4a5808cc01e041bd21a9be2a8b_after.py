import time
import traceback


import os

import dataanalysis.callback
import dataanalysis.core as da
import dataanalysis.emerge as emerge
import dataanalysis.graphtools
from dataanalysis.printhook import log,log_logstash
from dataanalysis.caches.delegating import SelectivelyDelegatingCache

import dqueue
import imp



try:
    import sentryclient
except ImportError:
    def get_sentry_client():
        return None
else:
    def get_sentry_client():
        return sentryclient.get_client()

from dataanalysis.printhook import get_local_log
log=get_local_log("queue")


class QueueCache(SelectivelyDelegatingCache):
    delegate_by_default=True

    def __init__(self,queue_directory="/tmp/queue"):
        super(QueueCache, self).__init__()
        self.queue_directory=queue_directory
        self.queue = dqueue.from_uri(self.queue_directory)

        print("initialized dqueue:", self.queue)

    def delegate(self, hashe, obj):
        log(self,"will delegate",obj,"as",hashe)
        task_data = dict(
            object_identity=obj.get_identity().serialize(),
        )
        r=self.queue.put(
            task_data,
            submission_data=dict(
                callbacks=obj.callbacks,
                request_origin="undefined",
            ),
        )

        if r['state'] == "done":
            #todo
            obj.process_hooks("top",obj,message="task dependencies done while delegating, strange",state="locked?", task_comment="dependencies done before task")
            #self.queue.remember(task_data) # really is a race condit: retry
            #raise Exception("delegated task already done: the task is done but cache was not stored and delegated requested: ",task_data['object_identity']['factory_name'])#
            #,task_data['object_identity']['assumptions'])

        r['task_data']=task_data
        return r

    def wipe_queue(self,kinds=["waiting"]):
        self.queue.wipe(kinds)


    def __repr__(self):
        return "["+self.__class__.__name__+": queue in \""+self.queue_directory+"\"]"


class QueueCacheWorker(object):

    def __repr__(self):
        return "[%s: %i]"%(self.__class__.__name__,id(self))

    def __init__(self,queue_directory="default"):
        self.queue_directory = queue_directory

        self.load_queue()
        print("initialized dqueue:", self.queue)

    def load_queue(self):
        self.queue = dqueue.from_uri(self.queue_directory)


    def run_task(self,task):
        task_data=task.task_data
        log("emerging from object_identity",task_data['object_identity'])
        object_identity=da.DataAnalysisIdentity.from_dict(task_data['object_identity'])
        da.reset()

        imp.reload(dataanalysis.graphtools)
        log("fresh factory knows",da.AnalysisFactory.cache)

        log(object_identity)
        A=emerge.emerge_from_identity(object_identity)
        A._da_delegation_allowed=False

        dataanalysis.callback.Callback.set_callback_accepted_classes([da.byname(object_identity.factory_name).__class__])

        for url in task.submission_info['callbacks']:
            log("setting object callback",A,url)
            A.set_callback(url)

        log("emerged object:",A)

        request_root_node=getattr(A, 'request_root_node', False)
        if request_root_node:
            final_state = "done"
        else:
            final_state = "task_done"

        try:
            result=A.get(requested_by=[repr(self)],isolated_directory_key=task.key,isolated_directory_cleanup=True)
            A.raise_stored_exceptions()
        except da.AnalysisException as e:
            A.process_hooks("top", A, message="task complete", state=final_state, task_comment="completed with failure "+repr(e))
            A.process_hooks("top", A, message="analysis exception", exception=repr(e),state="node_analysis_exception")
        except da.AnalysisDelegatedException as delegation_exception:
            final_state = "task_done"
            log("delegated dependencies:",delegation_exception)
            A.process_hooks("top",A,message="task dependencies delegated",state=final_state, task_comment="task dependencies delegated",delegation_exception=repr(delegation_exception))
            raise
        except dqueue.TaskStolen:
            raise
        except Exception as e:
            A.process_hooks("top", A, message="task complete", state=final_state, task_comment="completed with unexpected failure "+repr(e))

            client=get_sentry_client()
            if client is not None:
                client.captureException()

            raise
        else:
            A.process_hooks("top",A,message="task complete",state=final_state, task_comment="completed with success")
            return result


    def run_once(self):
        self.run_all(limited_burst=1)

    def run_all(self,burst=True,wait=10, limited_burst=None):
        log_logstash("worker", message="worker starting", worker_event="starting")
        worker_age=0

        try:
            worker_heartrate_skip=int(os.environ.get("WORKER_HEARTRATE_SKIP","0"))
        except Exception as e:
            log("problem determining worker heartrate",os.environ.get("WORKER_HEARTRATE_SKIP","UNDEFINED"))
            worker_heartrate_skip=0

        while True:
            if worker_heartrate_skip>0 and worker_age%worker_heartrate_skip==0:
                log_logstash("worker", message="worker heart rate "+repr(self.queue.info), queue_info=self.queue.info,worker_age=worker_age)
            worker_age+=1

            if limited_burst is not None and limited_burst>0 and worker_age>limited_burst:
                break

            try:
                log("trying to get a task from", self.queue)
                print("trying to get a task from", self.queue)
                task=self.queue.get()
                log("got this:",task)
                log_logstash("worker",message="worker taking task",origin="dda_worker",worker_event="taking_task",target=task.task_data['object_identity']['factory_name'])
            except dqueue.TaskStolen:
                time.sleep(wait)
                continue
            except dqueue.Empty:
                if burst:
                    break
                else:
                    time.sleep(wait)
                    continue

            try:
                self.run_task(task)
            except dqueue.TaskStolen as e:
                log("task stolen, whatever",e)
            except da.AnalysisDelegatedException as delegation_exception:
                log("found delegated dependencies:", delegation_exception.delegation_states,level='top')
                task_dependencies = [d['task_data'] for d in delegation_exception.delegation_states]
                #locked_task=dqueue.Task.from_file(self.queue.put(task.task_data)['fn'])
                #assert task.filename_key == locked_task.filename_key

                self.queue.task_locked(depends_on=task_dependencies)
                log("task locked",task)
                log_logstash("worker", message="worker task locked", origin="dda_worker", worker_event="task_done",
                             target=task.task_data['object_identity']['factory_name'])
            except Exception as e:
                log("task failed:",e)
                log_logstash("worker",message="worker task failed",origin="dda_worker",worker_event="task_failed",target=task.task_data['object_identity']['factory_name'])
                client=get_sentry_client()
                if client is not None:
                    client.captureException()
                traceback.print_exc()

                def update(task):
                    task.execution_info = dict(
                        status="failed",
                        exception=dict(
                            exception_class=e.__class__.__name__,
                            exception_message=getattr(e, 'message', repr(e)),
                            exception_args=e.args,
                            formatted_exception=traceback.format_exc(),
                        ),
                    )

                #TODO: ddasentry
         #       A.process_hooks("top",A,message="task dependencies delegated",state=final_state, task_comment="task dependencies delegated")

                self.queue.task_failed(update)
            else:
                log("DONE!")
                log_logstash("worker",message="worker task done",origin="dda_worker",worker_event="task_done",target=task.task_data['object_identity']['factory_name'])
                self.queue.task_done()

    def queue_status(self):
        return ""

        def get_task_attributes(task):
            for k in task.task_data['object_identity']['assumptions']:
                if isinstance(k,tuple) and k[0] == "ScWData":
                    return {'scw':k[1]['_da_stored_string_input_scwid']}

        r="="*80+"\n"
        for kind in "failed","done","locked","waiting","running":
            r+=kind+":"
            tasks=self.queue.list(kind)
            r += "(%i) \n" % len(tasks)
            for task_fn in tasks:
                try:
                    task=dqueue.Task.from_file(self.queue.queue_dir(kind)+"/"+task_fn)
                except Exception as e:
                    r+="> unreadable"
                else:
                    r+="> "+task_fn+": "+task.task_data['object_identity']['factory_name'] + ";"+repr(get_task_attributes(task))+"\n"
                    if task.depends_on is not None:
                        for dependency in task.depends_on:
                            r+="> > "+dependency['object_identity']['factory_name'] + ";"+repr(get_task_attributes(task)) + "\n"
            r+="\n\n"
        return r


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("queue", default=None)
    parser.add_argument('-V', dest='very_verbose',  help='...',action='store_true', default=False)
    parser.add_argument('-b', dest='burst_mode',  help='...',action='store_true', default=False)
    parser.add_argument('-B', dest='limited_burst', help='...', type=int, default=0)
    parser.add_argument('-w', dest='watch', type=int, help='...', default=0)
    parser.add_argument('-W', dest='watch_closely', type=int, help='...', default=0)
    parser.add_argument('-d', dest='delay between requests', type=int, help='...', default=10)

    args=parser.parse_args()

    if args.very_verbose:
        dataanalysis.printhook.global_permissive_output=True
        da.debug_output()

    qcworker = QueueCacheWorker(args.queue)

    if args.watch_closely > 0:
        while True:
            log(qcworker.queue_status())
            time.sleep(args.watch_closely)
    elif args.watch>0:
        while True:
            log(qcworker.queue.info)
            time.sleep(args.watch)
    else:
        qcworker.run_all(burst=args.burst_mode,limited_burst=args.limited_burst, wait=args.delay)





