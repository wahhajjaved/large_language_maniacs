from __future__ import unicode_literals

import django
from django.test import TestCase
from django.db import IntegrityError

from tests.models import Band, BandMember, Restaurant, Review, Album

# make sure that we're using the same unittest library that Django uses internally
try:
    # Firstly, try to import unittest from Django
    from django.utils import unittest
except ImportError:
    # Django doesn't include unittest
    # We must be running on Django 1.7+ which doesn't support Python 2.6 so
    # the standard unittest library should be unittest2
    import unittest

class ClusterTest(TestCase):
    def test_can_create_cluster(self):
        beatles = Band(name='The Beatles')

        self.assertEqual(0, beatles.members.count())

        beatles.members = [
            BandMember(name='John Lennon'),
            BandMember(name='Paul McCartney'),
        ]

        # we should be able to query this relation using (some) queryset methods
        self.assertEqual(2, beatles.members.count())
        self.assertEqual('John Lennon', beatles.members.all()[0].name)
        self.assertEqual('Paul McCartney', beatles.members.filter(name='Paul McCartney')[0].name)
        self.assertEqual('Paul McCartney', beatles.members.get(name='Paul McCartney').name)
        self.assertRaises(BandMember.DoesNotExist, lambda: beatles.members.get(name='Reginald Dwight'))
        self.assertRaises(BandMember.MultipleObjectsReturned, lambda: beatles.members.get())

        self.assertEqual([('Paul McCartney',)], beatles.members.filter(name='Paul McCartney').values_list('name'))
        self.assertEqual(['Paul McCartney'], beatles.members.filter(name='Paul McCartney').values_list('name', flat=True))
        # quick-and-dirty check that we can invoke values_list with empty args list
        beatles.members.filter(name='Paul McCartney').values_list()

        self.assertTrue(beatles.members.filter(name='Paul McCartney').exists())
        self.assertFalse(beatles.members.filter(name='Reginald Dwight').exists())

        self.assertEqual('John Lennon', beatles.members.first().name)
        self.assertEqual('Paul McCartney', beatles.members.last().name)

        self.assertTrue('John Lennon', beatles.members.order_by('name').first())
        self.assertTrue('Paul McCartney', beatles.members.order_by('-name').first())

        # these should not exist in the database yet
        self.assertFalse(Band.objects.filter(name='The Beatles').exists())
        self.assertFalse(BandMember.objects.filter(name='John Lennon').exists())

        beatles.save()
        # this should create database entries
        self.assertTrue(Band.objects.filter(name='The Beatles').exists())
        self.assertTrue(BandMember.objects.filter(name='John Lennon').exists())

        john_lennon = BandMember.objects.get(name='John Lennon')
        beatles.members = [john_lennon]
        # reassigning should take effect on the in-memory record
        self.assertEqual(1, beatles.members.count())
        # but not the database
        self.assertEqual(2, Band.objects.get(name='The Beatles').members.count())

        beatles.save()
        # now updated in the database
        self.assertEqual(1, Band.objects.get(name='The Beatles').members.count())
        self.assertEqual(1, BandMember.objects.filter(name='John Lennon').count())
        # removed member should be deleted from the db entirely
        self.assertEqual(0, BandMember.objects.filter(name='Paul McCartney').count())

        # queries on beatles.members should now revert to SQL
        self.assertTrue(beatles.members.extra(where=["tests_bandmember.name='John Lennon'"]).exists())

    def test_related_manager_assignment_ops(self):
        beatles = Band(name='The Beatles')
        john = BandMember(name='John Lennon')
        paul = BandMember(name='Paul McCartney')

        beatles.members.add(john)
        self.assertEqual(1, beatles.members.count())

        beatles.members.add(paul)
        self.assertEqual(2, beatles.members.count())
        # ensure that duplicates are filtered
        beatles.members.add(paul)
        self.assertEqual(2, beatles.members.count())

        beatles.members.remove(john)
        self.assertEqual(1, beatles.members.count())
        self.assertEqual(paul, beatles.members.all()[0])

        george = beatles.members.create(name='George Harrison')
        self.assertEqual(2, beatles.members.count())
        self.assertEqual('George Harrison', george.name)

    def test_can_pass_child_relations_as_constructor_kwargs(self):
        beatles = Band(name='The Beatles', members=[
            BandMember(name='John Lennon'),
            BandMember(name='Paul McCartney'),
        ])
        self.assertEqual(2, beatles.members.count())
        self.assertEqual(beatles, beatles.members.all()[0].band)

    def test_can_access_child_relations_of_superclass(self):
        fat_duck = Restaurant(name='The Fat Duck', serves_hot_dogs=False, reviews=[
            Review(author='Michael Winner', body='Rubbish.')
        ])
        self.assertEqual(1, fat_duck.reviews.count())
        self.assertEqual(fat_duck.reviews.first().author, 'Michael Winner')
        self.assertEqual(fat_duck, fat_duck.reviews.all()[0].place)

        fat_duck.save()
        # ensure relations have been saved to the database
        fat_duck = Restaurant.objects.get(id=fat_duck.id)
        self.assertEqual(1, fat_duck.reviews.count())
        self.assertEqual(fat_duck.reviews.first().author, 'Michael Winner')


    def test_can_only_commit_on_saved_parent(self):
        beatles = Band(name='The Beatles', members=[
            BandMember(name='John Lennon'),
            BandMember(name='Paul McCartney'),
        ])
        self.assertRaises(IntegrityError, lambda: beatles.members.commit())

        beatles.save()
        beatles.members.commit()

    def test_queryset_filtering(self):
        beatles = Band(name='The Beatles', members=[
            BandMember(id=1, name='John Lennon'),
            BandMember(id=2, name='Paul McCartney'),
        ])
        self.assertEqual('Paul McCartney', beatles.members.get(id=2).name)
        self.assertEqual('Paul McCartney', beatles.members.get(id='2').name)
        self.assertEqual(1, beatles.members.filter(name='Paul McCartney').count())

        # also need to be able to filter on foreign fields that return a model instance
        # rather than a simple python value
        self.assertEqual(2, beatles.members.filter(band=beatles).count())
        # and ensure that the comparison is not treating all unsaved instances as identical
        rutles = Band(name='The Rutles')
        self.assertEqual(0, beatles.members.filter(band=rutles).count())

        # and the comparison must be on the model instance's ID where available,
        # not by reference
        beatles.save()
        beatles.members.add(BandMember(id=3, name='George Harrison'))  # modify the relation so that we're not to a plain database-backed queryset

        also_beatles = Band.objects.get(id=beatles.id)
        self.assertEqual(3, beatles.members.filter(band=also_beatles).count())

    def test_queryset_exclude_filtering(self):
        beatles = Band(name='The Beatles', members=[
            BandMember(id=1, name='John Lennon'),
            BandMember(id=2, name='Paul McCartney'),
        ])

        self.assertEqual(1, beatles.members.exclude(name='Paul McCartney').count())
        self.assertEqual('John Lennon', beatles.members.exclude(name='Paul McCartney').first().name)

    def test_prefetch_related(self):
        Band.objects.create(name='The Beatles', members=[
            BandMember(id=1, name='John Lennon'),
            BandMember(id=2, name='Paul McCartney'),
        ])
        with self.assertNumQueries(2):
            lists = [list(band.members.all()) for band in Band.objects.prefetch_related('members')]
        normal_lists = [list(band.members.all()) for band in Band.objects.all()]
        self.assertEqual(lists, normal_lists)

    @unittest.skipIf(django.VERSION < (1, 7), "Custom querysets on prefetch_related are only available in Django 1.7 and later")
    def test_prefetch_related_with_custom_queryset(self):
        from django.db.models import Prefetch
        Band.objects.create(name='The Beatles', members=[
            BandMember(id=1, name='John Lennon'),
            BandMember(id=2, name='Paul McCartney'),
        ])
        with self.assertNumQueries(2):
            lists = [
                list(band.members.all())
                for band in Band.objects.prefetch_related(
                    Prefetch('members', queryset=BandMember.objects.filter(name__startswith='Paul'))
                )
            ]
        normal_lists = [list(band.members.filter(name__startswith='Paul')) for band in Band.objects.all()]
        self.assertEqual(lists, normal_lists)

    def test_order_by_with_multiple_fields(self):
        beatles = Band(name='The Beatles', albums=[
            Album(name='Please Please Me', sort_order=2),
            Album(name='With The Beatles', sort_order=1),
            Album(name='Abbey Road', sort_order=2),
        ])

        albums = [album.name for album in beatles.albums.order_by('sort_order', 'name')]
        self.assertEqual(['With The Beatles', 'Abbey Road', 'Please Please Me'], albums)

        albums = [album.name for album in beatles.albums.order_by('sort_order', '-name')]
        self.assertEqual(['With The Beatles', 'Please Please Me', 'Abbey Road'], albums)

    def test_meta_ordering(self):
        beatles = Band(name='The Beatles', albums=[
            Album(name='Please Please Me', sort_order=2),
            Album(name='With The Beatles', sort_order=1),
            Album(name='Abbey Road', sort_order=3),
        ])

        # in the absence of an explicit order_by clause, it should use the ordering as defined
        # in Album.Meta, which is 'sort_order'
        albums = [album.name for album in beatles.albums.all()]
        self.assertEqual(['With The Beatles', 'Please Please Me', 'Abbey Road'], albums)

    def test_parental_key_checks_clusterable_model(self):
        from django.core import checks
        from django.db import models
        from modelcluster.fields import ParentalKey

        class Instrument(models.Model):
            # Oops, BandMember is not a Clusterable model
            member = ParentalKey(BandMember)

            class Meta:
                # Prevent Django from thinking this is in the database
                # This shouldn't affect the test
                abstract = True

        # Check for error
        errors = Instrument.check()
        self.assertEqual(1, len(errors))

        # Check the error itself
        error = errors[0]
        self.assertIsInstance(error, checks.Error)
        self.assertEqual(error.id, 'modelcluster.E001')
        self.assertEqual(error.obj, Instrument.member.field)
        self.assertEqual(error.msg, 'ParentalKey must point to a subclass of ClusterableModel.')
        self.assertEqual(error.hint, 'Change tests.BandMember into a ClusterableModel or use a ForeignKey instead.')
