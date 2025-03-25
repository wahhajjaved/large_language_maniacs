from operator import attrgetter
from datetime import datetime, timedelta

from mock import Mock

from pyramid import testing

from springboard.tests import SpringboardTestCase
from springboard.views.base import SpringboardViews

from springboard_iogt import filters


class TestFilters(SpringboardTestCase):
    maxDiff = None

    def setUp(self):
        self.workspace = self.mk_workspace()
        self.config = testing.setUp(settings={
            'unicore.repos_dir': self.working_dir,
            'unicore.content_repo_urls': self.workspace.working_dir,
        })

    def tearDown(self):
        testing.tearDown()

    def test_category_dict(self):
        categories = self.mk_categories(self.workspace, count=3)
        uuids = [category.uuid for category in categories]
        views = SpringboardViews(self.mk_request())
        cat_dict = filters.category_dict(views.all_categories, uuids + [None])
        self.assertEqual(set(cat_dict.keys()), set(uuids))
        self.assertEqual(sorted(cat_dict.values(), key=attrgetter('uuid')),
                         sorted(categories, key=attrgetter('uuid')))

    def test_recent_pages(self):
        workspaces = [self.workspace,
                      self.mk_workspace(name='test_recent_pages-2')]
        testing.setUp(settings={
            'unicore.repos_dir': self.working_dir,
            'unicore.content_repo_urls':
                '\n'.join(ws.working_dir for ws in workspaces)
        })
        views = SpringboardViews(self.mk_request())
        now = datetime.utcnow()

        def set_created_at(workspace, page, i):
            page = page.update({'created_at': (
                datetime.utcnow() - timedelta(hours=i)).isoformat()
            })
            workspace.save(page, 'Updated page')
            return page

        pages_ws1 = self.mk_pages(workspaces[0], count=3, featured=True)
        pages_ws2 = self.mk_pages(workspaces[1], count=3, featured=True)
        for i, h in enumerate((0, 1, 5)):
            pages_ws1[i] = set_created_at(workspaces[0], pages_ws1[i], i=h)
        for i, h in enumerate((2, 3, 4)):
            pages_ws2[i] = set_created_at(workspaces[1], pages_ws2[i], i=h)
        workspaces[0].refresh_index()
        workspaces[1].refresh_index()

        result = filters.recent_pages(views.all_pages, 'eng_GB', dt=now)
        result2 = filters.recent_pages(views.all_pages, 'eng_GB', dt=now)
        self.assertEqual(result, result2)
        self.assertEqual(
            sorted(result, key=attrgetter('uuid')),
            sorted(pages_ws1 + [pages_ws2[0]], key=attrgetter('uuid')))

        result2 = filters.recent_pages(views.all_pages, 'eng_GB',
                                       dt=now + timedelta(hours=1))
        self.assertNotEqual(result, result2)
        self.assertEqual(sorted(result, key=attrgetter('uuid')),
                         sorted(result2, key=attrgetter('uuid')))

    def test_content_section(self):
        [page] = self.mk_pages(self.workspace, count=1)
        section_obj = filters.content_section(page)
        self.assertIs(section_obj, None)

        page.es_meta = Mock(index='unicore-cms-content-ffl-za-qa')
        section_obj = filters.content_section(page)
        self.assertEqual(section_obj.slug, 'ffl')
        self.assertEqual(section_obj.title, 'Facts for Life')
