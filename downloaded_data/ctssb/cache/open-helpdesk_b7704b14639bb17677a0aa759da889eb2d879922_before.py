# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

from django import VERSION as DJANGO_VERSION
from django.contrib.sites.models import Site
from django.test import TestCase
from lxml.html import fromstring

from helpdesk.defaults import (HELPDESK_REQUESTERS,
                               HELPDESK_TICKET_MAX_TIPOLOGIES)
from helpdesk.models import Ticket, Tipology, Category
from helpdesk.admin import MessageInline
from .helpers import AdminTestMixin
from .factories import (
    UserFactory, CategoryFactory, GroupFactory, SiteFactory, TicketFactory,
    TipologyFactory)


class RequesterMakeTicketTest(AdminTestMixin, TestCase):
    def setUp(self):
        self.requester = UserFactory(
            groups=[GroupFactory(name=HELPDESK_REQUESTERS[0],
                                 permissions=list(HELPDESK_REQUESTERS[1]))])
        self.client.login(username=self.requester.username, password='default')
        self.post_data = self.get_formset_post_data(
            data={'content': 'helpdesk_content', 'tipologies': None,
                  'priority': 1},
            formset='attachment_set')
        self.default_site = Site.objects.get(pk=1)

    def get_category(self, n_tipologies=None, site=None):
        if not n_tipologies:
            n_tipologies = HELPDESK_TICKET_MAX_TIPOLOGIES
        tipology_names = ['tip{}'.format(i) for i in range(0, n_tipologies)]
        category = CategoryFactory(tipologies=tipology_names)
        if site is None:
            site = self.default_site
        [t.sites.add(site) for t in category.tipologies.all()]
        self.post_data.update({'tipologies': category.tipology_pks})
        return category

    def test_adding_ticket_set_requester_field(self):
        """
        Test that adding new ticket, the field requester is setted with
        logged user.
        """
        self.get_category(2)
        self.client.post(self.get_url(Ticket, 'add'), data=self.post_data)
        self.assertEqual(Ticket.objects.count(), 1)
        ticket = Ticket.objects.latest()
        self.assertEqual(ticket.requester.pk, self.requester.pk)

    def test_changelist_view_is_filtered(self):
        """
        Test that the changelist is filtered by tickets with requester's field
        matching to logged user.
        """
        n = 2
        category = self.get_category(1)
        for user in [self.requester, UserFactory(
                groups=self.requester.groups.all())]:
            [TicketFactory(requester=user,
                           tipologies=category.tipologies.all())
             for i in range(0, n)]
        response = self.client.get(self.get_url(Ticket, 'changelist'))
        if DJANGO_VERSION < (1, 6):
            tickets_pks = response.context['cl'].result_list.values_list(
                'pk', flat=True)
        else:
            tickets_pks = response.context['cl'].queryset.values_list(
                'pk', flat=True)
        self.assertEqual(len(tickets_pks), n)
        self.assertEqual(
            set(tickets_pks),
            set(self.requester.requested_tickets.values_list('pk', flat=True)))

    def test_form_with_less_tipologies_fields_is_validate(self):
        self.get_category(HELPDESK_TICKET_MAX_TIPOLOGIES - 1)
        assert (len(self.post_data['tipologies'])
                < HELPDESK_TICKET_MAX_TIPOLOGIES)
        response = self.client.post(self.get_url(Ticket, 'add'),
                                    data=self.post_data)
        self.assertRedirects(response, self.get_url(Ticket, 'changelist'))

    def test_form_with_equals_tipologies_fields_is_validate(self):
        self.get_category(HELPDESK_TICKET_MAX_TIPOLOGIES)
        assert (len(self.post_data['tipologies'])
                == HELPDESK_TICKET_MAX_TIPOLOGIES)
        response = self.client.post(self.get_url(Ticket, 'add'),
                                    data=self.post_data)
        self.assertRedirects(response, self.get_url(Ticket, 'changelist'))

    def test_form_with_more_tipologies_fields_is_not_validate(self):
        self.get_category(HELPDESK_TICKET_MAX_TIPOLOGIES + 1)
        assert (len(self.post_data['tipologies'])
                > HELPDESK_TICKET_MAX_TIPOLOGIES)
        response = self.client.post(self.get_url(Ticket, 'add'),
                                    data=self.post_data)
        self.assertEqual(response.status_code, 200)
        self.assertAdminFormError(response, 'tipologies',
                                  'Too many tipologies selected. You can'
                                  ' select a maximum of {}.'.format(
                                      HELPDESK_TICKET_MAX_TIPOLOGIES))

    def test_tipologies_field_is_filtered_by_current_site(self):
        category_in_site = self.get_category(2)
        category_not_in_site = self.get_category(2, site=SiteFactory())
        response = self.client.get(self.get_url(Ticket, 'add'))
        dom = fromstring(response.content)
        form_tipologies = {int(option.attrib['value']) for option
                           in dom.cssselect('#id_tipologies option')}
        self.assertSetEqual(form_tipologies,
                            {c.pk for c in category_in_site.tipologies.all()})
        self.assertSetEqual(
            form_tipologies.intersection(
                {c.pk for c in category_not_in_site.tipologies.all()}), set())

    def test_add_ticket_dont_have_messageinline_in_formset(self):
        """
        Test that in add ticket view, MessageInline not in formsets.
        """
        self.get_category(2)
        response = self.client.get(self.get_url(Ticket, 'add'))
        self.assertInlineClassNotInFormset(response, MessageInline)

    def test_chnage_ticket_have_messageinline_in_formset(self):
        """
        Test that in change ticket view, MessageInline in formsets.
        """
        category = self.get_category(1)
        ticket = TicketFactory(content='',
                               requester=self.requester,
                               tipologies=category.tipologies.all())
        response = self.client.get(
            self.get_url(Ticket, 'change', args=(ticket.pk,)))
        self.assertInlineClassInFormset(response, MessageInline)


class CategoryAndTipologyTest(AdminTestMixin, TestCase):
    def setUp(self):
        self.admin = UserFactory(is_superuser=True)
        self.client.login(username=self.admin.username,
                          password='default')
        self.tipology = TipologyFactory(
            category=CategoryFactory(),
            sites=[SiteFactory() for i in range(0, 2)])

    def test_view_site_from_tipology_changelist_view(self):
        response = self.client.get(self.get_url(Tipology, 'changelist'))
        dom = fromstring(response.content)
        view_site_links = dom.cssselect('a.view_site')
        self.assertEqual(len(view_site_links),
                         self.tipology.sites.count())
        response = self.client.get(view_site_links[0].get('href'))
        self.assertEqual(response.status_code, 200)
        dom = fromstring(response.content)
        self.assertEqual(
            len(dom.cssselect('div.result-list table tbody tr')), 1)

    def test_view_category_from_tipology_changelist_view(self):
        response = self.client.get(self.get_url(Tipology, 'changelist'))
        dom = fromstring(response.content)
        view_category_links = dom.cssselect('a.view_category')
        self.assertEqual(len(view_category_links), 1)
        response = self.client.get(view_category_links[0].get('href'))
        self.assertEqual(response.status_code, 200)
        dom = fromstring(response.content)
        self.assertEqual(
            len(dom.cssselect('div.result-list table tbody tr')), 1)

    def test_view_tipology_from_category_changelist_view(self):
        TipologyFactory(category=self.tipology.category)
        response = self.client.get(self.get_url(Category, 'changelist'))
        dom = fromstring(response.content)
        view_tipology_links = dom.cssselect('a.view_tipology')
        self.assertEqual(len(view_tipology_links), 2)
        for link in view_tipology_links:
            response = self.client.get(link.get('href'))
            self.assertEqual(response.status_code, 200)
            dom = fromstring(response.content)
            self.assertEqual(
                len(dom.cssselect('div.result-list table tbody tr')),
                1)


# class OpenTicketViewTest(AdminTestMixin, TestCase):
#
#     def setUp(self):
#         self.operator = UserFactory(
#             groups=[GroupFactory(name=HELPDESK_OPERATORS[0],
#                                  permissions=list(HELPDESK_OPERATORS[1]))])
#         self.client.login(username=self.operator.username,
#                           password='default')
#         self.category = CategoryFactory(tipologies=['tip1'])
#         self.ticket = TicketFactory(
#             requester=self.operator,
#             tipologies=self.category.tipologies.all())
#
#     def test_for_call_view(self):
#         response = self.client.get(
#             self.get_url(Ticket, 'open', kwargs={'pk': self.ticket.pk}))


# def test_live_server(live_server, admin_client):
#     print(live_server)
#     response = admin_client.get('/admin/')
#     from selenium import webdriver
#     browser = webdriver.Firefox()
#     browser.set_window_size(1024, 768)
#     browser.implicitly_wait(5)
#     browser.get(live_server + '/admin/')
#     # browser.quit()
#     # print(Site.objects.all())
