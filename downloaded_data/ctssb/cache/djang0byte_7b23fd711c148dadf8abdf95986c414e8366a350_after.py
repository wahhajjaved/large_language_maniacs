# -*- coding: utf-8 -*-
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#       
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#       
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.



from django.db import transaction
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from main.forms import *
from main.models import *
from django.views.decorators.cache import cache_page
from simplepagination import paginate
from annoying.decorators import render_to
from tagging.models import TaggedItem
from main.utils import Access
from django.template import RequestContext
from settings import DEFAULT_CACHE_TIME
from django.views.decorators.vary import vary_on_cookie
from django.utils import simplejson
from django.utils.translation import gettext as _


@transaction.commit_on_success
@login_required
def newpost(request, type = 'post'):
    """Create post form and action

    Keyword arguments:
    request -- request object
    type -- String

    Returns: HttpResponse

    """
    profile = request.user.get_profile()
    type = request.GET.get('type') or 'post'
    preview = False
    is_draft = False
    if request.POST.get('draft'):
        is_draft = True
    if request.POST.get('preview'):
        preview = True
        is_draft = True
    extend = 'base.html'
    if request.GET.get('json'):
        extend = 'json.html'
    if type != 'answer':
        _type = type
        print type
        if type == 'post':
            type = 0
            form = CreatePostForm
        elif type == 'link':
            type = 1
            form = CreatePostLinkForm
        else:
            type = 2
            form = CreatePostTranslateForm
        if request.method == 'POST':
            form = form(request.POST)
            if form.is_valid() and not preview:
                data = form.cleaned_data
                if is_draft:
                    post = Draft()
                else:
                    post = Post()
                post.author = request.user
                post.type = type
                post.set_data(data)
                post.save(edit=False)
                if not is_draft:
                    post.set_tags(data['tags'])
                    return HttpResponseRedirect('/post/%d/' % (post.id))
                else:
                    if preview:
                        return HttpResponseRedirect('/draft/%d/' % (draft.id))
                    else:
                        return HttpResponseRedirect('/draft/')
            else:
                if is_draft:
                    draft = Draft()
                    draft.author = request.user
                    draft.set_data(form.data)
                    draft.type = type
                    draft.save(edit=False)
                    if preview:
                        return HttpResponseRedirect('/draft/%d/' % (draft.id))
                    else:
                        return HttpResponseRedirect('/draft/')
                return render_to_response('newpost.html',
                                    {'form': form, 'blogs': Blog.create_list(profile), 'type': _type, 'extend': extend},
                                     context_instance=RequestContext(request))
        else:
            return render_to_response('newpost.html',
                                  {'form': form(), 'blogs': Blog.create_list(profile), 'type': _type, 'extend': extend},
                                   context_instance=RequestContext(request))
    else:
        if request.method == 'POST':
            post = Post()
            post.title = request.POST.get('title')
            post.author = request.user
            post.set_blog(request.POST.get('blog'))
            if request.POST.get('multi', 0):
                post.type = 4#'Multiple Answer'
            else:
                post.type = 3#post.type = 'Answer'
            post.save()
            post.set_tags(request.POST.get('tags'))
            post.create_comment_root()
            for answer_item in range(int(request.POST.get('count'))):
                answer = Answer()
                answer.value = request.POST.get(str(answer_item))
                answer.post = post
                answer.save()
            return HttpResponseRedirect('/post/%d/' % (post.id))
        multi = False
        count = 2
        return render_to_response('newanswer.html', {'answers_count': range(count),
        'count': count, 'blogs': profile.get_blogs(), 'multi': multi, 'extend': extend},
                                    context_instance=RequestContext(request))

@cache_page(DEFAULT_CACHE_TIME)
@render_to('post.html')
def post(request, id):
    """Print single post

    Keyword arguments:
    request -- request object
    id -- Integer

    Returns: HttpResponse

    """
    post = Post.objects.get(id=id)
    author = post.author.get_profile()
    comments = post.get_comment()
    form = CreateCommentForm({'post': id, 'comment': 0})
    post.get_content = post.get_full_content
    post.is_answer(request.user)
    options = {}
    if request.user.is_authenticated():
        try:
            options['favourite'] = Favourite.objects.get(post=post, user=request.user)
        except Favourite.DoesNotExist:
            options['favourite'] = False
        try:
            options['spy'] = Spy.objects.get(post=post, user=request.user)
        except Spy.DoesNotExist:
            options['spy'] = False
    return({'post': post, 'author': author, 'comments': comments, 'comment_form': form, "options": options,
        'single': True, 'PERM_EDIT_POST': post.type < 3 and (request.user.has_perm('main.change_post') or request.user == post.author)})


@cache_page(DEFAULT_CACHE_TIME)
@render_to('post_list.html')
@paginate(style='digg', per_page=10)
def post_list(request, type = None, param = None):
    """Print post list

    Keyword arguments:
    request -- request object
    type -- String
    param -- String

    Returns: Array

    """
    posts = None
    subject = None
    option = None
    if type == None:
        blog_types = BlogType.objects.filter(display_default=False)
        blogs = Blog.objects.filter(type__in=blog_types)
        posts = Post.objects.exclude(blog__in=blogs)
    elif BlogType.check(type):
        posts = Post.objects.filter(blog__in=BlogType.objects.get(name=type).get_blogs())
    elif type == 'pers':
        posts = Post.objects.filter(blog=None)
    elif type == 'blog':
        blog = Blog.objects.get(id=param)
        posts = blog.get_posts()
        subject = blog
        option = blog.check_user(request.user)
    elif type == 'tag':
        posts = TaggedItem.objects.get_by_model(Post, param)
        subject = param
        #posts = [post.post for post in posts_with_tag]
    elif type == 'auth':
        user = User.objects.get(username=param)
        profile = user.get_profile()
        posts = profile.get_posts()
        subject = profile
        option = profile.is_my_friend(request.user)
    elif type == 'favourite':
        #TODO: rewrite favorite to ManyToMany
        posts = [f.post for f in Favourite.objects.select_related('post').filter(user=request.user)]
    try:
        posts = posts.order_by('-id')
    except AttributeError:
        pass
    #TODO: fix answer result in post list
    return {'object_list': posts, 'single': False, 'type': type, 'subject': subject, 'option': option}

def post_list_with_param(request, type, param = None):
    """Wrapper for post_list

    Keyword arguments:
    request -- request object
    type -- String
    param -- String

    Returns: HttpResponse

    """
    return post_list(request, type, param)

@login_required
def new_comment(request, post = 0, comment = 0):
    """New comment form

    Keyword arguments:
    request -- request object
    post -- Integer
    comment -- Integer

    Returns: HttpResponse

    """
    extend = 'base.html'
    json = False
    if request.GET.get('json', 0):
        extend = 'json.html'
        json = True
    print request.GET.get('json')
    if request.method == 'POST':
        form = CreateCommentForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            post = Post.objects.get(id=data['post'])
            if data['comment'] == 0:
                root = Comment.objects.get(post=post, depth=1)
                no_notify = post.author == request.user
            else:
                root = Comment.objects.get(id=data['comment'])
                no_notify = root.author == request.user

            comment = root.add_child(post=post,
            author=request.user, text=utils.parse(data['text']),
            created=datetime.datetime.now())
            comment.save()
            if not no_notify:
                Notify.new_comment_notify(comment)
            if json:
                return(render_to_response('comment.html',
                                          {'post': comment.post, 'comment': comment, 'extend': extend},
                                          context_instance=RequestContext(request)))
            else:
                return HttpResponseRedirect('/post/%d/#cmnt%d' %
                            (comment.post.id, comment.id))
    else:
        form = CreateCommentForm({'post': post, 'comment': comment})
    return render_to_response('new_comment.html', {'form': form, 'extend': extend, 'pid': post, 'cid': comment},
                              context_instance=RequestContext(request))




@cache_page(DEFAULT_CACHE_TIME)
@vary_on_cookie
@login_required
@render_to('lenta.html')
@paginate(style='digg', per_page=10)
def lenta(request):
    """Return last posts and comments, adresed to user

    Keyword arguments:
    request -- request object

    Returns: Array

    """
    notifs = Notify.objects.select_related('post', 'comment').filter(user=request.user).order_by("-id")
    return {'object_list': notifs}

