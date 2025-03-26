from netlib import utils, tutils
from netlib.http import Headers

def test_bidi():
    b = utils.BiDi(a=1, b=2)
    assert b.a == 1
    assert b.get_name(1) == "a"
    assert b.get_name(5) is None
    tutils.raises(AttributeError, getattr, b, "c")
    tutils.raises(ValueError, utils.BiDi, one=1, two=1)


def test_hexdump():
    assert list(utils.hexdump(b"one\0" * 10))


def test_clean_bin():
    assert utils.clean_bin(b"one") == b"one"
    assert utils.clean_bin(b"\00ne") == b".ne"
    assert utils.clean_bin(b"\nne") == b"\nne"
    assert utils.clean_bin(b"\nne", False) == b".ne"
    assert utils.clean_bin(u"\u2605".encode("utf8")) == b"..."

    assert utils.clean_bin(u"one") == u"one"
    assert utils.clean_bin(u"\00ne") == u".ne"
    assert utils.clean_bin(u"\nne") == u"\nne"
    assert utils.clean_bin(u"\nne", False) == u".ne"
    assert utils.clean_bin(u"\u2605") == u"\u2605"


def test_pretty_size():
    assert utils.pretty_size(100) == "100B"
    assert utils.pretty_size(1024) == "1kB"
    assert utils.pretty_size(1024 + (1024 / 2.0)) == "1.5kB"
    assert utils.pretty_size(1024 * 1024) == "1MB"


def test_parse_url():
    with tutils.raises(ValueError):
        utils.parse_url("")

    s, h, po, pa = utils.parse_url(b"http://foo.com:8888/test")
    assert s == b"http"
    assert h == b"foo.com"
    assert po == 8888
    assert pa == b"/test"

    s, h, po, pa = utils.parse_url("http://foo/bar")
    assert s == b"http"
    assert h == b"foo"
    assert po == 80
    assert pa == b"/bar"

    s, h, po, pa = utils.parse_url(b"http://user:pass@foo/bar")
    assert s == b"http"
    assert h == b"foo"
    assert po == 80
    assert pa == b"/bar"

    s, h, po, pa = utils.parse_url(b"http://foo")
    assert pa == b"/"

    s, h, po, pa = utils.parse_url(b"https://foo")
    assert po == 443

    with tutils.raises(ValueError):
        utils.parse_url(b"https://foo:bar")

    # Invalid IDNA
    with tutils.raises(ValueError):
        utils.parse_url("http://\xfafoo")
    # Invalid PATH
    with tutils.raises(ValueError):
        utils.parse_url("http:/\xc6/localhost:56121")
    # Null byte in host
    with tutils.raises(ValueError):
        utils.parse_url("http://foo\0")
    # Port out of range
    _, _, port, _ = utils.parse_url("http://foo:999999")
    assert port == 80
    # Invalid IPv6 URL - see http://www.ietf.org/rfc/rfc2732.txt
    with tutils.raises(ValueError):
        utils.parse_url('http://lo[calhost')


def test_unparse_url():
    assert utils.unparse_url(b"http", b"foo.com", 99, b"") == b"http://foo.com:99"
    assert utils.unparse_url(b"http", b"foo.com", 80, b"/bar") == b"http://foo.com/bar"
    assert utils.unparse_url(b"https", b"foo.com", 80, b"") == b"https://foo.com:80"
    assert utils.unparse_url(b"https", b"foo.com", 443, b"") == b"https://foo.com"


def test_urlencode():
    assert utils.urlencode([('foo', 'bar')])


def test_urldecode():
    s = "one=two&three=four"
    assert len(utils.urldecode(s)) == 2


def test_get_header_tokens():
    headers = Headers()
    assert utils.get_header_tokens(headers, "foo") == []
    headers["foo"] = "bar"
    assert utils.get_header_tokens(headers, "foo") == [b"bar"]
    headers["foo"] = "bar, voing"
    assert utils.get_header_tokens(headers, "foo") == [b"bar", b"voing"]
    headers.set_all("foo", ["bar, voing", "oink"])
    assert utils.get_header_tokens(headers, "foo") == [b"bar", b"voing", b"oink"]


def test_multipartdecode():
    boundary = b'somefancyboundary'
    headers = Headers(
        content_type=b'multipart/form-data; boundary=' + boundary
    )
    content = (
        "--{0}\n"
        "Content-Disposition: form-data; name=\"field1\"\n\n"
        "value1\n"
        "--{0}\n"
        "Content-Disposition: form-data; name=\"field2\"\n\n"
        "value2\n"
        "--{0}--".format(boundary.decode()).encode()
    )

    form = utils.multipartdecode(headers, content)

    assert len(form) == 2
    assert form[0] == (b"field1", b"value1")
    assert form[1] == (b"field2", b"value2")


def test_parse_content_type():
    p = utils.parse_content_type
    assert p(b"text/html") == (b"text", b"html", {})
    assert p(b"text") is None

    v = p(b"text/html; charset=UTF-8")
    assert v == (b'text', b'html', {b'charset': b'UTF-8'})
