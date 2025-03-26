from django.contrib import admin
try:
    from django.contrib.contenttypes.admin import GenericTabularInline
except ImportError:  # Django < 1.9 pragma: no cover
    from django.contrib.contenttypes.generic import GenericTabularInline
from django.shortcuts import resolve_url
import reversion
from reversion.admin import VersionAdmin
from reversion.models import Version
from test_app.models import TestModel, TestModelParent, TestModelInline, TestModelGenericInline
from test_app.tests.base import TestBase, LoginTestBase


class AdminTestBase(LoginTestBase):

    def setUp(self):
        super(AdminTestBase, self).setUp()
        reversion.unregister(TestModel)
        reversion.unregister(TestModelParent)
        admin.site.register(TestModelParent, VersionAdmin)

    def tearDown(self):
        super(AdminTestBase, self).tearDown()
        admin.site.unregister(TestModelParent)


class AdminRegisterTest(AdminTestBase):

    def setAutoRegister(self):
        self.assertTrue(reversion.is_registered(TestModelParent))

    def setAutoRegisterFollowsParent(self):
        self.assertTrue(reversion.is_registered(TestModel))


class TestModelInlineAdmin(admin.TabularInline):

    model = TestModelInline


class TestModelGenericInlineAdmin(GenericTabularInline):

    model = TestModelGenericInline


class TestModelParentAdmin(VersionAdmin):

    inlines = (TestModelInlineAdmin, TestModelGenericInlineAdmin)


class AdminRegisterInlineTest(TestBase):

    def setUp(self):
        super(AdminRegisterInlineTest, self).setUp()
        reversion.unregister(TestModel)
        reversion.unregister(TestModelParent)
        admin.site.register(TestModelParent, TestModelParentAdmin)

    def tearDown(self):
        super(AdminRegisterInlineTest, self).tearDown()
        if reversion.is_registered(TestModelInline):
            reversion.unregister(TestModelInline)
        if reversion.is_registered(TestModelGenericInline):
            reversion.unregister(TestModelGenericInline)
        admin.site.unregister(TestModelParent)

    def testAutoRegisterInline(self):
        self.assertTrue(reversion.is_registered(TestModelInline))

    def testAutoRegisterGenericInline(self):
        self.assertTrue(reversion.is_registered(TestModelGenericInline))


class AdminAddViewTest(AdminTestBase):

    def testAddView(self):
        self.client.post(resolve_url("admin:test_app_testmodelparent_add"), {
            "name": "v1",
            "parent_name": "parent_v1",
        })
        obj = TestModelParent.objects.get()
        self.assertSingleRevision((obj, obj.testmodel_ptr), user=self.user, comment=None)


class AdminUpdateViewTest(AdminTestBase):

    def testUpdateView(self):
        obj = TestModelParent.objects.create()
        self.client.post(resolve_url("admin:test_app_testmodelparent_change", obj.pk), {
            "name": "v2",
            "parent_name": "parent v2",
        })
        self.assertSingleRevision((obj, obj.testmodel_ptr), user=self.user, comment=None)


class AdminChangelistView(AdminTestBase):

    def testChangelistView(self):
        obj = TestModelParent.objects.create()
        response = self.client.get(resolve_url("admin:test_app_testmodelparent_changelist"))
        self.assertContains(response, resolve_url("admin:test_app_testmodelparent_change", obj.pk))


class AdminRevisionViewTest(AdminTestBase):

    def setUp(self):
        super(AdminRevisionViewTest, self).setUp()
        with reversion.create_revision():
            self.obj = TestModelParent.objects.create()
        with reversion.create_revision():
            self.obj.name = "v2"
            self.obj.parent_name = "parent v2"
            self.obj.save()

    def testRevisionView(self):
        response = self.client.get(resolve_url(
            "admin:test_app_testmodelparent_revision",
            self.obj.pk,
            Version.objects.get_for_object(self.obj)[1].pk,
        ))
        self.assertContains(response, 'value="v1"')
        self.assertContains(response, 'value="parent v1"')

    def testRevisionViewOldRevision(self):
        response = self.client.get(resolve_url(
            "admin:test_app_testmodelparent_revision",
            self.obj.pk,
            Version.objects.get_for_object(self.obj)[0].pk,
        ))
        self.assertContains(response, 'value="v2"')
        self.assertContains(response, 'value="parent v2"')

    def testRevisionViewRevertError(self):
        Version.objects.get_for_object(self.obj).update(format="boom")
        response = self.client.get(resolve_url(
            "admin:test_app_testmodelparent_revision",
            self.obj.pk,
            Version.objects.get_for_object(self.obj)[1].pk,
        ))
        self.assertEqual(
            response["Location"].replace("http://testserver", ""),
            resolve_url("admin:test_app_testmodelparent_changelist"),
        )

    def testRevisionViewRevert(self):
        self.client.post(resolve_url(
            "admin:test_app_testmodelparent_revision",
            self.obj.pk,
            Version.objects.get_for_object(self.obj)[1].pk,
        ), {
            "name": "v1",
            "parent_name": "parent v1",
        })
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.name, "v1")
        self.assertEqual(self.obj.parent_name, "parent v1")


class AdminRecoverViewTest(AdminTestBase):

    def setUp(self):
        super(AdminRecoverViewTest, self).setUp()
        with reversion.create_revision():
            obj = TestModelParent.objects.create()
        obj.delete()

    def testRecoverView(self):
        response = self.client.get(resolve_url(
            "admin:test_app_testmodelparent_recover",
            Version.objects.get_for_model(TestModelParent).get().pk,
        ))
        self.assertContains(response, 'value="v1"')
        self.assertContains(response, 'value="parent v1"')

    def testRecoverViewRecover(self):
        self.client.post(resolve_url(
            "admin:test_app_testmodelparent_recover",
            Version.objects.get_for_model(TestModelParent).get().pk,
        ), {
            "name": "v1",
            "parent_name": "parent v1",
        })
        obj = TestModelParent.objects.get()
        self.assertEqual(obj.name, "v1")
        self.assertEqual(obj.parent_name, "parent v1")


class AdminRecoverlistViewTest(AdminTestBase):

    def testRecoverlistView(self):
        with reversion.create_revision():
            obj = TestModelParent.objects.create()
        obj.delete()
        response = self.client.get(resolve_url("admin:test_app_testmodelparent_recoverlist"))
        self.assertContains(response, resolve_url(
            "admin:test_app_testmodelparent_recover",
            Version.objects.get_for_model(TestModelParent).get().pk,
        ))


class AdminHistoryViewTest(AdminTestBase):

    def testHistorylistView(self):
        with reversion.create_revision():
            obj = TestModelParent.objects.create()
        response = self.client.get(resolve_url("admin:test_app_testmodelparent_history", obj.pk))
        self.assertContains(response, resolve_url(
            "admin:test_app_testmodelparent_revision",
            obj.pk,
            Version.objects.get_for_model(TestModelParent).get().pk,
        ))
