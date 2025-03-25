from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from api.models import Post, Task, WorkLog, Payment
from django.db.models import Sum
from datetime import datetime, timedelta, date


class RootView(LoginRequiredMixin, View):
    def get(self, request):
        blogStats = {}  # Build data for blog dashboard

        blogStats['count'] = Post.objects.filter(worklog__isnull=True).count()

        if blogStats['count'] > 0:
            latestPost = Post.objects.filter(worklog__isnull=True).order_by('-created')[0]
            daysDelta = (datetime.today() - latestPost.created).days
            if not daysDelta:
                blogStats['latest'] = "today"
            else:
                blogStats['latest'] = "{} days ago".format(daysDelta)
        else:
            blogStats['latest'] = "No posts"

        todoStats = {}  # Build data for todo dashboard

        currentLogs = WorkLog.objects.filter(task__status=2).filter(post__deleted=False)
        currentLogged = currentLogs.aggregate(Sum('log'))['log__sum'] or 0
        currentTasks = Task.objects.filter(status=2)
        currentEstimation = currentTasks.aggregate(Sum('estimation'))['estimation__sum'] or 0
        todoStats['payLoad'] = currentEstimation - currentLogged

        weekAgo = datetime.today() - timedelta(days=7)
        latestLogs = WorkLog.objects.filter(post__deleted=False).filter(post__created__gte=weekAgo)
        todoStats['lastWeekLogged'] = latestLogs.aggregate(Sum('log'))['log__sum'] or 0

        moneyStats = {}  # Build data for money dashboard

        todayPayments = Payment.objects.filter(spent=date.today()).aggregate(Sum('amount'))['amount__sum'] or 0
        moneyStats['today'] = todayPayments

        monthPayments = Payment.objects.filter(spent__month=date.today().month, spent__year=date.today().year).aggregate(Sum('amount'))['amount__sum'] or 0
        moneyStats['month'] = monthPayments

        return render(request, 'root/home.html', {
            'blogStats': blogStats,
            'todoStats': todoStats,
            'moneyStats': moneyStats,
        })
