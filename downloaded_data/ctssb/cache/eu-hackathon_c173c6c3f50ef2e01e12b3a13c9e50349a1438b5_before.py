from django.db import models

def get_random_object_from_queryset(queryset):
    return queryset.order_by('?').first()


class AxisManager(models.Manager):

    def get_random_axis(self, languages=[]):
        axis = get_random_object_from_queryset(self)
        rejected = []
        while axis.is_fully_qualified and axis.has_contributor_for_languages(languages):
            rejected.append(axis.pk)
            axis = get_random_object_from_queryset(self.exclude(pk__in=rejected))
        return axis


class ContributorManager(models.Manager):

    def get_random_contributor(self, languages=[]):
        from .models import Contributor
        return self.filter(
            status__lt=Contributor.STATUS_QUALIFIED,
            language_code__in=languages
        ).order_by('?').first()
