# Copyright 2013: Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
SQLAlchemy implementation for DB.API
"""

import collections
import datetime as dt
import os
import time

import alembic
from alembic import config as alembic_config
import alembic.migration as alembic_migration
from alembic import script as alembic_script
from oslo_config import cfg
from oslo_db import exception as db_exc
from oslo_db.sqlalchemy import session as db_session
from oslo_utils import timeutils
import six
from sqlalchemy import or_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import load_only as sa_loadonly

from rally.common.db.sqlalchemy import models
from rally.common.i18n import _
from rally import consts
from rally import exceptions
from rally.task import atomic
from rally.task.processing import charts


CONF = cfg.CONF

_FACADE = None

INITIAL_REVISION_UUID = "ca3626f62937"


def serialize_data(data):
    if data is None:
        return None
    if isinstance(data, (six.integer_types,
                         six.string_types,
                         six.text_type,
                         dt.date,
                         dt.time,
                         float,
                         )):
        return data
    if isinstance(data, dict):
        return collections.OrderedDict((k, serialize_data(v))
                                       for k, v in data.items())
    if isinstance(data, (list, tuple)):
        return [serialize_data(i) for i in data]
    if hasattr(data, "_as_dict"):
        # NOTE(andreykurilin): it is an instance of the Model. It support a
        #   method `_as_dict`, which should transform an object into dict
        #   (quite logical as from the method name), BUT it does some extra
        #   work - tries to load properties which were marked to not be loaded
        #   in particular request and fails since the session object is not
        #   present. That is why the code bellow makes a custom transformation.
        result = {}
        for key in data.__dict__:
            if not key.startswith("_"):
                result[key] = serialize_data(getattr(data, key))
        return result

    raise ValueError(_("Can not serialize %s") % data)


def serialize(fn):
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        return serialize_data(result)
    return wrapper


def _create_facade_lazily():
    global _FACADE

    if _FACADE is None:
        _FACADE = db_session.EngineFacade.from_config(CONF)

    return _FACADE


def get_engine():
    facade = _create_facade_lazily()
    return facade.get_engine()


def get_session(**kwargs):
    facade = _create_facade_lazily()
    return facade.get_session(**kwargs)


def get_backend():
    """The backend is this module itself."""
    return Connection()


def _alembic_config():
    path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    config = alembic_config.Config(path)
    return config


class Connection(object):

    def engine_reset(self):
        global _FACADE

        _FACADE = None

    def schema_cleanup(self):
        models.drop_db()

    def schema_revision(self, config=None, engine=None, detailed=False):
        """Current database revision.

        :param config: Instance of alembic config
        :param engine: Instance of DB engine
        :param detailed: whether to return a dict with detailed data
        :rtype detailed: bool
        :returns: Database revision
        :rtype: string
        :rtype: dict
        """
        engine = engine or get_engine()
        with engine.connect() as conn:
            context = alembic_migration.MigrationContext.configure(conn)
            revision = context.get_current_revision()
        if detailed:
            config = config or _alembic_config()
            sc_dir = alembic_script.ScriptDirectory.from_config(config)
            return {"revision": revision,
                    "current_head": sc_dir.get_current_head()}
        return revision

    def schema_upgrade(self, revision=None, config=None, engine=None):
        """Used for upgrading database.

        :param revision: Desired database version
        :type revision: string
        :param config: Instance of alembic config
        :param engine: Instance of DB engine
        """
        revision = revision or "head"
        config = config or _alembic_config()
        engine = engine or get_engine()

        if self.schema_revision() is None:
            self.schema_stamp(INITIAL_REVISION_UUID, config=config)

        alembic.command.upgrade(config, revision or "head")

    def schema_create(self, config=None, engine=None):
        """Create database schema from models description.

        Can be used for initial installation instead of upgrade('head').
        :param config: Instance of alembic config
        :param engine: Instance of DB engine
        """
        engine = engine or get_engine()

        # NOTE(viktors): If we will use metadata.create_all() for non empty db
        #                schema, it will only add the new tables, but leave
        #                existing as is. So we should avoid of this situation.
        if self.schema_revision(engine=engine) is not None:
            raise db_exc.DBMigrationError("DB schema is already under version"
                                          " control. Use upgrade() instead")

        models.BASE.metadata.create_all(engine)
        self.schema_stamp("head", config=config)

    def schema_stamp(self, revision, config=None):
        """Stamps database with provided revision.

        Don't run any migrations.
        :param revision: Should match one from repository or head - to stamp
                         database with most recent revision
        :type revision: string
        :param config: Instance of alembic config
        """
        config = config or _alembic_config()
        return alembic.command.stamp(config, revision=revision)

    def model_query(self, model, session=None):
        """The helper method to create query.

        :param model: The instance of
                      :class:`rally.common.db.sqlalchemy.models.RallyBase` to
                      request it.
        :param session: Reuse the session object or get new one if it is
                        None.
        :returns: The query object.
        :raises Exception: when the model is not a sublcass of
                 :class:`rally.common.db.sqlalchemy.models.RallyBase`.
        """
        session = session or get_session()
        query = session.query(model)

        def issubclassof_rally_base(obj):
            return isinstance(obj, type) and issubclass(obj, models.RallyBase)

        if not issubclassof_rally_base(model):
            raise Exception(_("The model should be a subclass of RallyBase"))

        return query

    def _tags_get(self, uuid, tag_type, session=None):
        tags = (self.model_query(models.Tag, session=session).
                filter_by(uuid=uuid, type=tag_type).all())

        return list(set(t.tag for t in tags))

    def _uuids_by_tags_get(self, tag_type, tags):
        tags = (self.model_query(models.Tag).
                filter(models.Tag.type == tag_type,
                       models.Tag.tag.in_(tags)).all())

        return list(set(tag.uuid for tag in tags))

    def _task_get(self, uuid, load_only=None, session=None):
        pre_query = self.model_query(models.Task, session=session)
        if load_only:
            pre_query = pre_query.options(sa_loadonly(load_only))

        task = pre_query.filter_by(uuid=uuid).first()
        if not task:
            raise exceptions.TaskNotFound(uuid=uuid)
        task.tags = sorted(self._tags_get(uuid, consts.TagType.TASK, session))
        return task

    def _task_workload_data_get_all(self, workload_uuid):
        session = get_session()
        with session.begin():
            results = (self.model_query(models.WorkloadData, session=session).
                       filter_by(workload_uuid=workload_uuid).
                       order_by(models.WorkloadData.chunk_order.asc()))

        return sorted([raw for workload_data in results
                       for raw in workload_data.chunk_data["raw"]],
                      key=lambda x: x["timestamp"])

    @serialize
    def task_get(self, uuid=None, detailed=False):
        session = get_session()
        task = serialize_data(self._task_get(uuid, session=session))

        if detailed:
            task["subtasks"] = self._subtasks_get_all_by_task_uuid(
                uuid, session=session)

        return task

    @serialize
    def task_get_status(self, uuid):
        return self._task_get(uuid, load_only="status").status

    @serialize
    def task_create(self, values):
        tags = values.pop("tags", None)
        # TODO(ikhudoshyn): currently 'input_task'
        # does not come in 'values'
        # After completely switching to the new
        # DB schema in API we should reconstruct
        # input_task's from associated workloads
        # the same is true for 'pass_sla',
        # 'task_duration', 'validation_result'
        # and 'validation_duration'
        task = models.Task()
        task.update(values)
        task.save()

        if tags:
            for t in set(tags):
                tag = models.Tag()
                tag.update({"uuid": task.uuid,
                            "type": consts.TagType.TASK,
                            "tag": t})
                tag.save()
        task.tags = sorted(self._tags_get(task.uuid, consts.TagType.TASK))
        return task

    @serialize
    def task_update(self, uuid, values):
        session = get_session()
        values.pop("uuid", None)
        tags = values.pop("tags", None)
        with session.begin():
            task = self._task_get(uuid, session=session)
            task.update(values)

            if tags:
                for t in set(tags):
                    tag = models.Tag()
                    tag.update({"uuid": task.uuid,
                                "type": consts.TagType.TASK,
                                "tag": t})
                    tag.save()
            # take an updated instance of task
            task = self._task_get(uuid, session=session)
        return task

    def task_update_status(self, uuid, statuses, status_value):
        session = get_session()
        result = (
            session.query(models.Task).filter(
                models.Task.uuid == uuid, models.Task.status.in_(
                    statuses)).
            update({"status": status_value}, synchronize_session=False)
        )
        if not result:
            status = " or ".join(statuses)
            msg = _("Task with uuid='%(uuid)s' and in statuses:'"
                    "%(statuses)s' not found.'") % {"uuid": uuid,
                                                    "statuses": status}
            raise exceptions.RallyException(msg)
        return result

    @serialize
    def task_list(self, status=None, deployment=None, tags=None):
        session = get_session()
        tasks = []
        with session.begin():
            query = self.model_query(models.Task)

            filters = {}
            if status is not None:
                filters["status"] = status
            if deployment is not None:
                filters["deployment_uuid"] = self.deployment_get(
                    deployment)["uuid"]
            if filters:
                query = query.filter_by(**filters)

            if tags:
                uuids = self._uuids_by_tags_get(
                    consts.TagType.TASK, tags)
                query = query.filter(models.Task.uuid.in_(uuids))

            for task in query.all():
                task.tags = sorted(
                    self._tags_get(task.uuid, consts.TagType.TASK, session))
                tasks.append(task)

        return tasks

    def task_delete(self, uuid, status=None):
        session = get_session()
        with session.begin():
            query = base_query = (self.model_query(models.Task).
                                  filter_by(uuid=uuid))
            if status is not None:
                query = base_query.filter_by(status=status)

            (self.model_query(models.WorkloadData).filter_by(task_uuid=uuid).
             delete(synchronize_session=False))

            (self.model_query(models.Workload).filter_by(task_uuid=uuid).
             delete(synchronize_session=False))

            (self.model_query(models.Subtask).filter_by(task_uuid=uuid).
             delete(synchronize_session=False))

            (self.model_query(models.Tag).filter_by(
                uuid=uuid, type=consts.TagType.TASK).
             delete(synchronize_session=False))

            count = query.delete(synchronize_session=False)
            if not count:
                if status is not None:
                    task = base_query.first()
                    if task:
                        raise exceptions.TaskInvalidStatus(uuid=uuid,
                                                           require=status,
                                                           actual=task.status)
                raise exceptions.TaskNotFound(uuid=uuid)

    def _subtasks_get_all_by_task_uuid(self, task_uuid, session=None):
        result = (self.model_query(models.Subtask, session=session).filter_by(
            task_uuid=task_uuid).all())
        subtasks = []
        for subtask in result:
            subtask = serialize_data(subtask)
            subtask["workloads"] = []
            workloads = (self.model_query(models.Workload, session=session).
                         filter_by(subtask_uuid=subtask["uuid"]).all())
            for workload in workloads:
                workload.data = self._task_workload_data_get_all(
                    workload.uuid)
                subtask["workloads"].append(serialize_data(workload))
            subtasks.append(subtask)
        return subtasks

    @serialize
    def subtask_create(self, task_uuid, title, description=None, context=None):
        subtask = models.Subtask(task_uuid=task_uuid)
        subtask.update({
            "title": title,
            "description": description or "",
            "context": context or {},
        })
        subtask.save()
        return subtask

    @serialize
    def subtask_update(self, subtask_uuid, values):
        subtask = self.model_query(models.Subtask).filter_by(
            uuid=subtask_uuid).first()
        subtask.update(values)
        subtask.save()
        return subtask

    @serialize
    def workload_get(self, workload_uuid):
        return self.model_query(models.Workload).filter_by(
            uuid=workload_uuid).first()

    @serialize
    def workload_create(self, task_uuid, subtask_uuid, name, description,
                        position, runner, runner_type, hooks, context, sla,
                        args, context_execution, statistics):
        workload = models.Workload(task_uuid=task_uuid,
                                   subtask_uuid=subtask_uuid,
                                   name=name,
                                   description=description,
                                   position=position,
                                   runner=runner,
                                   runner_type=runner_type,
                                   hooks=hooks,
                                   context=context,
                                   sla=sla,
                                   args=args,
                                   context_execution=context_execution,
                                   statistics=statistics)
        workload.save()
        return workload

    @serialize
    def workload_data_create(self, task_uuid, workload_uuid, chunk_order,
                             data):
        workload_data = models.WorkloadData(task_uuid=task_uuid,
                                            workload_uuid=workload_uuid)

        raw_data = data.get("raw", [])
        iter_count = len(raw_data)

        failed_iter_count = 0

        started_at = float("inf")
        finished_at = 0
        for d in raw_data:
            if d.get("error"):
                failed_iter_count += 1

            timestamp = d["timestamp"]
            duration = d["duration"]
            finished = timestamp + duration

            if timestamp < started_at:
                started_at = timestamp

            if finished > finished_at:
                finished_at = finished

        now = time.time()
        if started_at == float("inf"):
            started_at = now
        if finished_at == 0:
            finished_at = now

        workload_data.update({
            "task_uuid": task_uuid,
            "workload_uuid": workload_uuid,
            "chunk_order": chunk_order,
            "iteration_count": iter_count,
            "failed_iteration_count": failed_iter_count,
            "chunk_data": {"raw": raw_data},
            # TODO(ikhudoshyn)
            "chunk_size": 0,
            "compressed_chunk_size": 0,
            "started_at": dt.datetime.fromtimestamp(started_at),
            "finished_at": dt.datetime.fromtimestamp(finished_at)
        })
        workload_data.save()
        return workload_data

    @serialize
    def workload_set_results(self, workload_uuid, subtask_uuid, task_uuid,
                             load_duration, full_duration, start_time,
                             sla_results, hooks_results):
        session = get_session()
        with session.begin():
            workload_results = self._task_workload_data_get_all(workload_uuid)

            iter_count = len(workload_results)

            failed_iter_count = 0
            max_duration = None
            min_duration = None

            for d in workload_results:
                if d.get("error"):
                    failed_iter_count += 1

                duration = d.get("duration", 0)

                if max_duration is None or duration > max_duration:
                    max_duration = duration

                if min_duration is None or min_duration > duration:
                    min_duration = duration

            atomics = collections.OrderedDict()

            for itr in workload_results:
                merged_atomic = atomic.merge_atomic(itr["atomic_actions"])
                for name, value in merged_atomic.items():
                    duration = value["duration"]
                    count = value["count"]
                    if name not in atomics or count > atomics[name]["count"]:
                        atomics[name] = {"min_duration": duration,
                                         "max_duration": duration,
                                         "count": count}
                    elif count == atomics[name]["count"]:
                        if duration < atomics[name]["min_duration"]:
                            atomics[name]["min_duration"] = duration
                        if duration > atomics[name]["max_duration"]:
                            atomics[name]["max_duration"] = duration

            durations_stat = charts.MainStatsTable(
                {"total_iteration_count": iter_count,
                 "statistics": {"atomics": atomics}})

            for itr in workload_results:
                durations_stat.add_iteration(itr)

            sla = sla_results or []
            # NOTE(ikhudoshyn): we call it 'pass_sla'
            # for the sake of consistency with other models
            # so if no SLAs were specified, then we assume pass_sla == True
            success = all([s.get("success") for s in sla])

            session.query(models.Workload).filter_by(
                uuid=workload_uuid).update(
                {
                    "sla_results": {"sla": sla},
                    "context_execution": {},
                    "hooks": hooks_results or [],
                    "load_duration": load_duration,
                    "full_duration": full_duration,
                    "min_duration": min_duration,
                    "max_duration": max_duration,
                    "total_iteration_count": iter_count,
                    "failed_iteration_count": failed_iter_count,
                    "start_time": start_time,
                    "statistics": {"durations": durations_stat.to_dict(),
                                   "atomics": atomics},
                    "pass_sla": success}
            )
            task_values = {
                "task_duration": models.Task.task_duration + load_duration}
            if not success:
                task_values["pass_sla"] = False

            subtask_values = {
                "duration": models.Subtask.duration + load_duration}
            if not success:
                subtask_values["pass_sla"] = False
            session.query(models.Task).filter_by(uuid=task_uuid).update(
                task_values)

            session.query(models.Subtask).filter_by(uuid=subtask_uuid).update(
                subtask_values)

    def _deployment_get(self, deployment, session=None):
        stored_deployment = self.model_query(
            models.Deployment,
            session=session).filter_by(name=deployment).first()
        if not stored_deployment:
            stored_deployment = self.model_query(
                models.Deployment,
                session=session).filter_by(uuid=deployment).first()

        if not stored_deployment:
            raise exceptions.DeploymentNotFound(deployment=deployment)
        return stored_deployment

    @serialize
    def deployment_create(self, values):
        deployment = models.Deployment()
        try:
            deployment.update(values)
            deployment.save()
        except db_exc.DBDuplicateEntry:
            raise exceptions.DeploymentNameExists(deployment=values["name"])
        return deployment

    def deployment_delete(self, uuid):
        session = get_session()
        with session.begin():
            count = (self.model_query(models.Resource, session=session).
                     filter_by(deployment_uuid=uuid).count())
            if count:
                raise exceptions.DeploymentIsBusy(uuid=uuid)

            count = (self.model_query(models.Deployment, session=session).
                     filter_by(uuid=uuid).delete(synchronize_session=False))
            if not count:
                raise exceptions.DeploymentNotFound(deployment=uuid)

    @serialize
    def deployment_get(self, deployment):
        return self._deployment_get(deployment)

    @serialize
    def deployment_update(self, deployment, values):
        session = get_session()
        values.pop("uuid", None)
        with session.begin():
            dpl = self._deployment_get(deployment, session=session)
            dpl.update(values)
        return dpl

    @serialize
    def deployment_list(self, status=None, parent_uuid=None, name=None):
        query = (self.model_query(models.Deployment).
                 filter_by(parent_uuid=parent_uuid))

        if name:
            query = query.filter_by(name=name)
        if status:
            query = query.filter_by(status=status)
        return query.all()

    @serialize
    def resource_create(self, values):
        resource = models.Resource()
        resource.update(values)
        resource.save()
        return resource

    @serialize
    def resource_get_all(self, deployment_uuid, provider_name=None, type=None):
        query = (self.model_query(models.Resource).
                 filter_by(deployment_uuid=deployment_uuid))
        if provider_name is not None:
            query = query.filter_by(provider_name=provider_name)
        if type is not None:
            query = query.filter_by(type=type)
        return query.all()

    def resource_delete(self, id):
        count = (self.model_query(models.Resource).
                 filter_by(id=id).delete(synchronize_session=False))
        if not count:
            raise exceptions.ResourceNotFound(id=id)

    @serialize
    def verifier_create(self, name, vtype, namespace, source, version,
                        system_wide, extra_settings=None):
        verifier = models.Verifier()
        properties = {"name": name, "type": vtype, "namespace": namespace,
                      "source": source, "extra_settings": extra_settings,
                      "version": version, "system_wide": system_wide}
        verifier.update(properties)
        verifier.save()
        return verifier

    @serialize
    def verifier_get(self, verifier_id):
        return self._verifier_get(verifier_id)

    def _verifier_get(self, verifier_id, session=None):
        verifier = self.model_query(
            models.Verifier, session=session).filter(
                or_(models.Verifier.name == verifier_id,
                    models.Verifier.uuid == verifier_id)).first()
        if not verifier:
            raise exceptions.ResourceNotFound(id=verifier_id)
        return verifier

    @serialize
    def verifier_list(self, status=None):
        query = self.model_query(models.Verifier)
        if status:
            query = query.filter_by(status=status)
        return query.all()

    def verifier_delete(self, verifier_id):
        session = get_session()
        with session.begin():
            query = self.model_query(
                models.Verifier, session=session).filter(
                    or_(models.Verifier.name == verifier_id,
                        models.Verifier.uuid == verifier_id))
            count = query.delete(synchronize_session=False)
            if not count:
                raise exceptions.ResourceNotFound(id=verifier_id)

    @serialize
    def verifier_update(self, verifier_id, properties):
        session = get_session()
        with session.begin():
            verifier = self._verifier_get(verifier_id)
            verifier.update(properties)
            verifier.save()
        return verifier

    @serialize
    def verification_create(self, verifier_id, deployment_id, tags=None,
                            run_args=None):
        verifier = self._verifier_get(verifier_id)
        deployment = self._deployment_get(deployment_id)
        verification = models.Verification()
        verification.update({"verifier_uuid": verifier.uuid,
                             "deployment_uuid": deployment["uuid"],
                             "run_args": run_args})
        verification.save()

        if tags:
            for t in set(tags):
                tag = models.Tag()
                tag.update({"uuid": verification.uuid,
                            "type": consts.TagType.VERIFICATION,
                            "tag": t})
                tag.save()

        return verification

    @serialize
    def verification_get(self, verification_uuid):
        verification = self._verification_get(verification_uuid)
        verification.tags = sorted(self._tags_get(verification.uuid,
                                                  consts.TagType.VERIFICATION))
        return verification

    def _verification_get(self, verification_uuid, session=None):
        verification = self.model_query(
            models.Verification, session=session).filter_by(
            uuid=verification_uuid).first()
        if not verification:
            raise exceptions.ResourceNotFound(id=verification_uuid)
        return verification

    @serialize
    def verification_list(self, verifier_id=None, deployment_id=None,
                          tags=None, status=None):
        session = get_session()
        with session.begin():
            filter_by = {}
            if verifier_id:
                verifier = self._verifier_get(verifier_id, session=session)
                filter_by["verifier_uuid"] = verifier.uuid
            if deployment_id:
                deployment = self._deployment_get(deployment_id,
                                                  session=session)
                filter_by["deployment_uuid"] = deployment.uuid
            if status:
                filter_by["status"] = status

            query = self.model_query(models.Verification, session=session)
            if filter_by:
                query = query.filter_by(**filter_by)

            def add_tags_to_verifications(verifications):
                for verification in verifications:
                    verification.tags = sorted(self._tags_get(
                        verification.uuid, consts.TagType.VERIFICATION))
                return verifications

            if tags:
                uuids = self._uuids_by_tags_get(
                    consts.TagType.VERIFICATION, tags)
                query = query.filter(models.Verification.uuid.in_(uuids))

        return add_tags_to_verifications(query.all())

    def verification_delete(self, verification_uuid):
        session = get_session()
        with session.begin():
            count = self.model_query(
                models.Verification, session=session).filter_by(
                uuid=verification_uuid).delete(synchronize_session=False)
        if not count:
            raise exceptions.ResourceNotFound(id=verification_uuid)

    @serialize
    def verification_update(self, verification_uuid, properties):
        session = get_session()
        with session.begin():
            verification = self._verification_get(verification_uuid)
            verification.update(properties)
            verification.save()
        return verification

    @serialize
    def register_worker(self, values):
        try:
            worker = models.Worker()
            worker.update(values)
            worker.update({"updated_at": timeutils.utcnow()})
            worker.save()
            return worker
        except db_exc.DBDuplicateEntry:
            raise exceptions.WorkerAlreadyRegistered(
                worker=values["hostname"])

    @serialize
    def get_worker(self, hostname):
        try:
            return (self.model_query(models.Worker).
                    filter_by(hostname=hostname).one())
        except NoResultFound:
            raise exceptions.WorkerNotFound(worker=hostname)

    def unregister_worker(self, hostname):
        count = (self.model_query(models.Worker).
                 filter_by(hostname=hostname).delete())
        if count == 0:
            raise exceptions.WorkerNotFound(worker=hostname)

    def update_worker(self, hostname):
        count = (self.model_query(models.Worker).
                 filter_by(hostname=hostname).
                 update({"updated_at": timeutils.utcnow()}))
        if count == 0:
            raise exceptions.WorkerNotFound(worker=hostname)
