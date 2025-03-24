from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.core.paginator import Paginator
from qa.models import Question

# Create your views here.
def test(request, *args, **kwargs):
	return HttpResponse('OK')

def main(request):
    questions = Question.objects.order_by('-added_at')
    limit = request.GET.get('limit', 10)
    page = request.GET.get('page', 1)
    paginator = Paginator(questions, limit)
    paginator.baseurl = '?page='
    page = paginator.page(page)
    return render(request, 'fresh_questions.html', {
	'quests': page.object_list,
        'paginator': paginator, 'page': page,
    })

def popular(request):
    questions = Question.order_by('-rating')
    limit = request.GET.get('limit', 10)
    page = request.GET.get('page', 1)
    paginator = Paginator(questions, limit)
    paginator.baseurl = '/popular?page='
    page = paginator.page(page)
    return render(request, 'fresh_questions.html', {
	'quests': page.object_list,
        'paginator': paginator, 'page': page,
    })

def question(request, id):
    try:
	question = Question.objects.get(pk=id)
    except Question.DoesNotExist:
        raise Http404	 
    return render(request, 'question.html', {
        'quest': question
    })
