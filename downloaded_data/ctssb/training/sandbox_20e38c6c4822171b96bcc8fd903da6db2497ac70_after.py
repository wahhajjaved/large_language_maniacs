from django.core.management.base import BaseCommand, CommandError
from ldap3 import Connection, Server, ANONYMOUS, SIMPLE, SYNC, ASYNC, ALL, NTLM
from apps.users.models import Employee, System
import uuid

def importUser(item, account):
  obj, created = Employee.objects.update_or_create(uuid=uuid.UUID(str(item.objectGUID)), defaults={'email':'tempemail@slcschools.org','url':'/tempemail'})
  obj.username = str(item.userPrincipalName).lower()
  obj.first_name = item.givenName
  obj.last_name = item.sn
  if item.mail:
    obj.email = str(item.mail).lower()
  else:
    obj.email = str(item.userPrincipalName).lower()
  obj.is_staff = True
  obj.deleted = False
  if created:
    obj.create_user = account
  obj.update_user = account
  obj.save()

class Command(BaseCommand):
  importuserssvc = System.objects.get(username='importuserssvc')
  server = Server('slcsd.net', use_ssl=True, get_info=ALL)
  conn = Connection(server, user="slcsd\jc024987", password="$i2F'MI\?C@UXK]!3Lm", authentication=NTLM)
  conn.bind()
  conn.search('OU=WEB,OU=SERVERS,DC=SLCSD,DC=NET', '(&(objectClass=user)(| (memberof:1.2.840.113556.1.4.1941:=CN=USR_SERVERS_WEB_ALL_ADULT_STAFF,OU=WEB,OU=SERVERS,DC=SLCSD,DC=NET)(memberof:1.2.840.113556.1.4.1941:=CN=USR_SLCSD_NONEMPLOYEE,DC=SLCSD,DC=NET)))', attributes=['DisplayName','userPrincipalName','givenName','sn','objectGUID','mail'])
  for item in conn.entries:
    importUser(item, importuserssvc)
  conn.search('OU=DO,DC=SLCSD,DC=NET', '(&(objectClass=user)(| (memberof:1.2.840.113556.1.4.1941:=CN=USR_SERVERS_WEB_ALL_ADULT_STAFF,OU=WEB,OU=SERVERS,DC=SLCSD,DC=NET)(memberof:1.2.840.113556.1.4.1941:=CN=USR_SLCSD_NONEMPLOYEE,DC=SLCSD,DC=NET)))', attributes=['DisplayName','userPrincipalName','givenName','sn','objectGUID','mail'])
  for item in conn.entries:
    importUser(item, importuserssvc)
  conn.search('OU=INFORMATION_SYSTEMS,DC=SLCSD,DC=NET', '(&(objectClass=user)(|(memberof:1.2.840.113556.1.4.1941:=CN=USR_SERVERS_WEB_ALL_ADULT_STAFF,OU=WEB,OU=SERVERS,DC=SLCSD,DC=NET)(memberof:1.2.840.113556.1.4.1941:=CN=USR_SLCSD_NONEMPLOYEE,DC=SLCSD,DC=NET)))', attributes=['DisplayName','userPrincipalName','givenName','sn','objectGUID','mail'])
  for item in conn.entries:
    importUser(item, importuserssvc)

