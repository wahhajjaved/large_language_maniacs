from WS16_2012.views.views import View
from WS16_2012.models import Project

from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.contrib.auth.models import User


class AssignedTasksReportView(View):

    @method_decorator(permission_required(perm='auth.admin', raise_exception=True))
    def get(self, request, project_id):

        try:
            p = Project.objects.get(id=project_id)

            task_no = float(p.task_set.count())

            if task_no == 0:
                return JsonResponse({"message": "No data"}, status=402)

            data = []
            for u in p.participants.all():
                asg_no = float(u.assigned.all().filter(project=p).count())
                if task_no != 0:
                    data.append({"username": u.username, "percentage": (asg_no/task_no)})
                else:
                    data.append({"username": u.username, "percentage": 0})

            return JsonResponse(data, status=200, safe=False)
        except Exception as e:
            return JsonResponse({"message": "Bad request"}, status=400)


class CompletedTasksReportView(View):

    @method_decorator(permission_required(perm='auth.admin', raise_exception=True))
    def get(self, request, project_id):

        try:
            p = Project.objects.get(id=project_id)

            all_zero = True

            data = []
            for u in p.participants.all():
                asg_no = float(u.assigned.all().count())
                cmp_no = float(u.assigned.filter(status='DONE').all().count())

                if asg_no != 0:
                    data.append({"username": u.username, "percentage": (cmp_no/asg_no)})
                else:
                    data.append({"username": u.username, "percentage": 0})
                    all_zero = False

            if all_zero:
                return JsonResponse({"message": "No data"}, status=402)

            return JsonResponse(data, status=200, safe=False)
        except Exception as e:
            return JsonResponse({"message": "Bad request"}, status=400)


class TasksCreatedView(View):

    @method_decorator(permission_required(perm='auth.admin', raise_exception=True))
    def get(self, request, project_id):

        try:
            p = Project.objects.get(id=project_id)

            tasks = p.task_set.all().order_by('date_created')

            x = []
            y = []

            for t in tasks:

                dc = t.date_created.strftime("%Y/%m/%dT%H:00:00")

                if len(x) != 0 and x[-1] == dc:
                    y[-1] += 1
                    continue

                x.append(dc)
                y.append(1)

            return JsonResponse({"labels": x, "data": y}, status=200, safe=False)
        except Exception as e:
            return JsonResponse({"message": "Bad request"}, status=400)


class TasksDoneView(View):

    @method_decorator(permission_required(perm='auth.admin', raise_exception=True))
    def get(self, request, project_id):

        try:
            p = Project.objects.get(id=project_id)

            tasks = p.task_set.all().filter(status='DONE').order_by('date_finished')

            x = []
            y = []

            for t in tasks:

                dc = t.date_created.strftime("%Y/%m/%dT%H:00:00")

                if len(x) != 0 and x[-1] == dc:
                    y[-1] += 1
                    continue

                x.append(dc)
                y.append(1)

            return JsonResponse({"labels": x, "data": y}, status=200, safe=False)
        except Exception as e:
            return JsonResponse({"message": "Bad request"}, status=400)


class TasksDoneByUser(View):

    @method_decorator(permission_required(perm='auth.admin', raise_exception=True))
    def get(self, request, project_id, user_id):

        try:
            p = Project.objects.get(id=project_id)
            u = User.objects.get(id=user_id)

            tasks = p.task_set.all().filter(status='DONE').filter(assigned=u).order_by('date_finished')

            x = []
            y = []

            for t in tasks:

                dc = t.date_created.strftime("%Y/%m/%dT%H:00:00")

                if len(x) != 0 and x[-1] == dc:
                    y[-1] += 1
                    continue

                x.append(dc)
                y.append(1)

            return JsonResponse({"labels": x, "data": y}, status=200, safe=False)
        except Exception as e:
            return JsonResponse({"message": "Bad request"}, status=400)