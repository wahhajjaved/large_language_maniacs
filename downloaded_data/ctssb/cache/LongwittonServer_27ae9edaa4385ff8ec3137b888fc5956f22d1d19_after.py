# Create your views here.
from longwitton.models import Page
from django.http import HttpResponse

def current(request):
    try:
        last_page = Page.objects.all().order_by('-timestamp')[0]
        return HttpResponse(last_page.url, content_type='text/plain')
    except Exception, e:
        return HttpResponse(e)

# Modifies state with a GET! Bad me.
def update(request, new_url):
    p = Page(url=new_url)
    p.save()
    return HttpResponse('Fine.')
