# TODO: check usage of these functions and rename/refactor

from django.db.models import Q

def get_questions_with_tags(tlist, select='any', active_only=True, endorsed_only=True):
    if isinstance(tlist, str):
        result = models.Question.objects.filter(tags__name=tlist)
    else:
        if select == 'any':
            tfilters = Q(tags__name=tlist[0])
            for t in tlist[1:]:
                tfilters = tfilters | Q(tags__name=t)
            result = models.Question.objects.filter(tfilters)
        elif select == 'all':
            result = models.Question.objects.filter(tags__name=tlist[0])
            for t in tlist[1:]:
                result = result.filter(tags__name=t)
    # more filtering
    if active_only:
        result = result.filter(active=True)
    if endorsed_only:
        result = result.exclude(endorsed_by__isnull=True)
    return result

def get_questions_with_category(category='all', active_only=True, endorsed_only=False):
    ''' can be called with all, string for category name or instance of Category '''
    if category == 'all':
        result = models.Question.objects.all()
    elif isinstance(category, str):
        result = models.Question.objects.filter(category__name=category)
    elif isinstance(category, models.Category):
        result = models.Question.objects.filter(category=category)

    # filtering
    if active_only:
        result = result.filter(active=True)
    if endorsed_only:
        result = result.exclude(endorsed_by__isnull=True)

    return result

def get_questions_with_tag_for_day(tag, select):
    if isinstance(tag, str):
        query = models.Question.objects.filter(tags__name=tag).exclude(endorsed_by__isnull=True)
        for q in query:
            if q.day == select:
                return q
        return None
