"""
Codehub Article API endpoints
Pavlo Kovalov 2019
"""
import datetime

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from articles.models import Article
from articles.permissions import ArticlePermission
from articles.serializers import ArticleSerializer, ListArticleSerializer, MyArticlesListSerializer
from articles.tools import get_preview, get_reading_time
from articles.utils import ArticlePaginator


class ArticlesViewSet(viewsets.ModelViewSet):
    permission_classes = [ArticlePermission]
    serializer_class = ArticleSerializer
    pagination_class = ArticlePaginator

    def get_queryset(self):
        qs = Article.objects.filter(published=True)
        if self.action == 'my' or self.action == 'retrieve':
            qs = qs | Article.objects.filter(author=self.request.user)
        return qs

    def perform_create(self, serializer):
        text = serializer.validated_data['text']
        serializer.save(author=self.request.user, preview=get_preview(text),
                        estimate_reading_time=get_reading_time(text))

    def get_serializer_class(self, *args, **kwargs):
        if self.action == 'list':
            return ListArticleSerializer
        if self.action == 'my':
            return MyArticlesListSerializer
        return super().get_serializer_class()

    @action(methods=['GET'], detail=False, permission_classes=[IsAuthenticated])
    def my(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @action(methods=['GET'], detail=False)
    def recent(self, request, *args, **kwargs):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        qs = self.get_queryset()
        qs = qs.filter(date_created__gt=yesterday).order_by('views')[:5]
        return Response(ListArticleSerializer(qs, many=True).data)
