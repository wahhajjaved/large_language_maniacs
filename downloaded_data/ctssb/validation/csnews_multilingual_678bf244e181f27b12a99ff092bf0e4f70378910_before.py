from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from csnews_multilingual.models import Article
from csnews_multilingual.diggpaginator import DiggPaginator
from django.utils.translation import get_language

ARTICLE_NUMBER_PER_PAGE = 20


def _get_page(list, page):
    paginator = DiggPaginator(list, ARTICLE_NUMBER_PER_PAGE, body=5, padding=2)
    try:
        page = int(page)
    except ValueError:
        page = 1

    try:
        tor = paginator.page(page)
    except:
        tor = paginator.page(paginator.num_pages)
    return tor


def index(request):
    articles = Article.objects.language().filter(is_public=True)
    page = _get_page(articles, request.GET.get('page', '1'))
    return render_to_response('news/articles.html', locals(), context_instance=RequestContext(request))


def article_index(request, article_slug):
    obj = get_object_or_404(Article, slug=article_slug, language=get_language())
    return render_to_response('news/article.html', locals(), context_instance=RequestContext(request))


def archive(request):
    return render_to_response('news/archive.html', locals(), context_instance=RequestContext(request))
