"""
Flask-restful based API implementation for re:dash.

Currently the Flask server is used to serve the static assets (and the Angular.js app),
but this is only due to configuration issues and temporary.
"""
import csv
import hashlib
import json
import cStringIO
import time
import logging

from flask import render_template, send_from_directory, make_response, request, jsonify, redirect, \
    session, url_for
from flask.ext.restful import Resource, abort
from flask_login import current_user, login_user, logout_user
import sqlparse

from redash import redis_connection, statsd_client, models, settings, utils, __version__
from redash.wsgi import app, auth, api
from redash.tasks import QueryTask, record_event
from redash.cache import headers as cache_headers
from redash.permissions import require_permission
from redash.query_runner import query_runners, validate_configuration


@app.route('/ping', methods=['GET'])
def ping():
    return 'PONG.'


@app.route('/admin/<anything>')
@app.route('/dashboard/<anything>')
@app.route('/queries')
@app.route('/queries/<query_id>')
@app.route('/queries/<query_id>/<anything>')
@app.route('/personal')
@app.route('/')
@auth.required
def index(**kwargs):
    email_md5 = hashlib.md5(current_user.email.lower()).hexdigest()
    gravatar_url = "https://www.gravatar.com/avatar/%s?s=40" % email_md5

    user = {
        'gravatar_url': gravatar_url,
        'id': current_user.id,
        'name': current_user.name,
        'email': current_user.email,
        'groups': current_user.groups,
        'permissions': current_user.permissions
    }

    features = {
        'clientSideMetrics': settings.CLIENT_SIDE_METRICS
    }

    return render_template("index.html", user=json.dumps(user), name=settings.NAME,
                           features=json.dumps(features),
                           analytics=settings.ANALYTICS)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated():
        return redirect(request.args.get('next') or '/')

    if not settings.PASSWORD_LOGIN_ENABLED:
        return redirect(url_for("google_oauth.authorize", next=request.args.get('next')))

    if request.method == 'POST':
        user = models.User.select().where(models.User.email == request.form['username']).first()
        if user and user.verify_password(request.form['password']):
            remember = ('remember' in request.form)
            login_user(user, remember=remember)
            return redirect(request.args.get('next') or '/')

    return render_template("login.html",
                           name=settings.NAME,
                           analytics=settings.ANALYTICS,
                           next=request.args.get('next'),
                           username=request.form.get('username', ''),
                           show_google_openid=settings.GOOGLE_OAUTH_ENABLED)


@app.route('/logout')
def logout():
    logout_user()
    session.pop('openid', None)

    return redirect('/login')

@app.route('/status.json')
@auth.required
@require_permission('admin')
def status_api():
    status = {}
    info = redis_connection.info()
    status['redis_used_memory'] = info['used_memory_human']
    status['version'] = __version__
    status['queries_count'] = models.Query.select().count()
    status['query_results_count'] = models.QueryResult.select().count()
    status['unused_query_results_count'] = models.QueryResult.unused().count()
    status['dashboards_count'] = models.Dashboard.select().count()
    status['widgets_count'] = models.Widget.select().count()

    status['workers'] = []

    manager_status = redis_connection.hgetall('redash:status')
    status['manager'] = manager_status
    status['manager']['outdated_queries_count'] = models.Query.outdated_queries().count()

    queues = {}
    for ds in models.DataSource.select():
        for queue in (ds.queue_name, ds.scheduled_queue_name):
            queues.setdefault(queue, set())
            queues[queue].add(ds.name)

    status['manager']['queues'] = {}
    for queue, sources in queues.iteritems():
        status['manager']['queues'][queue] = {
            'data_sources': ', '.join(sources),
            'size': redis_connection.llen(queue)
        }

    return jsonify(status)


@app.route('/api/queries/format', methods=['POST'])
@auth.required
def format_sql_query():
    arguments = request.get_json(force=True)
    query = arguments.get("query", "")

    return sqlparse.format(query, reindent=True, keyword_case='upper')


@app.route('/queries/new', methods=['POST'])
@auth.required
def create_query_route():
    query = request.form.get('query', None)
    data_source_id = request.form.get('data_source_id', None)

    if query is None or data_source_id is None:
        abort(400)

    query = models.Query.create(name="New Query",
                                query=query,
                                data_source=data_source_id,
                                user=current_user._get_current_object(),
                                ttl=-1)

    return redirect('/queries/{}'.format(query.id), 303)


class BaseResource(Resource):
    decorators = [auth.required]

    def __init__(self, *args, **kwargs):
        super(BaseResource, self).__init__(*args, **kwargs)
        self._user = None

    @property
    def current_user(self):
        return current_user._get_current_object()

    def dispatch_request(self, *args, **kwargs):
        with statsd_client.timer('requests.{}.{}'.format(request.endpoint, request.method.lower())):
            response = super(BaseResource, self).dispatch_request(*args, **kwargs)
        return response


class EventAPI(BaseResource):
    def post(self):
        events_list = request.get_json(force=True)
        for event in events_list:
            record_event.delay(event)


api.add_resource(EventAPI, '/api/events', endpoint='events')


class MetricsAPI(BaseResource):
    def post(self):
        for stat_line in request.data.split():
            stat, value = stat_line.split(':')
            statsd_client._send_stat('client.{}'.format(stat), value, 1)

        return "OK."

api.add_resource(MetricsAPI, '/api/metrics/v1/send', endpoint='metrics')


class DataSourceTypeListAPI(BaseResource):
    @require_permission("admin")
    def get(self):
        return [q.to_dict() for q in query_runners.values()]

api.add_resource(DataSourceTypeListAPI, '/api/data_sources/types', endpoint='data_source_types')


class DataSourceListAPI(BaseResource):
    def get(self):
        data_sources = [ds.to_dict() for ds in models.DataSource.all()]
        return data_sources

    @require_permission("admin")
    def post(self):
        req = request.get_json(True)
        required_fields = ('options', 'name', 'type')
        for f in required_fields:
            if f not in req:
                abort(400)

        if not validate_configuration(req['type'], req['options']):
            abort(400)

        datasource = models.DataSource.create(name=req['name'], type=req['type'], options=req['options'])

        return datasource.to_dict()


api.add_resource(DataSourceListAPI, '/api/data_sources', endpoint='data_sources')


class DashboardRecentAPI(BaseResource):
    def get(self):
        return [d.to_dict() for d in models.Dashboard.recent(current_user.id).limit(20)]


class DashboardListAPI(BaseResource):
    def get(self):
        dashboards = [d.to_dict() for d in
                      models.Dashboard.select().where(models.Dashboard.is_archived==False)]

        return dashboards

    @require_permission('create_dashboard')
    def post(self):
        dashboard_properties = request.get_json(force=True)
        dashboard = models.Dashboard(name=dashboard_properties['name'],
                                     user=self.current_user,
                                     layout='[]')
        dashboard.save()
        return dashboard.to_dict()


class DashboardAPI(BaseResource):
    def get(self, dashboard_slug=None):
        try:
            dashboard = models.Dashboard.get_by_slug(dashboard_slug)
        except models.Dashboard.DoesNotExist:
            abort(404)

        return dashboard.to_dict(with_widgets=True)

    @require_permission('edit_dashboard')
    def post(self, dashboard_slug):
        dashboard_properties = request.get_json(force=True)
        # TODO: either convert all requests to use slugs or ids
        dashboard = models.Dashboard.get_by_id(dashboard_slug)
        dashboard.layout = dashboard_properties['layout']
        dashboard.name = dashboard_properties['name']
        dashboard.save()

        return dashboard.to_dict(with_widgets=True)

    @require_permission('edit_dashboard')
    def delete(self, dashboard_slug):
        dashboard = models.Dashboard.get_by_slug(dashboard_slug)
        dashboard.is_archived = True
        dashboard.save()

api.add_resource(DashboardListAPI, '/api/dashboards', endpoint='dashboards')
api.add_resource(DashboardRecentAPI, '/api/dashboards/recent', endpoint='recent_dashboards')
api.add_resource(DashboardAPI, '/api/dashboards/<dashboard_slug>', endpoint='dashboard')


class WidgetListAPI(BaseResource):
    @require_permission('edit_dashboard')
    def post(self):
        widget_properties = request.get_json(force=True)
        widget_properties['options'] = json.dumps(widget_properties['options'])
        widget_properties.pop('id', None)
        widget_properties['dashboard'] = widget_properties.pop('dashboard_id')
        widget_properties['visualization'] = widget_properties.pop('visualization_id')
        widget = models.Widget(**widget_properties)
        widget.save()

        layout = json.loads(widget.dashboard.layout)
        new_row = True

        if len(layout) == 0 or widget.width == 2:
            layout.append([widget.id])
        elif len(layout[-1]) == 1:
            neighbour_widget = models.Widget.get(models.Widget.id == layout[-1][0])
            if neighbour_widget.width == 1:
                layout[-1].append(widget.id)
                new_row = False
            else:
                layout.append([widget.id])
        else:
            layout.append([widget.id])

        widget.dashboard.layout = json.dumps(layout)
        widget.dashboard.save()

        return {'widget': widget.to_dict(), 'layout': layout, 'new_row': new_row}


class WidgetAPI(BaseResource):
    @require_permission('edit_dashboard')
    def delete(self, widget_id):
        widget = models.Widget.get(models.Widget.id == widget_id)
        widget.delete_instance()

api.add_resource(WidgetListAPI, '/api/widgets', endpoint='widgets')
api.add_resource(WidgetAPI, '/api/widgets/<int:widget_id>', endpoint='widget')


class QuerySearchAPI(BaseResource):
    @require_permission('view_query')
    def get(self):
        term = request.args.get('q', '')

        return [q.to_dict() for q in models.Query.search(term)]


class QueryRecentAPI(BaseResource):
    @require_permission('view_query')
    def get(self):
        return [q.to_dict() for q in models.Query.recent(current_user.id).limit(20)]


class QueryListAPI(BaseResource):
    @require_permission('create_query')
    def post(self):
        query_def = request.get_json(force=True)
        for field in ['id', 'created_at', 'api_key', 'visualizations', 'latest_query_data', 'last_modified_by']:
            query_def.pop(field, None)

        query_def['user'] = self.current_user
        query_def['data_source'] = query_def.pop('data_source_id')
        query = models.Query(**query_def)
        query.save()

        return query.to_dict()

    @require_permission('view_query')
    def get(self):
        return [q.to_dict(with_stats=True) for q in models.Query.all_queries()]


class QueryAPI(BaseResource):
    @require_permission('edit_query')
    def post(self, query_id):
        query = models.Query.get_by_id(query_id)
        
        query_def = request.get_json(force=True)
        for field in ['id', 'created_at', 'api_key', 'visualizations', 'latest_query_data', 'user', 'last_modified_by']:
            query_def.pop(field, None)

        if 'latest_query_data_id' in query_def:
            query_def['latest_query_data'] = query_def.pop('latest_query_data_id')

        if 'data_source_id' in query_def:
            query_def['data_source'] = query_def.pop('data_source_id')

        query_def['last_modified_by'] = self.current_user

        # TODO: use #save() with #dirty_fields.
        models.Query.update_instance(query_id, **query_def)

        query = models.Query.get_by_id(query_id)

        return query.to_dict(with_visualizations=True)

    @require_permission('view_query')
    def get(self, query_id):
        q = models.Query.get(models.Query.id == query_id)
        if q:
            return q.to_dict(with_visualizations=True)
        else:
            abort(404, message="Query not found.")

    # TODO: move to resource of its own? (POST /queries/{id}/archive)
    def delete(self, query_id):
        q = models.Query.get(models.Query.id == query_id)

        if q:
            if q.user.id == self.current_user.id or self.current_user.has_permission('admin'):
                q.archive()
            else:
                abort(403)
        else:
            abort(404, message="Query not found.")

api.add_resource(QuerySearchAPI, '/api/queries/search', endpoint='queries_search')
api.add_resource(QueryRecentAPI, '/api/queries/recent', endpoint='recent_queries')
api.add_resource(QueryListAPI, '/api/queries', endpoint='queries')
api.add_resource(QueryAPI, '/api/queries/<query_id>', endpoint='query')


class VisualizationListAPI(BaseResource):
    @require_permission('edit_query')
    def post(self):
        kwargs = request.get_json(force=True)
        kwargs['options'] = json.dumps(kwargs['options'])
        kwargs['query'] = kwargs.pop('query_id')
        
        vis = models.Visualization(**kwargs)
        vis.save()

        return vis.to_dict(with_query=False)


class VisualizationAPI(BaseResource):
    @require_permission('edit_query')
    def post(self, visualization_id):
        kwargs = request.get_json(force=True)
        if 'options' in kwargs:
            kwargs['options'] = json.dumps(kwargs['options'])
        kwargs.pop('id', None)
        kwargs.pop('query_id', None)

        update = models.Visualization.update(**kwargs).where(models.Visualization.id == visualization_id)
        update.execute()

        vis = models.Visualization.get_by_id(visualization_id)

        return vis.to_dict(with_query=False)

    @require_permission('edit_query')
    def delete(self, visualization_id):
        vis = models.Visualization.get(models.Visualization.id == visualization_id)
        vis.delete_instance()

api.add_resource(VisualizationListAPI, '/api/visualizations', endpoint='visualizations')
api.add_resource(VisualizationAPI, '/api/visualizations/<visualization_id>', endpoint='visualization')


class QueryResultListAPI(BaseResource):
    @require_permission('execute_query')
    def post(self):
        params = request.json

        if settings.FEATURE_TABLES_PERMISSIONS:
            metadata = utils.SQLMetaData(params['query'])

            if metadata.has_non_select_dml_statements or metadata.has_ddl_statements:
                return {
                    'job': {
                        'error': 'Only SELECT statements are allowed'
                    }
                }

            if len(metadata.used_tables - current_user.allowed_tables) > 0 and '*' not in current_user.allowed_tables:
                logging.warning('Permission denied for user %s to table %s', self.current_user.name, metadata.used_tables)
                return {
                    'job': {
                        'error': 'Access denied for table(s): %s' % (metadata.used_tables)
                    }
                }

        models.ActivityLog(
            user=self.current_user,
            type=models.ActivityLog.QUERY_EXECUTION,
            activity=params['query']
        ).save()

        if params['ttl'] == 0:
            query_result = None
        else:
            query_result = models.QueryResult.get_latest(params['data_source_id'], params['query'], int(params['ttl']))

        if query_result:
            return {'query_result': query_result.to_dict()}
        else:
            data_source = models.DataSource.get_by_id(params['data_source_id'])
            job = QueryTask.add_task(params['query'], data_source)
            return {'job': job.to_dict()}


class QueryResultAPI(BaseResource):
    @staticmethod
    def csv_response(query_result):
        s = cStringIO.StringIO()

        query_data = json.loads(query_result.data)
        writer = csv.DictWriter(s, fieldnames=[col['name'] for col in query_data['columns']])
        writer.writer = utils.UnicodeWriter(s)
        writer.writeheader()
        for row in query_data['rows']:
            writer.writerow(row)

        headers = {'Content-Type': "text/csv; charset=UTF-8"}
        headers.update(cache_headers)
        return make_response(s.getvalue(), 200, headers)

    @require_permission('view_query')
    def get(self, query_id=None, query_result_id=None, filetype='json'):
        if query_result_id is None and query_id is not None:
            query = models.Query.get(models.Query.id == query_id)
            if query:
                query_result_id = query._data['latest_query_data']

        if query_result_id:
            query_result = models.QueryResult.get_by_id(query_result_id)

        if query_result:
            if isinstance(self.current_user, models.ApiUser):
                event = {
                    'user_id': None,
                    'action': 'api_get',
                    'timestamp': int(time.time()),
                    'api_key': self.current_user.id,
                    'file_type': filetype
                }

                if query_id:
                    event['object_type'] = 'query'
                    event['object_id'] = query_id
                else:
                    event['object_type'] = 'query_result'
                    event['object_id'] = query_result_id

                record_event.delay(event)

            if filetype == 'json':
                data = json.dumps({'query_result': query_result.to_dict()}, cls=utils.JSONEncoder)
                return make_response(data, 200, cache_headers)
            else:
                return self.csv_response(query_result)

        else:
            abort(404)


api.add_resource(QueryResultListAPI, '/api/query_results', endpoint='query_results')
api.add_resource(QueryResultAPI,
                 '/api/query_results/<query_result_id>',
                 '/api/queries/<query_id>/results.<filetype>',
                 '/api/queries/<query_id>/results/<query_result_id>.<filetype>',
                 endpoint='query_result')


class JobAPI(BaseResource):
    def get(self, job_id):
        # TODO: if finished, include the query result
        job = QueryTask(job_id=job_id)
        return {'job': job.to_dict()}

    def delete(self, job_id):
        job = QueryTask(job_id=job_id)
        job.cancel()

api.add_resource(JobAPI, '/api/jobs/<job_id>', endpoint='job')

@app.route('/<path:filename>')
def send_static(filename):
    return send_from_directory(settings.STATIC_ASSETS_PATH, filename)


if __name__ == '__main__':
    app.run(debug=True)



