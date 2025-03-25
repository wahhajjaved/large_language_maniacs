import os
import requests

from django.conf import settings
from httmock import urlmatch, HTTMock

from xml.dom import minidom, Node

from onadata.apps.api.tests.viewsets.test_abstract_viewset import \
    TestAbstractViewSet
from onadata.apps.api.viewsets.xform_viewset import XFormViewSet
from onadata.apps.logger.models import XForm
from onadata.libs.permissions import OwnerRole, ManagerRole


@urlmatch(netloc=r'(.*\.)?enketo\.formhub\.org$')
def enketo_mock(url, request):
    response = requests.Response()
    response.status_code = 201
    response._content = \
        '{\n  "url": "https:\\/\\/dmfrm.enketo.org\\/webform",\n'\
        '  "code": "200"\n}'
    return response


class TestXFormViewSet(TestAbstractViewSet):
    def setUp(self):
        super(self.__class__, self).setUp()
        self.view = XFormViewSet.as_view({
            'get': 'list',
        })

    def test_form_list(self):
        self._publish_xls_form_to_project()
        request = self.factory.get('/', **self.extra)
        response = self.view(request)
        self.assertEqual(response.status_code, 200)

    def test_form_list_anon(self):
        self._publish_xls_form_to_project()
        request = self.factory.get('/')
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_public_form_owner_list(self):
        self.view = XFormViewSet.as_view({
            'get': 'retrieve'
        })
        self._publish_xls_form_to_project()
        request = self.factory.get('/', **self.extra)
        response = self.view(request, owner=self.user.username, pk='public')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

        # public shared form
        self.xform.shared = True
        self.xform.save()
        response = self.view(request, owner=self.user.username, pk='public')
        self.assertEqual(response.status_code, 200)
        self.form_data['public'] = True
        del self.form_data['date_modified']
        del response.data[0]['date_modified']
        self.assertEqual(response.data, [self.form_data])

        # public shared form data
        self.xform.shared_data = True
        self.xform.shared = False
        self.xform.save()
        response = self.view(request, owner=self.user.username, pk='public')
        self.assertEqual(response.status_code, 200)
        self.form_data['public_data'] = True
        self.form_data['public'] = False
        del response.data[0]['date_modified']
        self.assertEqual(response.data, [self.form_data])

    def test_public_form_list(self):
        self._publish_xls_form_to_project()
        request = self.factory.get('/', **self.extra)
        response = self.view(request, owner='public')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

        # public shared form
        self.xform.shared = True
        self.xform.save()
        response = self.view(request, owner='public')
        self.assertEqual(response.status_code, 200)
        self.form_data['public'] = True
        del self.form_data['date_modified']
        del response.data[0]['date_modified']
        self.assertEqual(response.data, [self.form_data])

        # public shared form data
        self.xform.shared_data = True
        self.xform.shared = False
        self.xform.save()
        response = self.view(request, owner='public')
        self.assertEqual(response.status_code, 200)
        self.form_data['public_data'] = True
        self.form_data['public'] = False
        del response.data[0]['date_modified']
        self.assertEqual(response.data, [self.form_data])

    def test_form_list_other_user_access(self):
        """Test that a different user has no access to bob's form"""
        self._publish_xls_form_to_project()
        request = self.factory.get('/', **self.extra)
        response = self.view(request, owner=self.user.username)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [self.form_data])

        # test with different user
        previous_user = self.user
        alice_data = {'username': 'alice', 'email': 'alice@localhost.com'}
        self._login_user_and_profile(extra_post_data=alice_data)
        self.assertEqual(self.user.username, 'alice')
        self.assertNotEqual(previous_user,  self.user)
        request = self.factory.get('/', **self.extra)
        response = self.view(request, owner=previous_user.username)
        self.assertEqual(response.status_code, 200)
        # should be empty
        self.assertEqual(response.data, [])

        # make form public
        xform = previous_user.xforms.get(id_string=self.form_data['id_string'])
        xform.shared = True
        xform.save()
        xform = previous_user.xforms.get(id_string=self.form_data['id_string'])
        self.form_data['public'] = True
        self.form_data['date_modified'] = xform.date_modified
        response = self.view(request, owner=previous_user.username)
        self.assertEqual(response.status_code, 200)

        # other user has access to public form
        self.assertEqual(response.data, [self.form_data])

    def test_form_get(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'retrieve'
        })
        formid = self.xform.pk
        request = self.factory.get('/', **self.extra)
        response = view(request, owner='bob', pk=formid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.form_data)

    def test_form_get_by_id_string(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'retrieve'
        })
        request = self.factory.get('/', **self.extra)
        # using id_string
        response = view(request, owner='bob', pk=self.xform.id_string)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.form_data)

    def test_form_get_multiple_users_same_id_string(self):
        self._publish_xls_form_to_project()
        self._login_user_and_profile(extra_post_data={'username': 'demo',
                                                      'email': 'demo@ona.io'})
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'retrieve'
        })
        request = self.factory.get('/', **self.extra)
        # using id_string
        response = view(request,
                        owner=self.user.username,
                        pk=self.xform.id_string)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.form_data)

    def test_form_format(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'form'
        })
        formid = self.xform.pk
        data = {
            "name": "transportation",
            "title": "transportation_2011_07_25",
            "default_language": "default",
            "id_string": "transportation_2011_07_25",
            "type": "survey",
        }
        request = self.factory.get('/', **self.extra)
        response = view(request, owner='bob', pk=formid, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertDictContainsSubset(data, response.data)
        response = view(request, owner='bob', pk=formid, format='xml')
        self.assertEqual(response.status_code, 200)
        response_doc = minidom.parseString(response.data)

        xml_path = os.path.join(
            settings.PROJECT_ROOT, "apps", "main", "tests", "fixtures",
            "transportation", "transportation.xml")
        with open(xml_path) as xml_file:
            expected_doc = minidom.parse(xml_file)

        model_node = [
            n for n in
            response_doc.getElementsByTagName("h:head")[0].childNodes
            if n.nodeType == Node.ELEMENT_NODE and
            n.tagName == "model"][0]

        # check for UUID and remove
        uuid_nodes = [
            node for node in model_node.childNodes
            if node.nodeType == Node.ELEMENT_NODE
            and node.getAttribute("nodeset") == "/transportation/formhub/uuid"]
        self.assertEqual(len(uuid_nodes), 1)
        uuid_node = uuid_nodes[0]
        uuid_node.setAttribute("calculate", "''")

        # check content without UUID
        self.assertEqual(response_doc.toxml(), expected_doc.toxml())

    def test_form_tags(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'labels',
            'post': 'labels',
            'delete': 'labels'
        })
        formid = self.xform.pk
        # no tags
        request = self.factory.get('/', **self.extra)
        response = view(request, owner='bob', pk=formid)
        self.assertEqual(response.data, [])
        # add tag "hello"
        request = self.factory.post('/', data={"tags": "hello"}, **self.extra)
        response = view(request, owner='bob', pk=formid)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, [u'hello'])
        # remove tag "hello"
        request = self.factory.delete('/', data={"tags": "hello"},
                                      **self.extra)
        response = view(request, owner='bob', pk=formid, label='hello')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_enketo_url(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'get': 'enketo'
        })
        formid = self.xform.pk
        # no tags
        request = self.factory.get('/', **self.extra)
        with HTTMock(enketo_mock):
            response = view(request, owner='bob', pk=formid)
            data = {"enketo_url": "https://dmfrm.enketo.org/webform"}
            self.assertEqual(response.data, data)

    def test_publish_xlsform(self):
        view = XFormViewSet.as_view({
            'post': 'create'
        })
        data = {
            'owner': 'http://testserver/api/v1/users/bob',
            'public': False,
            'public_data': False,
            'description': u'transportation_2011_07_25',
            'downloadable': True,
            'allows_sms': False,
            'encrypted': False,
            'sms_id_string': u'transportation_2011_07_25',
            'id_string': u'transportation_2011_07_25',
            'title': u'transportation_2011_07_25',
            'bamboo_dataset': u''
        }
        path = os.path.join(
            settings.PROJECT_ROOT, "apps", "main", "tests", "fixtures",
            "transportation", "transportation.xls")
        with open(path) as xls_file:
            post_data = {'xls_file': xls_file}
            request = self.factory.post('/', data=post_data, **self.extra)
            response = view(request)
            self.assertEqual(response.status_code, 201)
            xform = self.user.xforms.all()[0]
            data.update({
                'url':
                'http://testserver/api/v1/forms/bob/%s' % xform.pk
            })
            self.assertDictContainsSubset(data, response.data)
            self.assertTrue(OwnerRole.has_role(self.user, xform))

    def test_partial_update(self):
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'patch': 'partial_update'
        })
        description = 'DESCRIPTION'
        data = {'public': True, 'description': description}

        self.assertFalse(self.xform.shared)

        request = self.factory.patch('/', data=data, **self.extra)
        response = view(request, owner='bob', pk=self.xform.id)

        self.xform.reload()
        self.assertTrue(self.xform.shared)
        self.assertEqual(self.xform.description, description)
        self.assertEqual(response.data['public'], True)
        self.assertEqual(response.data['description'], description)

    def test_set_form_private(self):
        key = 'shared'
        self._publish_xls_form_to_project()
        self.xform.__setattr__(key, True)
        self.xform.save()
        view = XFormViewSet.as_view({
            'patch': 'partial_update'
        })
        data = {'public': False}

        self.assertTrue(self.xform.__getattribute__(key))

        request = self.factory.patch('/', data=data, **self.extra)
        response = view(request, owner='bob', pk=self.xform.id)

        self.xform.reload()
        self.assertFalse(self.xform.__getattribute__(key))
        self.assertFalse(response.data['public'])

    def test_set_form_bad_value(self):
        key = 'shared'
        self._publish_xls_form_to_project()
        view = XFormViewSet.as_view({
            'patch': 'partial_update'
        })
        data = {'public': 'String'}

        request = self.factory.patch('/', data=data, **self.extra)
        response = view(request, owner='bob', pk=self.xform.id)

        self.xform.reload()
        self.assertFalse(self.xform.__getattribute__(key))
        self.assertEqual(response.data,
                         {'shared':
                          [u"'String' value must be either True or False."]})

    def test_set_form_bad_key(self):
        self._publish_xls_form_to_project()
        self.xform.save()
        view = XFormViewSet.as_view({
            'patch': 'partial_update'
        })
        data = {'nonExistentField': False}

        request = self.factory.patch('/', data=data, **self.extra)
        response = view(request, owner='bob', pk=self.xform.id)

        self.xform.reload()
        self.assertFalse(self.xform.shared)
        self.assertFalse(response.data['public'])

    def test_form_delete(self):
        self._publish_xls_form_to_project()
        self.xform.save()
        view = XFormViewSet.as_view({
            'delete': 'destroy'
        })
        formid = self.xform.pk
        request = self.factory.delete('/', **self.extra)
        response = view(request, owner='bob', pk=formid)
        self.assertEqual(response.data, None)
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(XForm.DoesNotExist):
            self.xform.reload()

    def test_form_share_endpoint(self):
        self._publish_xls_form_to_project()
        alice_data = {'username': 'alice', 'email': 'alice@localhost.com'}
        alice_profile = self._create_user_profile(alice_data)
        self.assertFalse(ManagerRole.has_role(alice_profile.user, self.xform))

        view = XFormViewSet.as_view({
            'post': 'share'
        })
        formid = self.xform.pk
        data = {'username': 'alice', 'role': 'manager'}
        request = self.factory.post('/', data=data, **self.extra)
        response = view(request, owner='bob', pk=formid)

        self.assertTrue(response.status_code, 204)
        self.assertTrue(ManagerRole.has_role(alice_profile.user, self.xform))
