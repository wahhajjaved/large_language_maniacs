import json
from django.http import HttpResponse
from vigilate_backend.settings import TESTING
from django.db import IntegrityError
from django.db.models import Q
from django.contrib.auth.models import User as UserDjango
from django.core.mail import send_mail
from rest_framework import viewsets, status
from rest_framework.decorators import list_route, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from pkg_resources import parse_version
from vigilate_backend.utils import get_query, parse_cpe
from vigilate_backend.models import User, UserPrograms, Alert, Station
from vigilate_backend.serializers import UserSerializer, UserProgramsSerializer, AlertSerializer, AlertSerializerDetail, StationSerializer
from vigilate_backend import alerts
from vulnerability_manager import cpe_updater

def home(request):
    """Vigilate root url content
    """
    text = """VIGILATE 1337"""
    return HttpResponse(text)

class UserViewSet(viewsets.ModelViewSet):
    """View for users
    """
    serializer_class = UserSerializer

    def get_permissions(self):
        """Allow non-authenticated user to create an account
        """

        if self.request.method == 'POST' and self.request.path == "/api/v1/users/":
            return (AllowAny(),)
        return [perm() for perm in self.permission_classes]

    def get_queryset(self):
        """Get the queryset depending on the user permission
        """
        if self.request.user.is_superuser:
            return User.objects.all()
        else:
            return User.objects.filter(id=self.request.user.id)

    def perform_create(self, serializer):
        new_user = serializer.save()

        send_mail(
            'Vigilate account created',
            'Hello, your vigilate account has just been created.\nYou can now connect to the website with your mail address and your password.',
            'vigilate_2017@epitech.eu',
            [new_user.email],
            fail_silently=True,
        )

class UserProgramsViewSet(viewsets.ModelViewSet):
    """View for users programs
    """

    serializer_class = UserProgramsSerializer

    def get_queryset(self):
        """Get the queryset depending on the user permission
        """
        if self.request.user.is_superuser:
            return UserPrograms.objects.all()
        else:
            return UserPrograms.objects.filter(user_id=self.request.user.id)

    def create(self, request):
        """Create one or multiple program at once
        """
        result = set()
        query = get_query(request)
        if not query:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        only_one_program = False
        if not "programs_list" in query:
            if not all(x in query for x in ['program_version', 'program_name', 'minimum_score']):
                return Response(status=status.HTTP_400_BAD_REQUEST)

            only_one_program = True
            elem = {}
            elem['program_version'] = query['program_version']
            elem['program_name'] = query['program_name']
            elem['program_score'] = query['minimum_score']
            query['programs_list'] = [elem]
            if UserPrograms.objects.filter(user_id=request.user.id, program_name=elem['program_name']).exists():
                ret = {"detail": "Program %s already exists" % elem['program_name']}
                return Response(ret, status=status.HTTP_400_BAD_REQUEST)

        for elem in query['programs_list']:
            if not all(x in elem for x in ['program_version', 'program_name']):
                return Response(status=status.HTTP_400_BAD_REQUEST)
        
        up_to_date = False
        if TESTING:
            up_to_date = True
        for elem in query['programs_list']:
            prog = UserPrograms.objects.filter(user_id=request.user.id, program_name=elem['program_name'], poste=query['poste'])

            # if prog , user is already monitoring the given program, update is needed
            if prog:
                
                prog = prog[0]
                prog_changed = False
                if prog.program_version != elem['program_version']:
                    prog_changed = True
                    prog.program_version = elem['program_version']
                    (cpe, up_to_date) = cpe_updater.get_cpe_from_name_version(elem['program_name'], elem['program_version'], up_to_date)
                    prog.cpe = cpe
                if 'minimum_score' in elem and prog.minimum_score != int(elem['minimum_score']):
                    prog_changed = True
                    prog.minimum_score = int(elem['minimum_score'])
                if prog_changed:
                    prog.save()
                    alerts.check_prog(prog, request.user)
            else:
                #else: add a new program

                (cpe, up_to_date) =  cpe_updater.get_cpe_from_name_version(elem['program_name'], elem['program_version'], up_to_date)

                new_prog = UserPrograms(user_id=request.user, minimum_score=1, poste=query['poste'],
                                        program_name=elem['program_name'], program_version=elem['program_version'], cpe=cpe)
                if 'minimum_score' in elem:
                    new_prog.minimum_score = int(elem['minimum_score'])

                new_prog.save()
                alerts.check_prog(new_prog, request.user)

            if only_one_program:
                obj = UserPrograms.objects.get(user_id=request.user.id, program_name=elem['program_name'], poste=query['poste'])
                serializer = self.get_serializer(obj)
                return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(status=status.HTTP_200_OK)


    def perform_update(self, serializer):
        instance = serializer.save()
        (cpe, _) = cpe_updater.get_cpe_from_name_version(instance.program_name, instance.program_version, True)
        instance.cpe = cpe
        instance.save(update_fields=["cpe"])
        alerts.check_prog(instance, self.request.user)


class AlertViewSet(viewsets.ModelViewSet):
    """View for alerts
    """
    serializer_class = AlertSerializer
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AlertSerializerDetail
        return self.serializer_class

    def get_queryset(self):
        """Get the queryset depending on the user permission
        """
        if self.request.user.is_superuser:
            return Alert.objects.all()
        else:
            return Alert.objects.filter(user_id=self.request.user.id)


class StationViewSet(viewsets.ModelViewSet):
    """View for station
    """
    serializer_class = StationSerializer
    
    def get_queryset(self):
        """Get the queryset depending on the user permission
        """
        if self.request.user.is_superuser:
            return Station.objects.all()
        else:
            return Station.objects.filter(user_id=self.request.user.id)
