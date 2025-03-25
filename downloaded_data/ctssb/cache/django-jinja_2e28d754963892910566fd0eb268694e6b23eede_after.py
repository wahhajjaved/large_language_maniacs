# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

import datetime
import sys
import unittest

import django
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import NoReverseMatch
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.shortcuts import render
from django.template import RequestContext
from django.template.loader import get_template
from django.test import TestCase
from django.test import override_settings
from django.test import signals
from django.test.client import RequestFactory
from django_jinja.base import Template
from django_jinja.base import dict_from_context
from django_jinja.base import get_match_extension
from django_jinja.base import match_template
from django_jinja.views.generic.base import Jinja2TemplateResponseMixin

from .forms import TestForm
from .models import TestModel


class RenderTemplatesTests(TestCase):
    def setUp(self):
        if django.VERSION[:2] >= (1, 8):
            from django.template import engines
            env = engines["jinja2"]
        else:
            from django_jinja.base import env

        self.env = env
        self.factory = RequestFactory()

    def tearDown(self):
        pass

    def test_template_filters(self):
        filters_data = [
            ("{{ 'test-static.css'|static }}", {}, '/static/test-static.css'),
            ("{{ 'test-1'|reverseurl }}", {}, '/test1/'),
            ("{{ 'test-1'|reverseurl(data=2) }}", {}, '/test1/2/'),
            ("{{ num|floatformat }}", {'num': 34.23234}, '34.2'),
            ("{{ num|floatformat(3) }}", {'num': 34.23234}, '34.232'),
            ("{{ 'hola'|capfirst }}", {}, "Hola"),
            ("{{ 'hola mundo'|truncatechars(5) }}", {}, "ho..."),
            ("{{ 'hola mundo'|truncatewords(1) }}", {}, "hola ..."),
            ("{{ 'hola mundo'|truncatewords_html(1) }}", {}, "hola ..."),
            ("{{ 'hola mundo'|wordwrap(1) }}", {}, "hola\nmundo"),
            ("{{ 'hola mundo'|title }}", {}, "Hola Mundo"),
            ("{{ 'hola mundo'|slugify }}", {}, "hola-mundo"),
            ("{{ 'hello'|ljust(10) }}", {}, "hello     "),
            ("{{ 'hello'|rjust(10) }}", {}, "     hello"),
            ("{{ 'hello\nworld'|linebreaksbr }}", {}, "hello<br />world"),
            ("{{ '<div>hello</div>'|removetags('div') }}", {}, "hello"),
            ("{{ '<div>hello</div>'|striptags }}", {}, "hello"),
            ("{{ list|join(',') }}", {'list':['a','b']}, 'a,b'),
            ("{{ 3|add(2) }}", {}, "5"),
            ("{{ now|date('n Y') }}", {"now": datetime.datetime(2012, 12, 20)}, "12 2012"),
            ("{{ url('test-1') }}", {}, '/test1/'),
            ("{{ foo }}", {}, "bar"),
        ]

        print()
        for template_str, kwargs, result in filters_data:
            print("- Testing: ", template_str, "with:", kwargs)
            template = self.env.from_string(template_str)
            _result = template.render(kwargs)
            self.assertEqual(_result, result)

    def test_string_interpolation(self):
        template = self.env.from_string("{{ 'Hello %s!' % name }}")
        self.assertEqual(template.render({"name": "foo"}), "Hello foo!")

        template = self.env.from_string("{{ _('Hello %s!').format(name) }}")
        self.assertEqual(template.render({"name": "foo"}), "Hello foo!")

    def test_urlresolve_exceptions(self):
        template = self.env.from_string("{{ url('adads') }}")
        template.render({})

    def test_custom_addons_01(self):
        template = self.env.from_string("{{ 'Hello'|replace('H','M') }}")
        result = template.render({})

        self.assertEqual(result, "Mello")

    def test_custom_addons_02(self):
        template = self.env.from_string("{% if m is one %}Foo{% endif %}")
        result = template.render({'m': 1})

        self.assertEqual(result, "Foo")

    def test_custom_addons_03(self):
        template = self.env.from_string("{{ myecho('foo') }}")
        result = template.render({})

        self.assertEqual(result, "foo")

    def test_render_with(self):
        template = self.env.from_string("{{ myrenderwith() }}")
        result = template.render({})
        self.assertEqual(result, "<strong>Foo</strong>")

    def test_autoscape_with_form(self):
        form = TestForm()
        template = self.env.from_string("{{ form.as_p() }}")
        result = template.render({"form": form})

        self.assertIn('maxlength="2"', result)
        self.assertIn("/>", result)

    def test_autoscape_with_form_field(self):
        form = TestForm()
        template = self.env.from_string("{{ form.name }}")
        result = template.render({"form": form})

        self.assertIn('maxlength="2"', result)
        self.assertIn("/>", result)

    def test_autoscape_with_form_errors(self):
        form = TestForm({"name": "foo"})
        self.assertFalse(form.is_valid())

        template = self.env.from_string("{{ form.name.errors }}")
        result = template.render({"form": form})

        self.assertEqual(result,
                         ("""<ul class="errorlist"><li>Ensure this value """
                          """has at most 2 characters (it has 3).</li></ul>"""))

        template = self.env.from_string("{{ form.errors }}")
        result = template.render({"form": form})

        self.assertEqual(result,
                         ("""<ul class="errorlist"><li>name<ul class="errorlist">"""
                          """<li>Ensure this value has at most 2 characters (it """
                          """has 3).</li></ul></li></ul>"""))

    def test_autoescape_01(self):
        template = self.env.from_string("{{ foo|safe }}")
        result = template.render({'foo': '<h1>Hellp</h1>'})
        self.assertEqual(result, "<h1>Hellp</h1>")

    def test_autoescape_02(self):
        template = self.env.from_string("{{ foo }}")
        result = template.render({'foo': '<h1>Hellp</h1>'})
        self.assertEqual(result, "&lt;h1&gt;Hellp&lt;/h1&gt;")

    def test_autoescape_03(self):
        template = self.env.from_string("{{ foo|linebreaksbr }}")
        result = template.render({"foo": "<script>alert(1)</script>\nfoo"})
        self.assertEqual(result, "&lt;script&gt;alert(1)&lt;/script&gt;<br />foo")

    def test_debug_var_when_render_shortcut_is_used(self):
        prev_debug_value = settings.DEBUG
        settings.DEBUG = True

        request = self.factory.get("/")
        response = render(request, "test-debug-var.jinja")
        self.assertEqual(response.content, b"foobar")

        settings.DEBUG = prev_debug_value

    def test_csrf_01(self):
        template_content = "{% csrf_token %}"

        request = self.factory.get('/customer/details')
        if sys.version_info[0] < 3:
            request.META["CSRF_COOKIE"] = b'1234123123'
        else:
            request.META["CSRF_COOKIE"] = '1234123123'

        if django.VERSION[:2] >= (1, 8):
            template = self.env.from_string(template_content)
            result = template.render({}, request)

        else:
            context = dict_from_context(RequestContext(request))
            template = self.env.from_string(template_content)
            result = template.render(context)

        self.assertEqual(result, "<input type='hidden' name='csrfmiddlewaretoken' value='1234123123' />")

    def test_cache_01(self):
        template_content = "{% cache 200 'fooo' %}fóäo bar{% endcache %}"

        request = self.factory.get('/customer/details')
        context = dict_from_context(RequestContext(request))

        template = self.env.from_string(template_content)
        result = template.render(context)

        self.assertEqual(result, "fóäo bar")

    def test_404_page(self):
        response = self.client.get(reverse("page-404"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"404")
        response = self.client.post(reverse("page-404"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"404")
        response = self.client.put(reverse("page-404"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"404")
        response = self.client.delete(reverse("page-404"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"404")

    def test_403_page(self):
        response = self.client.get(reverse("page-403"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, b"403")

    def test_500_page(self):
        response = self.client.get(reverse("page-500"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content, b"500")

    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_get_default(self):
        from django_jinja.backend import Jinja2
        Jinja2.get_default.cache_clear()
        self.assertEqual(Jinja2.get_default(), self.env)

    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_get_default_multiple(self):
        from django_jinja.backend import Jinja2

        setting = {
            "append": [
                {
                    "BACKEND": "django_jinja.backend.Jinja2",
                    "NAME": "jinja2dup",
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "match_extension": ".jinjadup",
                    }
                }
            ]
        }

        with self.modify_settings(TEMPLATES=setting):
            with self.assertRaisesRegexp(ImproperlyConfigured, r'Several Jinja2 backends'):
                Jinja2.get_default()

    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_get_default_none(self):
        from django.conf import global_settings
        from django_jinja.backend import Jinja2

        with self.settings(TEMPLATES=global_settings.TEMPLATES):
            with self.assertRaisesRegexp(ImproperlyConfigured, r'No Jinja2 backend is configured'):
                Jinja2.get_default()


    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_overwrite_default_app_dirname(self):
        setting = [
            {
                "BACKEND": "django_jinja.backend.Jinja2",
                "NAME": "jinja2",
                "APP_DIRS": True,
                "OPTIONS": {
                    "match_extension": None,
                    "match_regex": None,
                    "app_dirname": "jinja2",
                }
            }
        ]

        with override_settings(TEMPLATES=setting):
            template = get_template("hola_mundo.html")
            data = template.render({"name": "jinja2"})
            self.assertEqual(data, "hola mundo de jinja2")



class DjangoPipelineTestTest(TestCase):
    def setUp(self):
        from django_jinja.base import env

        if django.VERSION[:2] >= (1, 8):
            from django.template import engines
            env = engines["jinja2"]

        self.env = env

    def test_pipeline_js_safe(self):
        template = self.env.from_string("{{ compressed_js('test') }}")
        result = template.render({})

        self.assertTrue(result.startswith("<script"))
        self.assertIn("text/javascript", result)
        self.assertIn("/static/script.2.js", result)

    def test_pipeline_css_safe_01(self):
        template = self.env.from_string("{{ compressed_css('test') }}")
        result = template.render({})
        self.assertIn("media=\"all\"", result)
        self.assertIn("stylesheet", result)
        self.assertIn("<link", result)
        self.assertIn("/static/style.2.css", result)

    def test_pipeline_css_safe_02(self):
        template = self.env.from_string("{{ compressed_css('test2') }}")
        result = template.render({})
        self.assertNotIn("media", result)
        self.assertIn("stylesheet", result)
        self.assertIn("<link", result)
        self.assertIn("/static/style.2.css", result)


class TemplateDebugSignalsTest(TestCase):
    def setUp(self):
        signals.template_rendered.connect(self._listener)

    def tearDown(self):
        signals.template_rendered.disconnect(self._listener)
        signals.template_rendered.disconnect(self._fail_listener)

    def _listener(self, sender=None, template=None, **kwargs):
        self.assertTrue(isinstance(sender, Template))
        self.assertTrue(isinstance(template, Template))

    def _fail_listener(self, *args, **kwargs):
        self.fail("I shouldn't be called")

    def test_render(self):
        with self.settings(TEMPLATE_DEBUG=True):
            tmpl = Template("OK")
            tmpl.render()

    def test_render_without_template_debug_setting(self):
        signals.template_rendered.connect(self._fail_listener)

        with self.settings(TEMPLATE_DEBUG=False):
            tmpl = Template("OK")
            tmpl.render()

    def test_stream(self):
        with self.settings(TEMPLATE_DEBUG=True):
            tmpl = Template("OK")
            tmpl.stream()

    def test_stream_without_template_debug_setting(self):
        signals.template_rendered.connect(self._fail_listener)

        with self.settings(TEMPLATE_DEBUG=False):
            tmpl = Template("OK")
            tmpl.stream()

    def test_template_used(self):
        """
        Test TestCase.assertTemplateUsed with django-jinja template
        """
        template_name = 'test.jinja'

        def view(request, template_name):
            tmpl = Template("{{ test }}")
            return HttpResponse(tmpl.stream({"test": "success"}))

        with self.settings(TEMPLATE_DEBUG=True):
            request = RequestFactory().get('/')
            response = view(request, template_name=template_name)
            self.assertEqual(response.content, b"success")


class BaseTests(TestCase):
    def test_match_template(self):
        self.assertTrue(
            match_template('admin/foo.html', regex=None, extension=None))
        self.assertFalse(
            match_template('admin/foo.html', regex=None, extension='.jinja'))
        self.assertTrue(
            match_template('admin/foo.html', regex=None, extension='.html'))
        self.assertTrue(
            match_template('admin/foo.html', regex=r'.*\.html', extension=None))
        self.assertFalse(
            match_template('admin/foo.html', regex=r"^(?!admin/.*)", extension=None))

    def test_get_match_extension(self):
        if django.VERSION[:2] < (1, 8):
            self.assertEquals(getattr(settings, 'DEFAULT_JINJA2_TEMPLATE_EXTENSION', '.jinja'), get_match_extension())
        else:
            from django_jinja.backend import Jinja2
            self.assertEquals(Jinja2.get_default().match_extension, get_match_extension())

    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_get_match_extension_using(self):
        setting = {
            "append": [
                {
                    "BACKEND": "django_jinja.backend.Jinja2",
                    "NAME": "jinja2dup",
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "match_extension": ".jinjadup",
                    }
                }
            ]
        }

        with self.modify_settings(TEMPLATES=setting):
            self.assertEquals(".jinja", get_match_extension(using='jinja2'))
            self.assertEquals(".jinjadup", get_match_extension(using="jinja2dup"))


class TemplateResponseTests(TestCase):
    class _BaseView(object):
        def get_template_names(self):
            return [
                'name1.html',
                'name2.html',
                'name3.html.jinja',
            ]

    def setUp(self):
        self.obj1 = TestModel.objects.create()

    def test_get_template_names(self):
        class _View(Jinja2TemplateResponseMixin, self._BaseView):
            pass

        view = _View()
        self.assertEquals(
            ['name1.html.jinja', 'name2.html.jinja', 'name3.html.jinja'],
            view.get_template_names()
        )

    def test_get_template_names_classext(self):
        class _View(Jinja2TemplateResponseMixin, self._BaseView):
            jinja2_template_extension = '.foo'

        view = _View()
        self.assertEquals(
            ['name1.html.foo', 'name2.html.foo', 'name3.html.jinja.foo'],
            view.get_template_names()
        )

    @unittest.skipIf(django.VERSION[:2] < (1, 8), "Not supported in Django < 1.8")
    def test_get_template_names_using(self):
        class _View(Jinja2TemplateResponseMixin, self._BaseView):
            template_engine = 'jinja2dup'

        setting = {
            "append": [
                {
                    "BACKEND": "django_jinja.backend.Jinja2",
                    "NAME": "jinja2dup",
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "match_extension": ".jinjadup",
                    }
                }
            ]
        }

        with self.modify_settings(TEMPLATES=setting):
            view = _View()
            self.assertEquals(
                ['name1.html.jinjadup', 'name2.html.jinjadup', 'name3.html.jinja.jinjadup'],
                view.get_template_names()
            )

class GenericViewTests(TestCase):
    def setUp(self):
        from django.utils import timezone

        self.obj1 = TestModel.objects.create(date=timezone.now())
        self.obj2 = TestModel.objects.create(date=timezone.now())

    def test_detailview(self):
        self.assertContains(
            self.client.get('/testmodel/{0}/detail'.format(self.obj1.pk)),
            'DetailView Test Template',
            status_code=200
        )

    def test_createview(self):
        self.assertContains(
            self.client.get('/testmodel/create'),
            'CreateView Test Template',
            status_code=200
        )

    def test_deleteview(self):
        self.assertContains(
            self.client.get('/testmodel/{0}/delete'.format(self.obj1.pk)),
            'DeleteView Test Template',
            status_code=200
        )

    def test_updateview(self):
        self.assertContains(
            self.client.get('/testmodel/{0}/update'.format(self.obj1.pk)),
            'UpdateView Test Template',
            status_code=200
        )

    def test_listview(self):
        self.assertContains(
            self.client.get('/testmodel/'),
            'ListView Test Template',
            status_code=200
        )

    def test_archiveindexview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/'),
            'ArchiveIndexView Test Template',
            status_code=200
        )

    def test_yeararchiveview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/{0:%Y}/'.format(self.obj1.date)),
            'YearArchiveView Test Template',
            status_code=200
        )

    def test_montharchiveview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/{0:%Y/%b}/'.format(self.obj1.date)),
            'MonthArchiveView Test Template',
            status_code=200
        )

    def test_weekarchiveview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/{0:%Y/week/%U}/'.format(self.obj1.date)),
            'WeekArchiveView Test Template',
            status_code=200
        )

    def test_dayarchiveview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/{0:%Y/%b/%d}/'.format(self.obj1.date)),
            'DayArchiveView Test Template',
            status_code=200
        )

    def test_todayarchiveview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/today/'),
            'TodayArchiveView Test Template',
            status_code=200
        )

    def test_datedetailview(self):
        self.assertContains(
            self.client.get('/testmodel/archive/{0:%Y/%b/%d}/{1}'.format(self.obj1.date, self.obj1.pk)),
            'DateDetailView Test Template',
            status_code=200
        )

    # ==== Special imports ====
    def test_import_archiveindexview(self):
        from django_jinja.views.generic import ArchiveIndexView

    def test_import_yeararchiveview(self):
        from django_jinja.views.generic import YearArchiveView

    def test_import_montharchiveview(self):
        from django_jinja.views.generic import MonthArchiveView

    def test_import_dayarchiveview(self):
        from django_jinja.views.generic import DayArchiveView

    def test_import_weekarchiveview(self):
        from django_jinja.views.generic import WeekArchiveView

    def test_import_todayarchiveview(self):
        from django_jinja.views.generic import TodayArchiveView

    def test_import_datedetailview(self):
        from django_jinja.views.generic import DateDetailView

    def test_import_detailview(self):
        from django_jinja.views.generic import DetailView

    def test_import_createview(self):
        from django_jinja.views.generic import CreateView

    def test_import_updateview(self):
        from django_jinja.views.generic import UpdateView

    def test_import_deleteview(self):
        from django_jinja.views.generic import DeleteView

    def test_import_listview(self):
        from django_jinja.views.generic import ListView
