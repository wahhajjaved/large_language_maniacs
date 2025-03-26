import json
from argparse import Action

from ldap3 import Connection
from ldap3.core.exceptions import LDAPException

ldap = None


def devpiserver_auth_user(userdict, username, password):
    if ldap is None:
        return dict(status="unknown")
    if len(password) == 0:
        return dict(status="reject")
    conn = Connection(ldap['server'], auto_bind=True)
    conn.search(ldap['base'], ldap['search'].format(username=username))
    if len(conn.entries) == 0:
        return dict(status='unknown')
    dn = conn.entries[0].entry_dn
    try:
        Connection(ldap['server'], auto_bind=True, user=dn, password=password)
    except LDAPException:
        return dict(status="reject")
    return dict(status="ok")


class LDAPConfigAction(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        global ldap
        print(values)
        with open(values, 'r') as f:
            ldap = json.load(f)
        setattr(namespace, self.dest, ldap)


def devpiserver_add_parser_options(parser):
    ldap = parser.addgroup("LDAP authentication")
    ldap.addoption(
        "--ldap-config", action=LDAPConfigAction,
        help="LDAP configuration file")
