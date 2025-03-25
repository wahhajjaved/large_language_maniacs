import falcon
from blog.hooks.users import is_admin
from blog.settings import settings, save_settings, SettingsSerializer
from blog.resources.base import BaseResource
from blog.utils.serializers import from_json, to_json


class BlogSettingsResource(BaseResource):

    route = '/v1/blog/admin/settings'

    @falcon.before(is_admin)
    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.body = to_json(settings, SettingsSerializer)

    @falcon.before(is_admin)
    def on_put(self, req, resp):
        resp.status = falcon.HTTP_204
        payload = req.stream.read()
        save_settings(from_json(SettingsSerializer, payload))
