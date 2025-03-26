from typing import Optional, Sequence

from mitmproxy import optmanager
from mitmproxy.net import tcp

# We redefine these here for now to avoid importing Urwid-related guff on
# platforms that don't support it, and circular imports. We can do better using
# a lazy checker down the track.
console_palettes = [
    "lowlight",
    "lowdark",
    "light",
    "dark",
    "solarized_light",
    "solarized_dark"
]
view_orders = [
    "time",
    "method",
    "url",
    "size",
]

APP_HOST = "mitm.it"
APP_PORT = 80
CA_DIR = "~/.mitmproxy"
LISTEN_PORT = 8080

# We manually need to specify this, otherwise OpenSSL may select a non-HTTP2 cipher by default.
# https://mozilla.github.io/server-side-tls/ssl-config-generator/?server=apache-2.2.15&openssl=1.0.2&hsts=yes&profile=old
DEFAULT_CLIENT_CIPHERS = (
    "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:"
    "ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:"
    "ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:"
    "DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:"
    "DHE-RSA-AES256-SHA:ECDHE-RSA-DES-CBC3-SHA:ECDHE-ECDSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:"
    "AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:AES:DES-CBC3-SHA:"
    "HIGH:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:"
    "!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA"
)


class Options(optmanager.OptManager):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.add_option(
            "onboarding", bool, True,
            "Toggle the mitmproxy onboarding app."
        )
        self.add_option(
            "onboarding_host", str, APP_HOST,
            """
            Domain to serve the onboarding app from. For transparent mode, use
            an IP when a DNS entry for the app domain is not present.             """
        )
        self.add_option(
            "onboarding_port", int, APP_PORT,
            "Port to serve the onboarding app from."
        )
        self.add_option(
            "anticache", bool, False,
            """
            Strip out request headers that might cause the server to return
            304-not-modified.
            """
        )
        self.add_option(
            "anticomp", bool, False,
            "Try to convince servers to send us un-compressed data."
        )
        self.add_option(
            "client_replay", Sequence[str], [],
            "Replay client requests from a saved file."
        )
        self.add_option(
            "replay_kill_extra", bool, False,
            "Kill extra requests during replay."
        )
        self.add_option(
            "keepserving", bool, True,
            "Continue serving after client playback or file read."
        )
        self.add_option(
            "server", bool, True,
            "Start a proxy server."
        )
        self.add_option(
            "server_replay_nopop", bool, False,
            """
            Disable response pop from response flow. This makes it possible to
            replay same response multiple times.
            """
        )
        self.add_option(
            "refresh_server_playback", bool, True,
            """
            Refresh server replay responses by adjusting date, expires and
            last-modified headers, as well as adjusting cookie expiration.
            """
        )
        self.add_option(
            "rfile", Optional[str], None,
            "Read flows from file."
        )
        self.add_option(
            "scripts", Sequence[str], [],
            """
            Execute a script.
            """
        )
        self.add_option(
            "showhost", bool, False,
            "Use the Host header to construct URLs for display."
        )
        self.add_option(
            "replacements", Sequence[str], [],
            """
            Replacement patterns of the form "/pattern/regex/replacement", where
            the separator can be any character.
            """
        )
        self.add_option(
            "replacement_files", Sequence[str], [],
            """
            Replacement pattern, where the replacement clause is a path to a
            file.
            """
        )
        self.add_option(
            "server_replay_use_headers", Sequence[str], [],
            "Request headers to be considered during replay."
        )
        self.add_option(
            "setheaders", Sequence[str], [],
            """
            Header set pattern of the form "/pattern/header/value", where the
            separator can be any character.
            """
        )
        self.add_option(
            "server_replay", Sequence[str], [],
            "Replay server responses from a saved file."
        )
        self.add_option(
            "stickycookie", Optional[str], None,
            "Set sticky cookie filter. Matched against requests."
        )
        self.add_option(
            "stickyauth", Optional[str], None,
            "Set sticky auth filter. Matched against requests."
        )
        self.add_option(
            "stream_large_bodies", Optional[str], None,
            """
            Stream data to the client if response body exceeds the given
            threshold. If streamed, the body will not be stored in any way.
            Understands k/m/g suffixes, i.e. 3m for 3 megabytes.
            """
        )
        self.add_option(
            "verbosity", int, 2,
            "Log verbosity."
        )
        self.add_option(
            "default_contentview", str, "auto",
            "The default content view mode."
        )
        self.add_option(
            "streamfile", Optional[str], None,
            "Write flows to file. Prefix path with + to append."
        )
        self.add_option(
            "server_replay_ignore_content", bool, False,
            "Ignore request's content while searching for a saved flow to replay."
        )
        self.add_option(
            "server_replay_ignore_params", Sequence[str], [],
            """
            Request's parameters to be ignored while searching for a saved flow
            to replay. Can be passed multiple times.
            """
        )
        self.add_option(
            "server_replay_ignore_payload_params", Sequence[str], [],
            """
            Request's payload parameters (application/x-www-form-urlencoded or
            multipart/form-data) to be ignored while searching for a saved flow
            to replay.
            """
        )
        self.add_option(
            "server_replay_ignore_host", bool, False,
            """
            Ignore request's destination host while searching for a saved flow
            to replay.
            """
        )

        # Proxy options
        self.add_option(
            "proxyauth", Optional[str], None,
            """
            Require authentication before proxying requests. If the value is
            "any", we prompt for authentication, but permit any values. If it
            starts with an "@", it is treated as a path to an Apache htpasswd
            file. If its is of the form "username:password", it is treated as a
            single-user credential.
            """
        )
        self.add_option(
            "add_upstream_certs_to_client_chain", bool, False,
            """
            Add all certificates of the upstream server to the certificate chain
            that will be served to the proxy client, as extras.
            """
        )
        self.add_option(
            "body_size_limit", Optional[str], None,
            """
            Byte size limit of HTTP request and response bodies. Understands
            k/m/g suffixes, i.e. 3m for 3 megabytes.
            """
        )
        self.add_option(
            "cadir", str, CA_DIR,
            "Location of the default mitmproxy CA files."
        )
        self.add_option(
            "certs", Sequence[str], [],
            """
            SSL certificates. SPEC is of the form "[domain=]path". The
            domain may include a wildcard, and is equal to "*" if not specified.
            The file at path is a certificate in PEM format. If a private key is
            included in the PEM, it is used, else the default key in the conf
            dir is used. The PEM file should contain the full certificate chain,
            with the leaf certificate as the first entry. Can be passed multiple
            times.
            """
        )
        self.add_option(
            "ciphers_client", str, DEFAULT_CLIENT_CIPHERS,
            "Set supported ciphers for client connections using OpenSSL syntax."
        )
        self.add_option(
            "ciphers_server", Optional[str], None,
            "Set supported ciphers for server connections using OpenSSL syntax."
        )
        self.add_option(
            "client_certs", Optional[str], None,
            "Client certificate file or directory."
        )
        self.add_option(
            "ignore_hosts", Sequence[str], [],
            """
            Ignore host and forward all traffic without processing it. In
            transparent mode, it is recommended to use an IP address (range),
            not the hostname. In regular mode, only SSL traffic is ignored and
            the hostname should be used. The supplied value is interpreted as a
            regular expression and matched on the ip or the hostname.
            """
        )
        self.add_option(
            "listen_host", str, "",
            "Address to bind proxy to."
        )
        self.add_option(
            "listen_port", int, LISTEN_PORT,
            "Proxy service port."
        )
        self.add_option(
            "upstream_bind_address", str, "",
            "Address to bind upstream requests to."
        )
        self.add_option(
            "mode", str, "regular",
            """
            Mode can be "regular", "transparent", "socks5", "reverse:SPEC",
            or "upstream:SPEC". For reverse and upstream proxy modes, SPEC
            is proxy specification in the form of "http[s]://host[:port]".
            """
        )
        self.add_option(
            "upstream_cert", bool, True,
            "Connect to upstream server to look up certificate details."
        )
        self.add_option(
            "keep_host_header", bool, False,
            """
            Reverse Proxy: Keep the original host header instead of rewriting it
            to the reverse proxy target.
            """
        )

        self.add_option(
            "http2", bool, True,
            "Enable/disable HTTP/2 support. "
            "HTTP/2 support is enabled by default.",
        )
        self.add_option(
            "http2_priority", bool, False,
            """
            PRIORITY forwarding for HTTP/2 connections. PRIORITY forwarding is
            disabled by default, because some webservers fail to implement the
            RFC properly.
            """
        )
        self.add_option(
            "websocket", bool, True,
            "Enable/disable WebSocket support. "
            "WebSocket support is enabled by default.",
        )
        self.add_option(
            "rawtcp", bool, False,
            "Enable/disable experimental raw TCP support. "
            "Disabled by default. "
        )

        self.add_option(
            "spoof_source_address", bool, False,
            """
            Use the client's IP for server-side connections. Combine with
            --upstream-bind-address to spoof a fixed source address.
            """
        )
        self.add_option(
            "upstream_auth", Optional[str], None,
            """
            Add HTTP Basic authentcation to upstream proxy and reverse proxy
            requests. Format: username:password.
            """
        )
        self.add_option(
            "ssl_version_client", str, "secure",
            """
            Set supported SSL/TLS versions for client connections. SSLv2, SSLv3
            and 'all' are INSECURE. Defaults to secure, which is TLS1.0+.
            """,
            choices=tcp.sslversion_choices.keys(),
        )
        self.add_option(
            "ssl_version_server", str, "secure",
            """
            Set supported SSL/TLS versions for server connections. SSLv2, SSLv3
            and 'all' are INSECURE. Defaults to secure, which is TLS1.0+.
            """,
            choices=tcp.sslversion_choices.keys(),
        )
        self.add_option(
            "ssl_insecure", bool, False,
            "Do not verify upstream server SSL/TLS certificates."
        )
        self.add_option(
            "ssl_verify_upstream_trusted_cadir", Optional[str], None,
            """
            Path to a directory of trusted CA certificates for upstream server
            verification prepared using the c_rehash tool.
            """
        )
        self.add_option(
            "ssl_verify_upstream_trusted_ca", Optional[str], None,
            "Path to a PEM formatted trusted CA certificate."
        )
        self.add_option(
            "tcp_hosts", Sequence[str], [],
            """
            Generic TCP SSL proxy mode for all hosts that match the pattern.
            Similar to --ignore, but SSL connections are intercepted. The
            communication contents are printed to the log in verbose mode.
            """
        )

        self.add_option(
            "intercept", Optional[str], None,
            "Intercept filter expression."
        )

        # Console options
        self.add_option(
            "console_eventlog", bool, False,
            "Show event log."
        )
        self.add_option(
            "console_focus_follow", bool, False,
            "Focus follows new flows."
        )
        self.add_option(
            "console_palette", str, "dark",
            "Color palette.",
            choices=sorted(console_palettes),
        )
        self.add_option(
            "console_palette_transparent", bool, False,
            "Set transparent background for palette."
        )
        self.add_option(
            "console_mouse", bool, True,
            "Console mouse interaction."
        )
        self.add_option(
            "console_order", Optional[str], None,
            "Flow sort order.",
            choices=view_orders,
        )
        self.add_option(
            "console_order_reversed", bool, False,
            "Reverse the sorting order."
        )

        self.add_option(
            "filter", Optional[str], None,
            "Filter view expression."
        )

        # Web options
        self.add_option(
            "web_open_browser", bool, True,
            "Start a browser."
        )
        self.add_option(
            "web_debug", bool, False,
            "Mitmweb debugging."
        )
        self.add_option(
            "web_port", int, 8081,
            "Mitmweb port."
        )
        self.add_option(
            "web_iface", str, "127.0.0.1",
            "Mitmweb interface."
        )

        # Dump options
        self.add_option(
            "filtstr", Optional[str], None,
            "The filter string for mitmdump."
        )
        self.add_option(
            "flow_detail", int, 1,
            "Flow detail display level."
        )

        self.update(**kwargs)
