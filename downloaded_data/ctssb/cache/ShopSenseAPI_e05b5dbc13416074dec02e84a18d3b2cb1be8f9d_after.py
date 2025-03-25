import json

from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from Movies.models import Movie, Director, Genre
from Movies.serializers import UserSerializer


class UserList(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UserDetail(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class MovieView(APIView):
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    def get(self, request):
        movies = Movie.objects.all()
        l = []
        for movie in movies:
            each_movie = {}
            each_movie["name"] = movie.name
            each_movie["director"] = movie.director.name
            each_movie["imdb_score"] = movie.imdb_score
            each_movie["99popularity"] = movie.popularity
            genre_list = []
            print each_movie
            for genre in movie.genre.all():
                genre_list.append(genre.name)
            each_movie["genre"] = genre_list
            l.append(each_movie)
        return Response(l)

    def post(self, request):
        data = request.DATA
        m = Movie()
        m.name = data["name"]
        m.director, created = Director.objects.get_or_create(name=data["director"])
        m.imdb_score = data["imdb_score"]
        m.popularity = data["99popularity"]
        m.save()
        for genre in data["genre"]:
            genre = genre.strip(" ")
            g ,created = Genre.objects.get_or_create(name=genre)
            m.genre.add(g)
        return Response({'code':200})

