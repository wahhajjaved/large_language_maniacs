#!/usr/bin/python
# -*- coding: utf-8 -*-

import appier

import crossline

from . import base

class PicaAdapter(base.BaseAdapter):
    """
    Simple adapter for the PicaPinto website to be used
    for the enter actions to be created.

    :see: https://picaponto.pt
    """

    def __init__(self):
        base.BaseAdapter.__init__(self)
        self._api = None

    @classmethod
    def ready(cls):
        base_url = appier.conf("PICA_BASE_URL", "https://picaponto.pt/")
        company = appier.conf("PICA_COMPANY", cast = int)
        return True if base_url and company else False

    def cross(self, info = None, app = None, *args, **kwargs):
        pass

    def enter(self, info = None, app = None, *args, **kwargs):
        info = info or dict()
        payload = kwargs.get("payload", {})
        entity = payload.get("entity", None)
        key = payload.get("key", None)

        # in case either no entity or no key is provided there's nothing
        # to be done for this enter operation
        if not entity or not key: return

        # ensures that the entity being used is a legitimate one, meaning
        # that the key that is provided is the expected one
        crossline.Entity.verify_g(entity, key)

        # retrieves the entity instance from the database and tries to
        # gather both the external service code and secret values in case
        # they are not available returns the control flow immediately
        entity_e = crossline.Entity.get_by_id(entity)
        code = entity_e.meta.get("pica:codigo")
        secret = entity_e.meta.get("pica:senha")
        if not code or not secret: return

        # retrieves the global configuration values that are going to be used
        # in the HTTP POST operation to the back-end service
        base_url = appier.conf("PICA_BASE_URL", "https://picaponto.pt/")
        company = appier.conf("PICA_COMPANY", cast = int)

        # runs the concrete HTTP operation, effectively persisting the
        # information on the external service
        appier.post(
            base_url + "ponto/ajax_add",
            params = dict(
                empresa_id = company,
                codigo = code,
                senha = secret,
                tipo_movimento = self._res_movement(entity)
            )
        )

    def _res_movement(self, entity):
        return "Entrada"
