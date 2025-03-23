#! /usr/bin/env python2.7
# -*- coding: utf-8 -*-
# vim: ts=4 et sw=4 sts=4

"""
Tests for the "feeds" app.
==========================
  
  :date: 2014-05-03
  :version: 0.1
  :description: Test Cases for :py:mod:`feeds`

- :py:mod:`feeds.models`
- :py:mod:`feeds.views`

 - for anonymous users / not logged in
 - for logged in users

- :py:mod:`feeds.tasks`

.. moduleauthor:: Andreas Neumeier <andreas@neumeier.org>

"""

import feedparser

from django.test import TestCase
from django.test.client import Client
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse

from feeds.models import Feed, Post
from feeds.tasks import aggregate, entry_process, feed_refresh, dummy
from feeds.tasks import entry_update_twitter, entry_update_facebook

from feeds import ENTRY_NEW, ENTRY_UPDATED, ENTRY_SAME, ENTRY_ERR

from datetime import datetime

class ModelTest(TestCase):
    """
    Test Models and their Managers

    :py:mod:`feeds.tests.ModelTest` aims to test following models:

    - :py:mod:`feeds.models.SiteManager`
    - :py:mod:`feeds.models.Site`
    - :py:mod:`feeds.models.TagManager`
    - :py:mod:`feeds.models.Tag`
    - :py:mod:`feeds.models.CategoryManager`
    - :py:mod:`feeds.models.Category`
    - :py:mod:`feeds.models.Feed`
    - :py:mod:`feeds.models.Post`
    - :py:mod:`feeds.models.Enclosure`
    
    .. codeauthor:: Andreas Neumeier <andreas@neumeier.org>
    """
    def setUp(self):
        """
        Set up enivironment to test models
        """
        self.client = Client()

    def test_site(self):
        """
        Create a :py:mod:`feeds.models.Site` Object and verify it functions properly.
        """

        from feeds.models import Site
        s = Site(url="https//angry-planet.com/")
        s.save()
        self.assertContains( s.get_absolute_url(), s.pk)
        self.assertEqual(str(s), "test")
        """Assert the __str__ representation equals the site-name."""

    def test_tag(self):
        """
        Test a Tag
        """
        from feeds.models import Tag
        """Import the :py:mod:`feeds.models.Tag`-model."""
        t = Tag(name="tag")
        """Instanciate the model."""
        tagid = t.save()
        """Save the model and retrieve the pk/id."""
        self.assertNotEqual(tagid, 0)
        """Assert the pk/id is not 0."""
        self.assertEqual(str(t), "tag")
        """Assert the __str__ representation equals the tag-name."""
        self.assertContains( t.get_absolute_url(), t.pk)
        """Assert the tag URL contains the tag.pk."""

    def test_category(self):
        """
        Test a :py:mod:`feeds:models.Category`

        .. todo:: use `fixtures` instead.
        """
        from feeds.models import Category
        c = Category(name="default")
        c.save()
        self.assertEquals(str(c), c.name)
        self.assertContains(c.get_absolute_url(), c.id)

    def tearDown(self):
        """
        Clean up environment after model tests
        """
        pass

class TaskTest(TestCase):
    """
    Test Tasks

    ..codeauthor:: Andreas Neumeier <andreas@neumeier.org>
    """
    def setUp(self):
        """
        Set up enivironment to test models
        """
        self.feed1 = Feed(feed_url=reverse('planet:rss1'), name="rss1", short_name="rss1")
        self.feed1.save()

        self.feed2 = Feed(feed_url=reverse('planet:rss2'), name="rss2", short_name="rss2")
        self.feed2.save()

        self.post1 = Post(feed=self.feed1, link="http://localhost/post1")
        self.post1.save()
        
        self.post2 = Post(feed=self.feed2, link="http://localhost/post2")
        self.post2.save()

    def test_task_time(self):
        """
        .. todo:: Needs amqp.
        """
        dummy.delay(invocation_time=datetime.now())
        dummy(10)

    def test_aggregate(self):
        result = aggregate()
        self.assertEqual(result, True)

    def test_count_tweets(self):
        result = entry_update_twitter(Post.objects.all()[0].id)
        self.assertEqual(result, 0)

    def test_count_share_like(self):
        result = entry_update_facebook(Post.objects.all()[0].id)
        self.assertEqual(result, True)


    def test_feed_refresh(self):
        feed = Feed.objects.all()[0]
        result = feed_refresh(feed.id)
        self.assertGreaterEqual(result[ENTRY_NEW], 0)
        self.assertGreaterEqual(result[ENTRY_UPDATED], 0)
        self.assertGreaterEqual(result[ENTRY_SAME], 0)
        self.assertGreaterEqual(result[ENTRY_ERR], 0)

    def test_entry_process(self):
        f = Feed.objects.all()[0]
        feed = feedparser.parse(f.feed_url)
        for entry in feed.entries:
            result = entry_process(entry, f.id, None, None)
            self.assertEqual(result, True)

    def tearDown(self):
        pass

class ViewsAnonymousTest(TestCase):
    """
    Test whether all :py:mod:`feeds.views` are working.

    Working, in this context means the, corresponding URL returns:

    - "2xx OK" for publically visible sites/pages.
    - "3xx Redirect" for pages that require authentication.

    URLs available in :mod:`feeds` are defined in :mod:`feeds.urls`.

    .. moduleauthor:: Andreas Neumeier <andreas@neumeier.org>
    """

    fixtures = ['Feed.yaml']

    def setUp(self):
        """
        Set up environment.
        """
        from models import Site
        site = Site(url="https://angry-planet.com/")
        site.save()
        self.site_id = site.pk
        """Test Site."""

        self.client = Client()
        """Test Client."""

    def test_feed_home(self):
        """
        Go to feed-home.

        Assert the returned page comes with "HTTP 200 OK".

        .. todo:: define/document expected result/return values.
        """
        result = self.client.get(reverse('planet:feed-home'))
        self.assertEqual(result.status_code, 200)

    def site_home(self):
        """
        site-home
        ---------
            :url: url(r'^site/$', SiteListView.as_view(), name="site-home"), 

            Should return 200
        """
        result = self.client.get(reverse('planet:site-home'))
        self.assertEqual(result.status_code, 200)

    def site_submit(self):
        """
        site-submit
        -----------
            :url: url(r'^site/submit/$', SiteSubmitWizardView.as_view(SiteSubmitForms), name="site-submit"), 

            Should return a form.
            Should accept a post.
        """
        result = self.client.get(reverse('planet:site-submit'))
        self.assertEqual(result.status_code, 200)

    def site_add(self):
        """
        site-add
        --------
            :url: url(r'^site/add/$', SiteCreateView.as_view(), name="site-add"), 

            To add a site should require credentials.
            
            Should result in a redirect to the login-page.
        """
        result = self.client.get(reverse('planet:site-add'))
        self.assertRedirects(result, '/accounts/login/?next=%s'%(reverse('planet:site-add')))
        self.assertEqual(result.status_code, 302)

    def site_view(self):
        """
        site-view
        ---------
            :url: url(r'^site/(?P<pk>\d+)/$', SiteDetailView.as_view(), name="site-view"), 

            Viewing a site should be available to the public.

            Should return 200.
        """
        result = self.client.get(reverse('planet:site-view', args=str(self.site_id)))
        self.assertEqual(result.status_code, 200)

    def site_update(self):
        """
        site-update
        -----------
            :url: url(r'^site/(?P<pk>\d+)/update/$', SiteUpdateView.as_view(), name="site-update"),

            .. todo:: needs to be defined.
        """
        result = self.client.get(reverse('planet:site-update', args=str(self.site_id)))
        self.assertRedirects(result, '/accounts/login/?next=%s'%(reverse('planet:site-update', args=str(self.site_id))))
        self.assertEqual(result.status_code, 302)

    def site_delete(self):
        """
        site-delete
        -----------
            :url: url(r'^site/(?P<pk>\d+)/delete/$', SiteDeleteView.as_view(), name="site-delete"), 
            
            .. todo:: needs to be defined.
        """
        result = self.client.get(reverse('planet:site-delete', args=str(self.site_id)))
        self.assertEqual(result.status_code, 302)

    def test_site_views(self):
        """
        Site.
        =====

        Test the :py:mod:`feeds.models.Site` section from the user-side.

        Access the following pages, in order, as defined in :py:mod:`feeds.urls`.

        """
        self.site_home()
        self.site_submit()
        self.site_add()
        self.site_view()
        self.site_update()
        self.site_delete()

    def feed_home(self):
        """
        feed-home
        ---------
            :url: url(r'^list/$', FeedListView.as_view(), name="feed-home"), 

            Should return 200 for an anonymous user.
        """
        result = self.client.get(reverse('planet:feed-home'))
        self.assertEqual(result.status_code, 200)

    def feed_home_paginated(self):
        """
        feed-home-paginated
        -------------------
            :url: url(r'^page/(?P<page>\w+)/$', FeedListView.as_view(), name="feed-home-paginated"), 

            - Should return 200 for an anonymous user.
            - Should allow to navigate between paginated results.
        """
        result = self.client.get(reverse('planet:feed-home-paginated', args=(1,)))
        self.assertEqual(result.status_code, 200)

    def feed_add(self):
        """
        feed-add
        --------
            :url: url(r'^add/$', FeedCreateView.as_view(), name="feed-add"), 

        """
        result = self.client.get(reverse('planet:feed-add'))
        self.assertRedirects(result, '/accounts/login/?next=%s'%(reverse('planet:feed-add')))
        self.assertEqual(result.status_code, 302)

    def feed_view(self):
        """
        feed-view
        ---------
            :url: url(r'^(?P<pk>\d+)/$', FeedDetailView.as_view(), name="feed-view"), 
            
            Viewing details for a :py:mod:`feeds.models.Feed` should be available to the public.

            Should return 200.

            The `fixture` has a feed with the ID 1.
        """

        result = self.client.get(reverse('planet:feed-view', args=(1,)))
        self.assertEqual(result.status_code, 200)

    def feed_update(self):
        """
        feed-update
        -----------
            :url: url(r'^(?P<pk>\d+)/update/$', FeedUpdateView.as_view(), name="feed-update"),

            The `fixture` has a feed with the ID 1.

            .. todo:: needs to be defined.
        """
        result = self.client.get(reverse('planet:feed-update', args=(1,)))
        self.assertRedirects(result, '/accounts/login/?next=%s'%(reverse('planet:feed-update', args=(1,))))
        self.assertEqual(result.status_code, 302)

    def feed_delete(self):
        """
        feed-delete
        -----------
            :url: url(r'^(?P<pk>\d+)/delete/$', FeedDeleteView.as_view(), name="feed-delete"), 
            
            The `fixture` has a feed with the ID 1.

            .. todo:: needs to be defined.
        """
        result = self.client.get(reverse('planet:feed-delete', args=(1,)))
        self.assertRedirects(result, '/accounts/login/?next=%s'%(reverse('planet:feed-delete', args=(1,))))
        self.assertEqual(result.status_code, 302)

    def test_feed_views(self):
        """
        Feed.
        =====

        Test Feed Views:

        .. todo::
            url(r'^(?P<pk>\d+)/refresh/$', FeedRefreshView.as_view(), name="feed-refresh"), 
        """
        self.feed_home()
        self.feed_home_paginated()
        self.feed_add()
        self.feed_view()
        self.feed_update()
        self.feed_delete()
        # self.feed_refresh()


class ViewsLoggedInTest(TestCase):
    """
    Test Feeds views for users that are authenticated.
    """

    username = "john"
    password = "password"

    def setUp(self):
        """
        Set up enivironment to test models
        """
        self.user = User.objects.create_user(self.username, 'lennon@thebeatles.com', self.password)
        """Test user."""
        
        self.feed1 = Feed(feed_url=reverse('planet:rss1'), name="rss1", short_name="rss1")
        self.feed1.save()
        """Feed 1."""

        self.feed2 = Feed(feed_url=reverse('planet:rss2'), name="rss2", short_name="rss2")
        self.feed2.save()
        """Feed 2."""

        self.client = Client()
        """Test Client."""

    def test_feed_home(self):
        """
        go to feed-home
        """
        result = self.client.get(reverse('planet:feed-home'))
        self.assertEqual(result.status_code, 200)

    def test_feed_home_paginated(self):
        """
        go to feed-home-paginated
        """
        result = self.client.get(reverse('planet:feed-home-paginated', args=("1",)))
        self.assertEqual(result.status_code, 200)

    def test_feed_add_anonymous(self):
        """
        go to feed-add
        """
        result = self.client.get(reverse('planet:feed-add'), follow=False)
        self.assertEqual(result.status_code, 302)
        # self.assertRedirects(result, '/accounts/login')

    def test_feed_add_logged_in_no_credentials(self):
        """
        go to feed-add
        """
        self.client.login(username=self.username, password=self.password)
        result = self.client.get(reverse('planet:feed-add'), follow=False)
        self.assertEqual(result.status_code, 302)
        # self.assertRedirects(result, '/accounts/login')

    def test_feed_add_logged_in_valid_credentials(self):
        """
        go to feed-add
        """
        self.user = User.objects.get(username=self.username)
        permission = Permission.objects.get(codename="add_feed")
        self.user.user_permissions.add(permission)
        self.user.save()
        self.client.login(username=self.username, password=self.password)
        """.. todo:: this currently gives 'AttributeError: 'module' object has no attribute 'CRISPY_TEMPLATE_PACK'."""
        # result = self.client.get(reverse('planet:feed-add'), follow=False)
        # self.assertEqual(result.status_code, 200)

    def test_feed_add_post_anonymous(self):
        """
        go to feed-add, anonymous client
        """
        result = self.client.post(reverse('planet:feed-add'))
        self.assertEqual(result.status_code, 302)

    def test_feed_add_post_no_credential(self):
        """
        go to feed-add, anonymous client
        """
        result = self.client.post(reverse('planet:feed-add'))
        self.client.login(username=self.username, password=self.password)
        self.assertEqual(result.status_code, 302)

    def test_feed_add_post_valid_credential(self):
        """
        go to feed-add, anonymous client
        """
        result = self.client.post(reverse('planet:feed-add'))
        self.client.login(username=self.username, password=self.password)
        permission = Permission.objects.get(codename="add_feed")
        self.assertEqual(result.status_code, 302)

    def test_feed_view(self):
        """
        go to feed-view for feed 1
        """
        result = self.client.get(reverse('planet:feed-view', args=(1,)))
        """.. todo:: figure out why this gives 404"""
        # self.assertEqual(result.status_code, 200)

    def test_category_home(self):
        """
        go to category home
        """
        c = Client()
        result = c.get(reverse('planet:category-home'))
        self.assertEqual(result.status_code, 200)

    def test_tags_home(self):
        """
        go to tags home
        """
        c = Client()
        result = c.get(reverse('planet:tag-home'))
        self.assertEqual(result.status_code, 200)

    def test_FeedRefreshView(self):
        """
        manually refresh a feed
        """
        c = Client()
        result = c.get(reverse('planet:feed-refresh', args=(Feed.objects.all()[0].id,)))
        self.assertEqual(result.status_code, 302)

    def test_create_post(self):
        """
        create a new post
        """
        feed = Feed.objects.all()[0]
        """Get first feed from the db. We use fixtures, so we can assume there are feeds."""
        with self.assertNumQueries(1):
            Post.objects.create(feed=feed)


