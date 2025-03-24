from django.db import models

class Route(models.Model):
	date = models.DateField('route date')
	space = models.IntegerField(default=4)


	def __unicode__(self):
		return u'%s' % self.date.strftime("%d %b (%a)")



class Pasanger(models.Model):
	name = models.CharField(max_length=32)
	link = models.CharField(max_length=32)


	def __unicode__(self):
		return self.name



class Ticket(models.Model):
	pasanger = models.ForeignKey(Pasanger)
	route = models.ForeignKey(Route)
	is_return = models.BooleanField(default=False)

	def __unicode__(self):
		return "%s - %s" % (self.pasanger.name, self.route.date.strftime("%d %b (%a)"))
