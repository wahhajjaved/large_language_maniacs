from django.http import HttpResponseServerError
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework import status
from xcapp.models import Runner, Team, Meet, RunnerMeet, Coach
from .runner_meet import RunnerMeetSerializer
# from .coach import CoachSerializer

class RunnerTeamSerializer(serializers.HyperlinkedModelSerializer):
    """
    Author: Scott Silver
    Purpose: JSON serializer for teams to convert native Python datatypes to
    be rendered into JSON
    Arguments:
        serializers.HyperlinkedModelSerializer
    """

    class Meta:
        model = Team
        url = serializers.HyperlinkedIdentityField(
            view_name='team',
            lookup_field='id'
        )
        fields = ('id', 'team_name')
        depth = 2

class MeetSerializer(serializers.HyperlinkedModelSerializer):
    """
    Author: Scott Silver
    Purpose: JSON serializer for orders to convert native Python datatypes to
    be rendered into JSON
    Arguments:
        serializers.HyperlinkedModelSerializer
    """
    class Meta:
        model = Meet
        url = serializers.HyperlinkedIdentityField(
            view_name='meet',
            lookup_field='id'
        )
        fields = ('id', 'name')

class RunnerMeetSerializer(serializers.HyperlinkedModelSerializer):
    """
    Author: Scott Silver
    Purpose: JSON serializer for orders to convert native Python datatypes to
    be rendered into JSON
    Arguments:
        serializers.HyperlinkedModelSerializer
    """
    meet = MeetSerializer(many=False)

    class Meta:
        model = RunnerMeet
        url = serializers.HyperlinkedIdentityField(
            view_name='meet',
            lookup_field='id'
        )
        fields = ('id', 'url', 'meet')
        depth = 1

class RunnerSerializer(serializers.HyperlinkedModelSerializer):
    """JSON serializer for runners

    Arguments:
        serializers
    """
    team = RunnerTeamSerializer(many=False)
    runnermeet = RunnerMeetSerializer(many=True)
    # coach = CoachSerializer(many=True)

    class Meta:
        model = Runner
        url = serializers.HyperlinkedIdentityField(
            view_name='runner',
            lookup_field='id'
        )
        fields = ('id', 'url', 'grade', 'first_name', 'last_name', 'phone',
        'email', 'address', 'parent', 'team', 'runnermeet', 'roster')
        depth = 2


class Runners(ViewSet):

    """Runners for xcapp
    Author: Scott Silver
    Purpose: Handle logic for operations performed on the Runner model to manage client requests for runners.
    database to GET, PUT, POST, and DELETE entries.
    Methods: GET, PUT, POST, DELETE
    """

    def create(self, request):

        """Handle POST operations

        Returns:
            Response -- JSON serialized Runner instance
        """
        newrunner = Runner()
        newrunner.grade = request.data["grade"]
        newrunner.first_name = request.data["first_name"]
        newrunner.last_name = request.data["last_name"]
        newrunner.phone = request.data["phone"]
        newrunner.email = request.data["email"]
        newrunner.address = request.data["address"]
        newrunner.parent = request.data["parent"]
        newrunner.team = Team.objects.get(pk=request.data["team"])
        newrunner.save()

        serializer = RunnerSerializer(newrunner, context={'request': request})

        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Handle GET requests for single runner

        Returns:
            Response -- JSON serialized runner instance
        """
        try:
            runner = Runner.objects.get(pk=pk)
            serializer = RunnerSerializer(runner, context={'request': request})
            return Response(serializer.data)
        except Exception as ex:
            return HttpResponseServerError(ex)

    def update(self, request, pk=None):
        """Handle PUT requests for a park area

        Returns:
            Response -- Empty body with 204 status code
        """
        runner= Runner.objects.get(pk=pk)
        runner.grade = request.data["grade"]
        runner.phone = request.data["phone"]
        runner.email = request.data["email"]
        runner.address = request.data["address"]
        runner.team = Team.objects.get(pk=request.data["team"])
        runner.save()

        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, pk=None):
        """Handle DELETE requests for a single runner

        Returns:
            Response -- 200, 404, or 500 status code
        """
        try:
            runner = Runner.objects.get(pk=pk)
            runner.delete()

            return Response({}, status=status.HTTP_204_NO_CONTENT)

        except Runner.DoesNotExist as ex:
            return Response({'message': ex.args[0]}, status=status.HTTP_404_NOT_FOUND)

        except Exception as ex:
            return Response({'message': ex.args[0]}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request):
        """Handle GET requests to runners resource

        Returns:
            Response -- JSON serialized list of runners
        """
        # objects.all() is an abstraction that the Object Relational Mapper
        # (ORM) in Django provides that queries the table holding
        # all the meets, and returns every row.
        coach = Coach.objects.get(pk=request.auth.user.id)
        runners = Runner.objects.filter(team__coach=coach)

        teams = self.request.query_params.get('team', None)

        if teams is not None:
            runners = Runner.objects.filter(runner_team__id = teams)


        serializer = RunnerSerializer(
            runners, many=True, context={'request': request})

        return Response(serializer.data)

