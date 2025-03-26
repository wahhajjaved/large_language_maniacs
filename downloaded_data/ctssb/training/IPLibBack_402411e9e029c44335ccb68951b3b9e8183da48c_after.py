from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse, Http404
from websocket import create_connection
from rest_framework_jwt.settings import api_settings
import json

from . import models
from . import serializers
from django.contrib.auth.models import User
from .models import Book
from .book import BookRepository
from django.shortcuts import get_object_or_404

class BookView(APIView):
    def get(self, request):
        books = Book.objects.all()
        serializer = serializers.BookSerializer(books, many=True)
        return Response({"books": serializer.data})

    def post(self, request):
        book = request.data
        serializer = serializers.BookSerializer(data=book)
        if serializer.is_valid(raise_exception=True):
            book_saved = serializer.save()
        return Response({"success": "Book '{}' create successfully".format(book_saved.model)})
    def put(self, request, pk):
        saved_book = get_object_or_404(models.Book.objects.all(), pk=pk)
        data = request.data
        serializer = serializers.BookSerializer(instance=saved_book, data=data, partial=True)
        if serializer.is_valid(raise_exception=True):
            book_saved = serializer.save()
        return Response({"success": "Book '{}' update successfully".format(book_saved.model)})
    def delete(self, request, pk):
        book = get_object_or_404(models.Book.objects.all(), pk=pk)
        book.delete()
        return Response({"message": "Book with id `{}` has been deleted.".format(pk)}, status=204)


class AuthorViewSet(generics.ListCreateAPIView):
    permission_classes = [AllowAny]
    queryset = models.Author.objects.all()
    serializer_class = serializers.AuthorSerializer

class BookViewSet(generics.ListCreateAPIView):
    permission_classes = [AllowAny]
    queryset = models.Book.objects.all()
    serializer_class = serializers.BookSerializer

    def get_queryset(self):
        querystring = self.request.query_params.get('q')

        if querystring is not None:
            return BookRepository.search(querystring)

        return Book.objects.all()

    def perform_create(self, serializer):
        print(self.request.data)
        serializer.save(author_id=self.request.data['author_id'])

    def perform_update(self, serializer):
        serializer.save(author_id=self.request.data['author_id'])


    def get(self, request, *args, **kwargs):
        web_socket(self)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        web_socket(self)
        return response

class UserList(generics.ListCreateAPIView):
    permission_classes = [AllowAny]
    queryset = User.objects.all()
    serializer_class = serializers.UserSerializer


class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [AllowAny]
    queryset = User.objects.all()
    serializer_class = serializers.UserSerializer 

class FileUploadView(APIView):
    permission_classes = [AllowAny]
    parser_class = (FileUploadParser,)

    def post(self, request, *args, **kwargs):

      file_serializer = serializers.FileSerializer(data=request.data)

      if file_serializer.is_valid():
          file_serializer.save()
          return Response(file_serializer.data, status=status.HTTP_201_CREATED)
      else:
          return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OauthVK(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = User.objects.create_user(email, email, User.objects.make_random_password())

        jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
        jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER

        payload = jwt_payload_handler(user)
        token = jwt_encode_handler(payload)

        return Response(data=jwt_response_payload_handler(token, user), status=status.HTTP_200_OK,)

class VkHook(APIView):
    queryset = models.Author.objects.all()
    permission_classes = [AllowAny]

    def post(self, request):
        if request.data.get('type') == "confirmation" and request.data.get("group_id") == 188767688:
            return HttpResponse('39b629c7')

        label = request.data.get('object').get('body').split('\n')
        if label[0] == "create":
            author = {"first_name": label[0], "last_name": label[1],"middle_name": label[2],}        
            serializer = serializers.AuthorSerializer(data=author)

            if serializer.is_valid(raise_exception=True):
                autor_saved = serializer.save()

            ws = create_connection("wss://iplibwebsocket.herokuapp.com/")
            ws.send(json.dumps({
                "messageType": "vkHook",
                "data": request.data
            }))
            ws.close()

            ws = create_connection("wss://iplibwebsocket.herokuapp.com/")
            ws.send(json.dumps({
                "messageType": "data",
                "authors": serializers.AuthorSerializer(models.Author.objects.all(), many=True).data
            }))
            ws.close()
        elif label[0] == "delete":
            id = int(label[1])
            qs = self.get_queryset().get(pk=id).delete()

            ws = create_connection("wss://iplibwebsocket.herokuapp.com/")
            ws.send(json.dumps({
                "messageType": "data",
                "authors": serializers.AuthorSerializer(models.Author.objects.all(), many=True).data
            }))
            ws.close()

        return HttpResponse('ok', content_type="text/plain", status=200)

def web_socket(self):
    ws = create_connection("wss://iplibwebsocket.herokuapp.com/")
    ws.send(json.dumps({
        "messageType": "data",
        "books": serializers.BookSerializer(self.get_queryset(), many=True).data
    }))
    ws.close()