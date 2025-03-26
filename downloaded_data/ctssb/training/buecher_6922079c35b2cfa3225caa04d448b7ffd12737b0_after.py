# -*- coding: utf-8 -*-

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.template.defaultfilters import slugify
import os
import shutil

def get_ebook_path(instance, filename):
	name = instance.book.title if instance.book.authors.count() == 0 else u"%s - %s" % (instance.book.title, u", ".join([str(author) for author in instance.book.authors.all()]))
	name = slugify(name)
	return os.path.join('books', str(instance.book.id), name + os.path.splitext(filename)[1])

class Person(models.Model):
	firstname = models.TextField()
	lastname = models.TextField()

	def __str__(self):
		return u"%s %s" % (self.firstname, self.lastname)

	class Meta:
		ordering = ('lastname', 'firstname')
		unique_together = ('firstname', 'lastname')

class Publisher(models.Model):
	name = models.TextField(unique=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ('name',)

class Binding(models.Model):
	name = models.TextField(unique=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ('name',)

class Language(models.Model):
	name = models.TextField(unique=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ('name',)

class Series(models.Model):
	name = models.TextField(unique=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ('name',)

class Book(models.Model):
	updated_at = models.DateTimeField(auto_now=True)
	created_at = models.DateTimeField(auto_now_add=True)

	title = models.TextField()
	isbn = models.CharField(max_length=13, blank=True)
	asin = models.CharField(max_length=10, blank=True)
	price = models.FloatField(default=0)
	published_on = models.DateField(blank=True, null=True)
	purchased_on = models.DateField(blank=True, null=True)
	read_on = models.DateField(blank=True, null=True)

	cover_image = models.ImageField(upload_to='books', blank=True, null=True)

	binding = models.ForeignKey(Binding, blank=True, null=True)
	languages = models.ManyToManyField(Language, blank=True, null=True)
	authors = models.ManyToManyField(Person, blank=True, null=True)
	publisher = models.ForeignKey(Publisher, blank=True, null=True)

	series = models.ForeignKey(Series, blank=True, null=True)
	volume = models.FloatField(blank=True, null=True)

	def save(self):
		if self.id is None:
			super(Book, self).save()
			if self.cover_image.name:
				self.cover_image = self.get_image_path(self.cover_image)
				super(Book, self).save()
		else:
			super(Book, self).save()
			if self.cover_image.name:
				self.cover_image = self.get_image_path(self.cover_image)
				super(Book, self).save()

	def get_image_path(self, filename):
		save_name = os.path.join('books', str(self.id), 'cover.jpg')
		current_path = os.path.join(settings.MEDIA_ROOT, self.cover_image.path)
		new_path = os.path.join(settings.MEDIA_ROOT, save_name)

		if os.path.exists(current_path):
			if not os.path.exists(os.path.dirname(new_path)):
				os.makedirs(os.path.dirname(new_path))

			shutil.move(current_path, new_path)

		return save_name

	def get_absolute_url(self):
		return reverse('book', args=[self.id])

	def get_authors(self):
		return u", ".join([str(author) for author in self.authors.all()])

	def get_list_title(self, length):
		author = self.authors.first()
		if self.series:
			if len(str(self.series)) < (length / 4) + 1 or author == None:
				series = u" (" + str(self.series) + u" #%g)" % self.volume
			else:
				series = u" (" + str(self.series)[:int(length / 4)] + u"… #%g)" % self.volume
		else:
			series = u""

		if len(self.title) + (len(str(author)) + 4 if author != None else 0) + len(series) > length:
			return self.title[:length - (len(str(author)) - 5 if author != None else 0) - len(series) - 5] + ((u" by " + str(author)) if author != None else '') + series
		else:
			return self.title + ((u" by " + str(author)) if author != None else '') + series

	def __str__(self):
		base = self.title if self.authors.count() == 0 else u"%s - %s" % (self.title, u", ".join([str(author) for author in self.authors.all()]))
		base = base if not self.series else u"%s (%s #%g)" % (base, str(self.series), self.volume)
		return base

class EBookFile(models.Model):
	ebook_file = models.FileField(upload_to=get_ebook_path, max_length=4096)
	book = models.ForeignKey(Book)

	def filename(self):
		return os.path.basename(self.ebook_file.name)

	def __str__(self):
		return self.filename()

	class Meta:
		verbose_name = 'E-Book File'

class Url(models.Model):
	url = models.TextField()
	book = models.ForeignKey(Book)

	def __str__(self):
		return self.url