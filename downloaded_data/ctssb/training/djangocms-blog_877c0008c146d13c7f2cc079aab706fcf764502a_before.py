# -*- coding: utf-8 -*-
from django.contrib.auth import get_user_model
from django.core.urlresolvers import resolve
from django.utils.timezone import now
from django.utils.translation import get_language
from django.views.generic import ListView, DetailView

from parler.views import ViewUrlMixin, TranslatableSlugMixin

from .models import Post, BlogCategory, BLOG_CURRENT_POST_IDENTIFIER
from .settings import get_setting

User = get_user_model()


class BaseBlogView(ViewUrlMixin):

    def get_queryset(self):
        language = get_language()
        queryset = self.model._default_manager.language(language_code=language)
        if not self.request.toolbar or not self.request.toolbar.edit_mode:
            queryset = queryset.published()
        return queryset.on_site()

    def render_to_response(self, context, **response_kwargs):
        response_kwargs['current_app'] = resolve(self.request.path).namespace
        return super(BaseBlogView, self).render_to_response(context, **response_kwargs)


class PostListView(BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    template_name = 'djangocms_blog/post_list.html'
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-latest'

    def get_context_data(self, **kwargs):
        context = super(PostListView, self).get_context_data(**kwargs)
        context['TRUNCWORDS_COUNT'] = get_setting('POSTS_LIST_TRUNCWORDS_COUNT')
        return context


class PostDetailView(TranslatableSlugMixin, BaseBlogView, DetailView):
    model = Post
    context_object_name = 'post'
    template_name = 'djangocms_blog/post_detail.html'
    slug_field = 'slug'
    view_url_name = 'djangocms_blog:post-detail'

    def get_context_data(self, **kwargs):
        context = super(PostDetailView, self).get_context_data(**kwargs)
        context['meta'] = self.get_object().as_meta()
        context['use_placeholer'] = get_setting('USE_PLACEHOLDER')
        setattr(self.request, BLOG_CURRENT_POST_IDENTIFIER, self.get_object())
        return context


class PostArchiveView(BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    template_name = 'djangocms_blog/post_list.html'
    date_field = 'date_published'
    allow_empty = True
    allow_future = True
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-archive'

    def get_queryset(self):
        qs = super(PostArchiveView, self).get_queryset()
        if 'month' in self.kwargs:
            qs = qs.filter(**{'%s__month' % self.date_field: self.kwargs['month']})
        if 'year' in self.kwargs:
            qs = qs.filter(**{'%s__year' % self.date_field: self.kwargs['year']})
        return qs

    def get_context_data(self, **kwargs):
        kwargs['month'] = int(self.kwargs.get('month')) if 'month' in self.kwargs else None
        kwargs['year'] = int(self.kwargs.get('year')) if 'year' in self.kwargs else None
        if kwargs['year']:
            kwargs['archive_date'] = now().replace(kwargs['year'], kwargs['month'] or 1, 1)
        return super(PostArchiveView, self).get_context_data(**kwargs)


class TaggedListView(BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    template_name = 'djangocms_blog/post_list.html'
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-tagged'

    def get_queryset(self):
        qs = super(TaggedListView, self).get_queryset()
        return qs.filter(tags__slug=self.kwargs['tag'])

    def get_context_data(self, **kwargs):
        kwargs['tagged_entries'] = (self.kwargs.get('tag')
                                    if 'tag' in self.kwargs else None)
        return super(TaggedListView, self).get_context_data(**kwargs)


class AuthorEntriesView(BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    template_name = 'djangocms_blog/post_list.html'
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-authors'

    def get_queryset(self):
        qs = super(AuthorEntriesView, self).get_queryset()
        if 'username' in self.kwargs:
            qs = qs.filter(**{'author__%s' % User.USERNAME_FIELD: self.kwargs['username']})
        return qs

    def get_context_data(self, **kwargs):
        kwargs['author'] = User.objects.get(**{User.USERNAME_FIELD: self.kwargs.get('username')})
        return super(AuthorEntriesView, self).get_context_data(**kwargs)


class CategoryEntriesView(BaseBlogView, ListView):
    model = Post
    context_object_name = 'post_list'
    template_name = 'djangocms_blog/post_list.html'
    _category = None
    paginate_by = get_setting('PAGINATION')
    view_url_name = 'djangocms_blog:posts-category'

    @property
    def category(self):
        if not self._category:
            self._category = BlogCategory.objects.active_translations(get_language(), slug=self.kwargs['category']).latest('pk')
        return self._category

    def get_queryset(self):
        qs = super(CategoryEntriesView, self).get_queryset()
        if 'category' in self.kwargs:
            qs = qs.filter(categories=self.category.pk)
        return qs

    def get_context_data(self, **kwargs):
        kwargs['category'] = self.category
        return super(CategoryEntriesView, self).get_context_data(**kwargs)
