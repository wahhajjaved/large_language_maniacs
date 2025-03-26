from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import PageNotAnInteger, EmptyPage
from django.http import Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from judge.models import Problem, Submission, SubmissionTestCase
from judge.utils.diggpaginator import DiggPaginator
from judge.views import get_result_table


def submission_status(request, code):
    try:
        submission = Submission.objects.get(id=int(code))
        test_cases = SubmissionTestCase.objects.filter(submission=submission)
        return render_to_response('submission_status.html',
                                  {'submission': submission, 'test_cases': test_cases,
                                   'title': 'Submission of %s by %s' %
                                            (submission.problem.name, submission.user.user.username)},
                                  context_instance=RequestContext(request))
    except ObjectDoesNotExist:
        raise Http404()


def chronological_submissions(request, code, page=1):
    return problem_submissions(request, code, page, True, title="All submissions for %s", order=['-id'])


def problem_submissions(request, code, page, dynamic_update, title, order):
    try:
        problem = Problem.objects.get(code=code)
        submissions = Submission.objects.filter(problem=problem).order_by(*order)
        can_see_results = (request.user.is_authenticated() and
                           submissions.filter(user=request.user.profile, result='AC').exists())

        paginator = DiggPaginator(submissions, 50, body=6, padding=2)
        try:
            submissions = paginator.page(page)
        except PageNotAnInteger:
            submissions = paginator.page(1)
        except EmptyPage:
            submissions = paginator.page(paginator.num_pages)
        return render_to_response('submissions.html',
                                  {'submissions': submissions,
                                   'results': get_result_table(code),
                                   'can_see_results': can_see_results,
                                   'dynamic_update': dynamic_update,
                                   'title': title % problem.name,
                                   'show_problem': False},
                                  context_instance=RequestContext(request))
    except ObjectDoesNotExist:
        raise Http404()


def submissions(request, page=1):
    paginator = DiggPaginator(Submission.objects.order_by('-id'), 50, body=6, padding=2)
    try:
        submissions = paginator.page(page)
    except PageNotAnInteger:
        submissions = paginator.page(1)
    except EmptyPage:
        submissions = paginator.page(paginator.num_pages)
    return render_to_response('submissions.html',
                              {'submissions': submissions,
                               'results': get_result_table(None),
                               'can_see_results': False, # TODO
                               'dynamic_update': True,
                               'title': 'All submissions',
                               'show_problem': True},
                              context_instance=RequestContext(request))