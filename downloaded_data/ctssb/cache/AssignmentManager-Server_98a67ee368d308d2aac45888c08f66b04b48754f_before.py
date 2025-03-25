from rest_framework import viewsets
from rest_framework.decorators import detail_route, list_route
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .serializers import TaskSerializer, TaskReadSerializer, CourseSerializer, MyUserSerializer, MyUserReadSerializer, VersionSerializer
from .models import Course, Task, MyUser, Version
from assignment.management.commands.update_grades import update_or_create_grades
from django.shortcuts import get_object_or_404
# Create your views here.


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TaskSerializer
        else:
            return TaskReadSerializer

    def get_queryset(self):
        if self.request.user.is_authenticated:
            q = self.request.query_params.get
            if q('course'):
                courses = Course.objects.filter(user=self.request.user.id, id=q('course'))
            else:
                courses = Course.objects.filter(user=self.request.user.id)
            return Task.objects.filter(course=courses, is_finished=False)
        else:
            return Task.objects.none()


class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.all()
    permission_classes = [IsAuthenticated, ]

    def get_queryset(self):
        request = self.request
        q = self.request.query_params.get
        queryset = Course.objects.filter(user=self.request.user.id)

        if q("cached"):
            update_or_create_grades(request.user)
        return queryset


class MyUserViewSet(viewsets.ModelViewSet):
    serializer_class = MyUserSerializer
    queryset = MyUser.objects.all()
    permission_classes = [IsAuthenticated, ]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MyUserSerializer
        else:
            return MyUserReadSerializer

    def get_queryset(self):
        return self.queryset.filter(id=self.request.user.id)


class VersionViewSet(viewsets.ModelViewSet):
    serializer_class = VersionSerializer
    queryset = Version.objects.all()
