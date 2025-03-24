# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import)

import os
import pytest

from briefdruckzentrum.api import Client, Order


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(BASE_DIR, 'fixtures')

VALID_RESPONSE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Auftrag>'
    '  <Files>'
    '    <DruckbareDaten>'
    '      <Datei>'
    '        <Name>LICENSE.pdf</Name>'
    '        <Seitenanzahl>1</Seitenanzahl>'
    '        <Betrag>39</Betrag>'
    '        <Porto>50</Porto>'
    '        <Versanddatum>15.10.2014</Versanddatum>'
    '      </Datei>'
    '    </DruckbareDaten>'
    '  </Files>'
    '  <Grundpreis>'
    '    <Betrag>0</Betrag>'
    '  </Grundpreis>'
    '  <Auftragskosten>'
    '    <Betrag>39</Betrag>'
    '    <Porto>50</Porto>'
    '    <Porto_MwSt_Frei>0</Porto_MwSt_Frei>'
    '  </Auftragskosten>'
    '</Auftrag>'
)


class TestClient(object):
    @pytest.yield_fixture
    def pdf(self):
        with open(os.path.join(FIXTURE_DIR, 'LICENSE.pdf')) as f:
            yield f

    @pytest.fixture
    def client(self):
        user = os.environ.get('USERNAME')
        password = os.environ.get('PASSWORD')
        return Client(user, password)

    @pytest.fixture
    def order(self, client, pdf):
        return client.create_order(pdf, 2, 1)

    def test_create_order(self, client, pdf):
        response = client.create_order(pdf, 2, 1)
        assert len(response.errors) == 1
        assert response.errors[0].code == 900

    def test_wrong_file(self, client):
        response = client.create_order('foo bar', 2, 1)
        assert len(response.errors) > 1
        assert response.errors[1].code == 100


class TestOrder(object):
    def test_valid_order(self):
        order = Order(VALID_RESPONSE)
        assert not order.errors
