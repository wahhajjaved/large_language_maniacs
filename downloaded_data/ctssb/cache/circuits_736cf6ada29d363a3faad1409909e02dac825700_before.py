import pytest

from circuits.web import Server, Controller

from circuits.web.client import Client, Connect, Request

class Root(Controller):

    def index(self):
        return "Hello World!"

def test(webapp):
    client = Client(webapp.server.base)
    client.start()

    client.fire(Connect())
    assert pytest.wait_event(client, 'connected', target='client')

    client.fire(Request("GET", "/"))
    while client.response is None: pass

    client.stop()

    response = client.response
    assert response.status == 200
    assert response.message == "OK"

    s = response.read()
    assert s == b"Hello World!"
