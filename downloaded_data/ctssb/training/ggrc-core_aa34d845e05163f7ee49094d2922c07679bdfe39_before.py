# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Custom resource for related assessments

This resource works with the following queries:
  - /api/related_assessments with get parameters:
    - object_type=Control
    - object_id=XXX
    - optional: limit=from,to
    - optional: order_by=field_name,(asc|desc),[field_name,(asc|desc)]
"""

from collections import defaultdict

from werkzeug.exceptions import BadRequest, Forbidden
from flask import request

from sqlalchemy import orm
from sqlalchemy import and_

from ggrc import db
from ggrc import models
from ggrc import utils
from ggrc.utils import benchmark
from ggrc.rbac import permissions
from ggrc.services import common
from ggrc.query import pagination
from ggrc.query.exceptions import BadQueryException


class RelatedAssessmentsResource(common.Resource):
  """Resource handler for audits."""

  def patch(self):
    """PATCH operation handler."""
    raise NotImplementedError()

  def post(self, *args, **kwargs):
    """POST operation handler."""
    raise NotImplementedError()

  @classmethod
  def add_to(cls, app, url, model_class=None, decorators=()):
    view_func = cls.as_view(cls.endpoint_name())
    app.add_url_rule(url, view_func=view_func, methods=['GET'])

  def _get_assessments(self, model, object_type, object_id):
    """Get a list of assessments.

    Get a list of assessments with all their data from the db, according to the
    request GET parameters.
    """

    ids_query = model.get_similar_objects_query(object_id, "Assessment")
    order_by = self._get_order_by_parameter()
    limit = self._get_limit_parameters()

    if not permissions.has_system_wide_read():
      if not permissions.is_allowed_read(object_id, object_type, None):
        raise Forbidden()
      acl = models.all_models.AccessControlList
      acr = models.all_models.AccessControlRole
      ids_query = db.session.query(acl.object_id).join(acr).filter(
          acr.read.is_(True),
          acl.object_type == "Assessment",
          acl.object_id.in_(ids_query)
      )

    query = models.Assessment.query.options(
        orm.Load(models.Assessment).undefer_group(
            "Assessment_complete",
        ),
        orm.Load(models.Assessment).joinedload(
            "audit"
        ).undefer_group(
            "Audit_complete",
        ),
        orm.Load(models.Assessment).joinedload(
            "custom_attribute_definitions"
        ).undefer_group(
            "CustomAttributeDefinitons_complete",
        ),
        orm.Load(models.Assessment).joinedload(
            "custom_attribute_values"
        ).undefer_group(
            "CustomAttributeValues_complete",
        ),
    ).filter(
        models.Assessment.id.in_(ids_query)
    )
    if order_by:
      query = pagination.apply_order_by(
          models.Assessment,
          query,
          order_by,
          models.Assessment,
      )
    total = query.count()
    if limit:
      query = pagination.apply_limit(query, limit)
    # note that using pagination.get_total_count here would return wrong counts
    # due to query being an eager query.

    return query, total

  @classmethod
  def _get_documents(cls, assessments):
    """Get documents mapped to assessments and their mappings."""

    assessment_ids = [asmt.id for asmt in assessments]

    related_document_types = (
        models.Document.ATTACHMENT,
        models.Document.URL,
    )

    source_query = db.session.query(
        models.Relationship.destination_id.label("assessment_id"),
        models.Relationship.source_id.label("document_id")
    ).join(
        models.Document,
        and_(
            models.Relationship.source_type == models.Document.__name__,
            models.Relationship.source_id == models.Document.id
        )
    ).filter(
        models.Relationship.destination_id.in_(assessment_ids),
        models.Relationship.destination_type == models.Assessment.__name__,
        models.Document.document_type.in_(related_document_types)
    )

    destination_query = db.session.query(
        models.Relationship.source_id.label("assessment_id"),
        models.Relationship.destination_id.label("document_id")
    ).join(
        models.Document,
        and_(
            models.Relationship.destination_type == models.Document.__name__,
            models.Relationship.destination_id == models.Document.id
        )
    ).filter(
        models.Relationship.source_id.in_(assessment_ids),
        models.Relationship.source_type == models.Assessment.__name__,
        models.Document.document_type.in_(related_document_types)
    )

    assessment_document_map = defaultdict(set)
    all_document_ids = set()
    for assessment_id, document_id in source_query.union(destination_query):
      assessment_document_map[assessment_id].add(document_id)
      all_document_ids.add(document_id)

    if all_document_ids:
      documents = models.Document.query.options(
          orm.Load(models.Document).undefer_group("Document_complete")
      ).filter(
          models.Document.id.in_(all_document_ids)
      ).all()

      documents_map = {document.id: document for document in documents}

    document_json_map = {}
    for assessment in assessments:
      document_json_map[assessment.id] = [
          documents_map[document_id].log_json_base()
          for document_id in assessment_document_map[assessment.id]
      ]
    return document_json_map

  @staticmethod
  def _get_snapshots_json(assessment, assessment_snapshot_map, snapshots_map):
    """Get json representation of related snapshots.

    This does not return a full json of the snapshot but only title which is
    needed for displaying on the related assessment modal.
    """
    snapshots_json = []
    for snapshot_id in assessment_snapshot_map[assessment.id]:
      snapshot = snapshots_map[snapshot_id]
      snapshot_json = snapshot.log_json_base()
      # We avoid using snapshot.revision.log_json_base() to reduce the amount
      # of data being sent to the client.
      snapshot_json["revision"] = {
          "content": {"title": snapshot.revision.content["title"]}
      }
      snapshots_json.append(snapshot_json)
    return snapshots_json

  def _get_snapshots(self, obj, assessments):
    """Get all snapshot data for current related_assessments."""
    assessment_type = obj.__class__.__name__
    if assessment_type == "Assessment":
      assessment_type = obj.assessment_type
    assessment_ids = [asmt.id for asmt in assessments]

    assessment_snapshot_query = db.session.query(
        models.Relationship.source_id.label("assessment_id"),
        models.Relationship.destination_id.label("snapshot_id")
    ).join(
        models.Snapshot,
        and_(
            models.Relationship.destination_type == models.Snapshot.__name__,
            models.Relationship.destination_id == models.Snapshot.id
        )
    ).filter(
        models.Relationship.source_id.in_(assessment_ids),
        models.Relationship.source_type == models.Assessment.__name__,
        models.Snapshot.child_type == assessment_type
    ).union(
        db.session.query(
            models.Relationship.destination_id.label("assessment_id"),
            models.Relationship.source_id.label("snapshot_id")
        ).join(
            models.Snapshot,
            and_(
                models.Relationship.source_type == models.Snapshot.__name__,
                models.Relationship.source_id == models.Snapshot.id
            )
        ).filter(
            models.Relationship.destination_id.in_(assessment_ids),
            models.Relationship.destination_type == models.Assessment.__name__,
            models.Snapshot.child_type == assessment_type
        )
    )

    assessment_snapshot_map = defaultdict(set)
    all_snapshot_ids = set()
    for assessment_id, snapshot_id in assessment_snapshot_query:
      assessment_snapshot_map[assessment_id].add(snapshot_id)
      all_snapshot_ids.add(snapshot_id)

    snapshots = models.Snapshot.eager_inclusions(
        models.Snapshot.query.options(
            orm.Load(models.Snapshot).undefer_group("Snapshot_complete")
        ),
        ["revision"]
    ).filter(
        models.Snapshot.id.in_(all_snapshot_ids)
    ).all()

    snapshots_map = {snapshot.id: snapshot for snapshot in snapshots}

    snapshot_json_map = {}
    for assessment in assessments:
      snapshot_json_map[assessment.id] = self._get_snapshots_json(
          assessment,
          assessment_snapshot_map,
          snapshots_map,
      )

    return snapshot_json_map

  @classmethod
  def _get_order_by_parameter(cls):
    """Parse order_by parameter.

    This function parses order by parameters such as:
      - order_by=attribute_name[,(asc | desc)]

    Returns:
      list of dicts with order_by parameters for the query api pagination.
    """
    request_param = request.args.get("order_by", "")
    order_by = None
    if request_param:
      param_list = request_param.split(",")
      if len(param_list) % 2 != 0:
        raise BadRequest()

      order_by = []
      for index in range(0, len(param_list), 2):
        order_by.append({
            "name": param_list[index],
            "desc": param_list[index + 1] == "desc"
        })
    return order_by

  @classmethod
  def _get_limit_parameters(cls):
    """Parse limit parameter.

    This function parses order by parameters such as:
      - limit=from,to

    Returns:
      list with From and To integers for query pagination.
    """
    limit_string = request.args.get("limit", "")
    limit = [int(i) for i in limit_string.split(",") if i]
    if limit and len(limit) != 2:
      raise ValueError
    return limit

  def _get_assessments_json(self, obj, assessments):
    """Get json representation for all assessments in result set."""
    with benchmark("get documents of related assessments"):
      document_json_map = self._get_documents(assessments)
    with benchmark("get snapshots of related assessments"):
      snapshot_json_map = self._get_snapshots(obj, assessments)

    with benchmark("generate related_assessment json"):
      assessments_json = []
      for assessment in assessments:
        single_json = assessment.log_json_base()
        single_json["audit"] = assessment.audit.log_json_base()
        single_json["custom_attribute_values"] = [
            cav.log_json_base()
            for cav in assessment.custom_attribute_values
        ]
        single_json["custom_attribute_definitions"] = [
            cad.log_json_base()
            for cad in assessment.custom_attribute_definitions
        ]
        single_json["snapshots"] = snapshot_json_map[assessment.id]
        single_json["documents"] = document_json_map[assessment.id]
        single_json["audit"]["viewLink"] = utils.view_url_for(
            assessment.audit)
        single_json["viewLink"] = utils.view_url_for(assessment)
        assessments_json.append(single_json)
      return assessments_json

  def dispatch_request(self, *args, **kwargs):
    """Dispatch request for related_assessments."""
    with benchmark("dispatch related_assessments request"):
      try:

        if request.method != 'GET':
          raise BadRequest()

        object_type = request.args.get("object_type")
        object_id = int(request.args.get("object_id"))

        model = models.inflector.get_model(object_type)
        obj = model.query.get(object_id)

        with benchmark("get related assessments"):
          assessments, total = self._get_assessments(
              model,
              object_type,
              object_id,
          )

          assessments_json = self._get_assessments_json(obj, assessments)

          response_object = {
              "total": total,
              "data": assessments_json,
          }

          return self.json_success_response(response_object, )

      except (ValueError, TypeError, AttributeError, BadQueryException):
        # Type Error and Value Error are for invalid integer values,
        # Attribute error is for invalid models passed, which return None type
        # that does not have query attribute.
        # Bad query exception is for invalid parameters for limit such as
        # negative numbers.
        raise BadRequest()
