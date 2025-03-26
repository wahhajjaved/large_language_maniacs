import django.http
import django.shortcuts
import djangoobjfeed.models
import django.contrib.auth.models

def get_return_address(request):
    if '_next' in request.POST:
        return request.POST['_next']
    if '_next' in request.GET:
        return request.GET['_next']
    if 'HTTP_REFERER' in request.META:
        return request.META['HTTP_REFERER']
    return '/'

def post(request, *arg, **kw):    
    feed = djangoobjfeed.models.ObjFeed.objects.get(id=int(request.POST['feed']))

    djangoobjfeed.models.Message(
        feed = feed,
        author = request.user,
        content = request.POST['content']
        ).save()

    return django.shortcuts.redirect(get_return_address(request))

def post_comment(request, *arg, **kw):    
    comment_on_feed_entry = None
    comment_on_comment = None

    if 'comment_on_feed_entry' in request.POST:
        comment_on_feed_entry = djangoobjfeed.models.ObjFeedEntry.objects.get(id=int(request.POST['comment_on_feed_entry']))
        if not comment_on_feed_entry.allowed_to_post_comment(request.user):
            raise Exception('Permission denied')

    if 'comment_on_comment' in request.POST:
        raise Exception("Comments on comments disabled because permission checking isn't implemented")
        comment_on_comment = djangoobjfeed.models.CommentFeedEntry.objects.get(id=int(request.POST['comment_on_comment']))

    djangoobjfeed.models.CommentFeedEntry(
        author = request.user,
        comment_on_feed_entry = comment_on_feed_entry,
        comment_on_comment = comment_on_comment,
        content = request.POST['content']
        ).save()

    return django.shortcuts.redirect(get_return_address(request))

def update_comment(request, *arg, **kw):    
    comment = djangoobjfeed.models.CommentFeedEntry.objects.get(id=int(request.POST['comment']))

    assert comment.author.id == request.user.id

    comment.content = request.POST['content']
    comment.save()

    return django.shortcuts.redirect(get_return_address(request))

def delete_comment(request, *arg, **kw):    
    comment = djangoobjfeed.models.CommentFeedEntry.objects.get(id=int(request.GET['comment']))

    assert comment.author.id == request.user.id

    comment.delete()

    return django.shortcuts.redirect(get_return_address(request))

def get_objfeed(request, objfeed_id):
    data = {}
    feed = djangoobjfeed.models.ObjFeed.objects.get(id=objfeed_id)
    data["feed"] = feed
    data["allowed_to_post"] = feed.subclassobject.allowed_to_post(request.user)
    data["entries"] = feed.entries.order_by("-obj_feed_entry__posted_at").all()[:5]
    return django.shortcuts.render_to_response(
        'djangoobjfeed/objfeed.html', 
        data,
        context_instance=django.template.RequestContext(request))

def get_objfeed_for_user(request, username):
    usr = django.contrib.auth.models.User.objects.get(username=username)
    return get_objfeed(request, usr.feed.id)
