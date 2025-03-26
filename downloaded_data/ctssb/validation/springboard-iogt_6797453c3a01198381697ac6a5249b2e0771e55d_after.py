import re
from urllib import urlencode
from datetime import datetime, timedelta

from pyramid import testing

from springboard.tests import SpringboardTestCase

from springboard_iogt.views import (
    IoGTViews, PERSONAE, PERSONA_COOKIE_NAME, PERSONA_SKIP_COOKIE_VALUE)
from springboard_iogt.application import main


class TestIoGTViews(SpringboardTestCase):

    def setUp(self):
        self.workspace = self.mk_workspace()
        self.config = testing.setUp(settings={
            'unicore.repos_dir': self.working_dir,
            'unicore.content_repo_urls': self.workspace.working_dir,
        })

    def tearDown(self):
        testing.tearDown()

    def test_recent_content(self):
        category_p1, category_p3 = self.mk_categories(self.workspace, count=2)
        [page1] = self.mk_pages(
            self.workspace, count=1,
            primary_category=category_p1.uuid,
            created_at=datetime.utcnow().isoformat())
        [page2] = self.mk_pages(
            self.workspace, count=1,
            primary_category=None,
            created_at=(datetime.utcnow() - timedelta(hours=1)).isoformat())
        [page3] = self.mk_pages(
            self.workspace, count=1,
            primary_category=category_p3.uuid,
            created_at=(datetime.utcnow() - timedelta(hours=2)).isoformat())
        views = IoGTViews(self.mk_request())

        results = views.recent_content()(limit=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(
            {(category_p1.uuid, page1.uuid), (None, page2.uuid)},
            set((c.uuid if c else None, p.uuid) for c, p in results))

        results = views.recent_content()(limit=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(
            {(category_p1.uuid, page1.uuid), (None, page2.uuid),
             (category_p3.uuid, page3.uuid)},
            set((c.uuid if c else None, p.uuid) for c, p in results))

    def test_index_view(self):
        [category] = self.mk_categories(self.workspace, count=1)
        [page1, page2] = self.mk_pages(
            self.workspace, count=2,
            created_at=datetime.utcnow().isoformat())
        page1 = page1.update({'primary_category': category.uuid})
        self.workspace.save(page1, 'Update page category')
        self.workspace.refresh_index()
        app = self.mk_app(self.workspace, main=main)
        app.set_cookie(PERSONA_COOKIE_NAME, PERSONA_SKIP_COOKIE_VALUE)

        response = app.get('/')
        self.assertEqual(response.status_int, 200)
        html = response.html
        re_page_url = re.compile(r'/page/.{32}/')
        re_category_url = re.compile(r'/category/.{32}/')
        self.assertEqual(len(html.find_all('a', href=re_page_url)), 2)
        self.assertEqual(len(html.find_all('a', href=re_category_url)), 2)

    def test_persona_tween(self):
        app = self.mk_app(self.workspace, main=main)

        response = app.get('/')
        self.assertEqual(response.status_int, 302)
        self.assertTrue(
            response.location.startswith('http://localhost/persona/'))

        response = app.get('/persona/')
        self.assertEqual(response.status_int, 200)

        response = app.get('/matches/nothing/', expect_errors=True)
        self.assertEqual(response.status_int, 404)

        self.mk_pages(
            self.workspace, count=2,
            created_at=datetime.utcnow().isoformat())  # sets up mapping
        app.set_cookie(PERSONA_COOKIE_NAME, PERSONA_SKIP_COOKIE_VALUE)
        response = app.get('/')
        self.assertEqual(response.status_int, 200)

        for slug in ('child', 'skip'):
            app.reset()
            response = app.get('/persona/%s/' % slug)
            self.assertEqual(response.status_int, 302)
            self.assertEqual(response.location, 'http://localhost/')

    def test_select_persona(self):
        app = self.mk_app(self.workspace, main=main)
        next_url = 'http://localhost/page/1234/'
        querystring = urlencode({'next': next_url})

        response = app.get('/persona/worker/?%s' % querystring)
        self.assertEqual(response.status_int, 302)
        self.assertEqual(response.location, next_url)
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('%s=WORKER;' % PERSONA_COOKIE_NAME, cookie)

        response = app.get('/persona/not-a-persona/', expect_errors=True)
        self.assertEqual(response.status_int, 404)

    def test_skip_persona_selection(self):
        app = self.mk_app(self.workspace, main=main)
        next_url = 'http://localhost/page/1234/'
        querystring = urlencode({'next': next_url})

        response = app.get('/persona/skip/?%s' % querystring)
        self.assertEqual(response.status_int, 302)
        self.assertEqual(response.location, next_url)
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn(
            '%s=%s;' % (PERSONA_COOKIE_NAME, PERSONA_SKIP_COOKIE_VALUE),
            cookie)

    def test_personae(self):
        app = self.mk_app(self.workspace, main=main)
        url = 'http://localhost/page/1234/'
        querystring = urlencode({'next': url})

        html = app.get(url).follow().html
        persona_url_tags = html.find_all('a', href=re.compile(
            r'/persona/(%s)/' % '|'.join(p.lower() for p in PERSONAE)))
        skip_url_tags = html.find_all('a', href=re.compile(r'/persona/skip/'))
        self.assertEqual(len(persona_url_tags), 4)
        self.assertEqual(len(skip_url_tags), 1)
        self.assertTrue(all(querystring in tag['href']
                            for tag in persona_url_tags))
        self.assertTrue(querystring in skip_url_tags[0]['href'])
