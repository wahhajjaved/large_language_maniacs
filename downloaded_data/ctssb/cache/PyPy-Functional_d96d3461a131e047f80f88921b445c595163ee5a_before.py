from rpython.tool.udir import udir
import os


class AppTestSSL:
    spaceconfig = dict(usemodules=('_ssl', '_socket', 'thread'))

    def setup_class(cls):
        cls.w_nullbytecert = cls.space.wrap(os.path.join(
            os.path.dirname(__file__), 'nullbytecert.pem'))

    def test_init_module(self):
        import _ssl
        assert _ssl._SSLSocket.__module__ == '_ssl'
        assert _ssl._SSLContext.__module__ == '_ssl'

    def test_sslerror(self):
        import _ssl, _socket
        assert issubclass(_ssl.SSLError, Exception)
        assert issubclass(_ssl.SSLError, IOError)
        assert issubclass(_ssl.SSLError, _socket.error)

    def test_constants(self):
        import _ssl

        assert isinstance(_ssl.SSL_ERROR_ZERO_RETURN, int)
        assert isinstance(_ssl.SSL_ERROR_WANT_READ, int)
        assert isinstance(_ssl.SSL_ERROR_WANT_WRITE, int)
        assert isinstance(_ssl.SSL_ERROR_WANT_X509_LOOKUP, int)
        assert isinstance(_ssl.SSL_ERROR_SYSCALL, int)
        assert isinstance(_ssl.SSL_ERROR_SSL, int)
        assert isinstance(_ssl.SSL_ERROR_WANT_CONNECT, int)
        assert isinstance(_ssl.SSL_ERROR_EOF, int)
        assert isinstance(_ssl.SSL_ERROR_INVALID_ERROR_CODE, int)

        assert isinstance(_ssl.OPENSSL_VERSION_INFO, tuple)
        assert len(_ssl.OPENSSL_VERSION_INFO) == 5
        assert isinstance(_ssl.OPENSSL_VERSION, str)
        assert 'openssl' in _ssl.OPENSSL_VERSION.lower()

    def test_RAND_add(self):
        import _ssl
        if not hasattr(_ssl, "RAND_add"):
            skip("RAND_add is not available on this machine")
        raises(TypeError, _ssl.RAND_add, 4, 4)
        raises(TypeError, _ssl.RAND_add, "xyz", "zyx")
        _ssl.RAND_add("xyz", 1.2345)

    def test_RAND_status(self):
        import _ssl
        if not hasattr(_ssl, "RAND_status"):
            skip("RAND_status is not available on this machine")
        _ssl.RAND_status()

    def test_RAND_egd(self):
        import _ssl, os, stat
        if not hasattr(_ssl, "RAND_egd"):
            skip("RAND_egd is not available on this machine")
        raises(TypeError, _ssl.RAND_egd, 4)

        # you need to install http://egd.sourceforge.net/ to test this
        # execute "egd.pl entropy" in the current dir
        if (not os.access("entropy", 0) or
            not stat.S_ISSOCK(os.stat("entropy").st_mode)):
            skip("This test needs a running entropy gathering daemon")
        _ssl.RAND_egd("entropy")

    def test_sslwrap(self):
        import _ssl, _socket, sys, gc
        if sys.platform == 'darwin' or 'freebsd' in sys.platform:
            skip("hangs indefinitely on OSX & FreeBSD (also on CPython)")
        s = _socket.socket()
        if sys.version_info < (2, 7, 9):
            ss = _ssl.sslwrap(s, 0)
        else:
            ss = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)._wrap_socket(s, 0)
        exc = raises(_socket.error, ss.do_handshake)
        if sys.platform == 'win32':
            assert exc.value.errno == 10057 # WSAENOTCONN
        else:
            assert exc.value.errno == 32 # Broken pipe
        del exc, ss, s
        gc.collect()     # force the destructor() to be called now

    def test_async_closed(self):
        import _ssl, _socket, sys, gc
        s = _socket.socket()
        s.settimeout(3)
        if sys.version_info < (2, 7, 9):
            ss = _ssl.sslwrap(s, 0)
        else:
            ss = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)._wrap_socket(s, 0)
        s.close()
        exc = raises(_ssl.SSLError, ss.write, "data")
        assert exc.value.message == 'Underlying socket has been closed.'
        del exc, ss, s
        gc.collect()     # force the destructor() to be called now

    def test_test_decode_nullbytecert(self):
        import _ssl
        p = _ssl._test_decode_cert(self.nullbytecert)
        subject = ((('countryName', 'US'),),
                   (('stateOrProvinceName', 'Oregon'),),
                   (('localityName', 'Beaverton'),),
                   (('organizationName', 'Python Software Foundation'),),
                   (('organizationalUnitName', 'Python Core Development'),),
                   (('commonName', 'null.python.org\x00example.org'),),
                   (('emailAddress', 'python-dev@python.org'),))
        assert p['subject'] == subject
        assert p['issuer'] == subject
        assert p['subjectAltName'] == \
            (('DNS', 'altnull.python.org\x00example.com'),
             ('email', 'null@python.org\x00user@example.org'),
             ('URI', 'http://null.python.org\x00http://example.org'),
             ('IP Address', '192.0.2.1'),
             ('IP Address', '2001:DB8:0:0:0:0:0:1\n'))

    def test_context(self):
        import _ssl
        s = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)

        assert type(s.options) is long
        assert s.options & _ssl.OP_NO_SSLv2
        s.options &= ~_ssl.OP_NO_SSLv2
        assert not s.options & _ssl.OP_NO_SSLv2
        raises(TypeError, "s.options = 2.5")

        assert not s.check_hostname
        exc = raises(ValueError, "s.check_hostname = True")
        assert str(exc.value) == "check_hostname needs a SSL context with " \
                                 "either CERT_OPTIONAL or CERT_REQUIRED"

        assert s.verify_mode == _ssl.CERT_NONE
        s.verify_mode = _ssl.CERT_REQUIRED
        assert s.verify_mode == _ssl.CERT_REQUIRED
        exc = raises(ValueError, "s.verify_mode = 1234")
        assert str(exc.value) == "invalid value for verify_mode"

        s.check_hostname = True
        assert s.check_hostname

        exc = raises(ValueError, "s.verify_mode = _ssl.CERT_NONE")
        assert str(exc.value) == "Cannot set verify_mode to CERT_NONE " \
                                 "when check_hostname is enabled."

    def test_set_default_verify_paths(self):
        import _ssl
        s = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        s.set_default_verify_paths()


class AppTestConnectedSSL:
    spaceconfig = {
        "usemodules": ['_ssl', '_socket', 'struct', 'binascii'],
    }

    def setup_method(self, method):
        # https://www.verisign.net/
        ADDR = "www.verisign.net", 443

        self.w_s = self.space.appexec([self.space.wrap(ADDR)], """(ADDR):
            import socket
            s = socket.socket()
            try:
                s.connect(ADDR)
            except:
                skip("no network available or issues with connection")
            return s
            """)

    def test_connect(self):
        import socket, gc
        ss = socket.ssl(self.s)
        self.s.close()
        del ss; gc.collect()

    def test_write(self):
        import socket, gc
        ss = socket.ssl(self.s)
        raises(TypeError, ss.write, 123)
        num_bytes = ss.write("hello\n")
        assert isinstance(num_bytes, int)
        assert num_bytes >= 0
        self.s.close()
        del ss; gc.collect()

    def test_read(self):
        import socket, gc
        ss = socket.ssl(self.s)
        raises(TypeError, ss.read)
        raises(TypeError, ss.read, "foo")
        ss.write("hello\n")
        data = ss.read(10)
        assert isinstance(data, str)
        self.s.close()
        del ss; gc.collect()

    def test_read_upto(self):
        import socket, gc
        ss = socket.ssl(self.s)
        raises(TypeError, ss.read, "foo")
        ss.write("hello\n")
        data = ss.read(10)
        assert isinstance(data, str)
        assert len(data) == 10
        assert ss.pending() > 50 # many more bytes to read
        self.s.close()
        del ss; gc.collect()

    def test_shutdown(self):
        import socket, ssl, sys, gc
        ss = socket.ssl(self.s)
        ss.write("hello\n")
        try:
            result = ss.shutdown()
        except socket.error, e:
            # xxx obscure case; throwing errno 0 is pretty odd...
            if e.errno == 0:
                skip("Shutdown raised errno 0. CPython does this too")
            raise
        assert result is self.s._sock
        raises(ssl.SSLError, ss.write, "hello\n")
        del ss; gc.collect()

    def test_npn_protocol(self):
        import socket, _ssl, gc
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        ctx._set_npn_protocols(b'\x08http/1.1\x06spdy/2')
        ss = ctx._wrap_socket(self.s, True,
                              server_hostname="svn.python.org")
        self.s.close()
        del ss; gc.collect()

    def test_tls_unique_cb(self):
        import ssl, sys, gc
        ss = ssl.wrap_socket(self.s)
        ss.do_handshake()
        assert isinstance(ss.get_channel_binding(), bytes)
        self.s.close()
        del ss; gc.collect()

    def test_compression(self):
        import ssl, sys, gc
        ss = ssl.wrap_socket(self.s)
        ss.do_handshake()
        assert ss.compression() in [None, 'ZLIB', 'RLE']
        self.s.close()
        del ss; gc.collect()


class AppTestConnectedSSL_Timeout(AppTestConnectedSSL):
    # Same tests, with a socket timeout
    # to exercise the poll() calls
    spaceconfig = {
        "usemodules": ['_ssl', '_socket', 'struct', 'binascii'],
    }

    def setup_class(cls):
        cls.space.appexec([], """():
            import socket; socket.setdefaulttimeout(1)
            """)

    def teardown_class(cls):
        cls.space.appexec([], """():
            import socket; socket.setdefaulttimeout(1)
            """)


class AppTestContext:
    spaceconfig = dict(usemodules=('_ssl',))

    def setup_class(cls):
        tmpfile = udir / "tmpfile.pem"
        tmpfile.write(SSL_CERTIFICATE + SSL_PRIVATE_KEY)
        cls.w_keycert = cls.space.wrap(str(tmpfile))
        tmpfile = udir / "key.pem"
        tmpfile.write(SSL_PRIVATE_KEY)
        cls.w_key = cls.space.wrap(str(tmpfile))
        tmpfile = udir / "cert.pem"
        tmpfile.write(SSL_CERTIFICATE)
        cls.w_cert = cls.space.wrap(str(tmpfile))
        tmpfile = udir / "badcert.pem"
        tmpfile.write(SSL_BADCERT)
        cls.w_badcert = cls.space.wrap(str(tmpfile))
        tmpfile = udir / "emptycert.pem"
        tmpfile.write(SSL_EMPTYCERT)
        cls.w_emptycert = cls.space.wrap(str(tmpfile))
        cls.w_dh512 = cls.space.wrap(os.path.join(
            os.path.dirname(__file__), 'dh512.pem'))

    def test_load_cert_chain(self):
        import _ssl
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        ctx.load_cert_chain(self.keycert)
        ctx.load_cert_chain(self.cert, self.key)
        raises(IOError, ctx.load_cert_chain, "inexistent.pem")
        raises(_ssl.SSLError, ctx.load_cert_chain, self.badcert)
        raises(_ssl.SSLError, ctx.load_cert_chain, self.emptycert)

    def test_load_verify_locations(self):
        import _ssl
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        ctx.load_verify_locations(self.keycert)
        ctx.load_verify_locations(cafile=self.keycert, capath=None)

        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        with open(self.keycert) as f:
            cacert_pem = f.read().decode('ascii')
        ctx.load_verify_locations(cadata=cacert_pem)
        assert ctx.cert_store_stats()["x509_ca"]

    def test_load_dh_params(self):
        import _ssl
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        ctx.load_dh_params(self.dh512)
        raises(TypeError, ctx.load_dh_params)
        raises(TypeError, ctx.load_dh_params, None)
        raises(_ssl.SSLError, ctx.load_dh_params, self.keycert)


class AppTestSSLError:
    spaceconfig = dict(usemodules=('_ssl', '_socket', 'thread'))

    def setup_class(cls):
        tmpfile = udir / "tmpfile.pem"
        tmpfile.write(SSL_CERTIFICATE + SSL_PRIVATE_KEY)
        cls.w_keycert = cls.space.wrap(str(tmpfile))

    def test_str(self):
        # The str() of a SSLError doesn't include the errno
        import _ssl
        e = _ssl.SSLError(1, "foo")
        assert str(e) == "foo"
        assert e.errno == 1
        # Same for a subclass
        e = _ssl.SSLZeroReturnError(1, "foo")
        assert str(e) == "foo"
        assert e.errno == 1

    def test_lib_reason(self):
        # Test the library and reason attributes
        import _ssl
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        exc = raises(_ssl.SSLError, ctx.load_dh_params, self.keycert)
        assert exc.value.library == 'PEM'
        assert exc.value.reason == 'NO_START_LINE'
        s = str(exc.value)
        assert s.startswith("[PEM: NO_START_LINE] no start line")

    def test_subclass(self):
        # Check that the appropriate SSLError subclass is raised
        # (this only tests one of them)
        import _ssl, _socket
        ctx = _ssl._SSLContext(_ssl.PROTOCOL_TLSv1)
        s = _socket.socket()
        try:
            s.bind(("127.0.0.1", 0))
            s.listen(5)
            c = _socket.socket()
            c.connect(s.getsockname())
            c.setblocking(False)
            
            c = ctx._wrap_socket(c, False)
            try:
                exc = raises(_ssl.SSLWantReadError, c.do_handshake)
                msg= str(exc.value)
                assert msg.startswith("The operation did not complete (read)")
                # For compatibility
                assert exc.value.errno == _ssl.SSL_ERROR_WANT_READ
            finally:
                c.shutdown()
        finally:
            s.close()

SSL_CERTIFICATE = """
-----BEGIN CERTIFICATE-----
MIICVDCCAb2gAwIBAgIJANfHOBkZr8JOMA0GCSqGSIb3DQEBBQUAMF8xCzAJBgNV
BAYTAlhZMRcwFQYDVQQHEw5DYXN0bGUgQW50aHJheDEjMCEGA1UEChMaUHl0aG9u
IFNvZnR3YXJlIEZvdW5kYXRpb24xEjAQBgNVBAMTCWxvY2FsaG9zdDAeFw0xMDEw
MDgyMzAxNTZaFw0yMDEwMDUyMzAxNTZaMF8xCzAJBgNVBAYTAlhZMRcwFQYDVQQH
Ew5DYXN0bGUgQW50aHJheDEjMCEGA1UEChMaUHl0aG9uIFNvZnR3YXJlIEZvdW5k
YXRpb24xEjAQBgNVBAMTCWxvY2FsaG9zdDCBnzANBgkqhkiG9w0BAQEFAAOBjQAw
gYkCgYEA21vT5isq7F68amYuuNpSFlKDPrMUCa4YWYqZRt2OZ+/3NKaZ2xAiSwr7
6MrQF70t5nLbSPpqE5+5VrS58SY+g/sXLiFd6AplH1wJZwh78DofbFYXUggktFMt
pTyiX8jtP66bkcPkDADA089RI1TQR6Ca+n7HFa7c1fabVV6i3zkCAwEAAaMYMBYw
FAYDVR0RBA0wC4IJbG9jYWxob3N0MA0GCSqGSIb3DQEBBQUAA4GBAHPctQBEQ4wd
BJ6+JcpIraopLn8BGhbjNWj40mmRqWB/NAWF6M5ne7KpGAu7tLeG4hb1zLaldK8G
lxy2GPSRF6LFS48dpEj2HbMv2nvv6xxalDMJ9+DicWgAKTQ6bcX2j3GUkCR0g/T1
CRlNBAAlvhKzO7Clpf9l0YKBEfraJByX
-----END CERTIFICATE-----
"""

SSL_PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
MIICdwIBADANBgkqhkiG9w0BAQEFAASCAmEwggJdAgEAAoGBANtb0+YrKuxevGpm
LrjaUhZSgz6zFAmuGFmKmUbdjmfv9zSmmdsQIksK++jK0Be9LeZy20j6ahOfuVa0
ufEmPoP7Fy4hXegKZR9cCWcIe/A6H2xWF1IIJLRTLaU8ol/I7T+um5HD5AwAwNPP
USNU0Eegmvp+xxWu3NX2m1Veot85AgMBAAECgYA3ZdZ673X0oexFlq7AAmrutkHt
CL7LvwrpOiaBjhyTxTeSNWzvtQBkIU8DOI0bIazA4UreAFffwtvEuPmonDb3F+Iq
SMAu42XcGyVZEl+gHlTPU9XRX7nTOXVt+MlRRRxL6t9GkGfUAXI3XxJDXW3c0vBK
UL9xqD8cORXOfE06rQJBAP8mEX1ERkR64Ptsoe4281vjTlNfIbs7NMPkUnrn9N/Y
BLhjNIfQ3HFZG8BTMLfX7kCS9D593DW5tV4Z9BP/c6cCQQDcFzCcVArNh2JSywOQ
ZfTfRbJg/Z5Lt9Fkngv1meeGNPgIMLN8Sg679pAOOWmzdMO3V706rNPzSVMME7E5
oPIfAkEA8pDddarP5tCvTTgUpmTFbakm0KoTZm2+FzHcnA4jRh+XNTjTOv98Y6Ik
eO5d1ZnKXseWvkZncQgxfdnMqqpj5wJAcNq/RVne1DbYlwWchT2Si65MYmmJ8t+F
0mcsULqjOnEMwf5e+ptq5LzwbyrHZYq5FNk7ocufPv/ZQrcSSC+cFwJBAKvOJByS
x56qyGeZLOQlWS2JS3KJo59XuLFGqcbgN9Om9xFa41Yb4N9NvplFivsvZdw3m1Q/
SPIXQuT8RMPDVNQ=
-----END PRIVATE KEY-----
"""
SSL_BADCERT = """
-----BEGIN RSA PRIVATE KEY-----
MIICXwIBAAKBgQC8ddrhm+LutBvjYcQlnH21PPIseJ1JVG2HMmN2CmZk2YukO+9L
opdJhTvbGfEj0DQs1IE8M+kTUyOmuKfVrFMKwtVeCJphrAnhoz7TYOuLBSqt7lVH
fhi/VwovESJlaBOp+WMnfhcduPEYHYx/6cnVapIkZnLt30zu2um+DzA9jQIDAQAB
AoGBAK0FZpaKj6WnJZN0RqhhK+ggtBWwBnc0U/ozgKz2j1s3fsShYeiGtW6CK5nU
D1dZ5wzhbGThI7LiOXDvRucc9n7vUgi0alqPQ/PFodPxAN/eEYkmXQ7W2k7zwsDA
IUK0KUhktQbLu8qF/m8qM86ba9y9/9YkXuQbZ3COl5ahTZrhAkEA301P08RKv3KM
oXnGU2UHTuJ1MAD2hOrPxjD4/wxA/39EWG9bZczbJyggB4RHu0I3NOSFjAm3HQm0
ANOu5QK9owJBANgOeLfNNcF4pp+UikRFqxk5hULqRAWzVxVrWe85FlPm0VVmHbb/
loif7mqjU8o1jTd/LM7RD9f2usZyE2psaw8CQQCNLhkpX3KO5kKJmS9N7JMZSc4j
oog58yeYO8BBqKKzpug0LXuQultYv2K4veaIO04iL9VLe5z9S/Q1jaCHBBuXAkEA
z8gjGoi1AOp6PBBLZNsncCvcV/0aC+1se4HxTNo2+duKSDnbq+ljqOM+E7odU+Nq
ewvIWOG//e8fssd0mq3HywJBAJ8l/c8GVmrpFTx8r/nZ2Pyyjt3dH1widooDXYSV
q6Gbf41Llo5sYAtmxdndTLASuHKecacTgZVhy0FryZpLKrU=
-----END RSA PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
Just bad cert data
-----END CERTIFICATE-----
-----BEGIN RSA PRIVATE KEY-----
MIICXwIBAAKBgQC8ddrhm+LutBvjYcQlnH21PPIseJ1JVG2HMmN2CmZk2YukO+9L
opdJhTvbGfEj0DQs1IE8M+kTUyOmuKfVrFMKwtVeCJphrAnhoz7TYOuLBSqt7lVH
fhi/VwovESJlaBOp+WMnfhcduPEYHYx/6cnVapIkZnLt30zu2um+DzA9jQIDAQAB
AoGBAK0FZpaKj6WnJZN0RqhhK+ggtBWwBnc0U/ozgKz2j1s3fsShYeiGtW6CK5nU
D1dZ5wzhbGThI7LiOXDvRucc9n7vUgi0alqPQ/PFodPxAN/eEYkmXQ7W2k7zwsDA
IUK0KUhktQbLu8qF/m8qM86ba9y9/9YkXuQbZ3COl5ahTZrhAkEA301P08RKv3KM
oXnGU2UHTuJ1MAD2hOrPxjD4/wxA/39EWG9bZczbJyggB4RHu0I3NOSFjAm3HQm0
ANOu5QK9owJBANgOeLfNNcF4pp+UikRFqxk5hULqRAWzVxVrWe85FlPm0VVmHbb/
loif7mqjU8o1jTd/LM7RD9f2usZyE2psaw8CQQCNLhkpX3KO5kKJmS9N7JMZSc4j
oog58yeYO8BBqKKzpug0LXuQultYv2K4veaIO04iL9VLe5z9S/Q1jaCHBBuXAkEA
z8gjGoi1AOp6PBBLZNsncCvcV/0aC+1se4HxTNo2+duKSDnbq+ljqOM+E7odU+Nq
ewvIWOG//e8fssd0mq3HywJBAJ8l/c8GVmrpFTx8r/nZ2Pyyjt3dH1widooDXYSV
q6Gbf41Llo5sYAtmxdndTLASuHKecacTgZVhy0FryZpLKrU=
-----END RSA PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
Just bad cert data
-----END CERTIFICATE-----
"""
SSL_EMPTYCERT = ""
