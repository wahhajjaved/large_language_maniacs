from django.db import models
from django.utils import timezone

# Create your models here.
class FileInfo(models.Model):
	name = models.CharField(max_length=50,null=False)
	size = models.IntegerField(False)
	downloads = models.IntegerField(default=0)
	created_date = models.DateTimeField()
	md5 = models.CharField(max_length=32, null=False)
	user_ip = models.CharField(max_length=40, default='255.255.255.0')

class UserGPS(models.Model):
	username = models.CharField(max_length=50, null=True)
	user_ip = models.GenericIPAddressField(null=True)
	user_agent = models.CharField(max_length=300, null=True)
	lng = models.CharField(max_length=15, null=True)
	lat = models.CharField(max_length=15, null=True)
	address = models.CharField(max_length=200, null=True)
	code = models.CharField(max_length=50, null=True, blank=True)
	quota = models.IntegerField(null=True)
	use = models.IntegerField(null=True)
	create_date = models.DateTimeField(auto_now_add = True, null=True)
	create_by = models.CharField(max_length=50, null=True)

	def __str__(self):
		return u'%s - %s - %s' %(self.address, self.user_ip, code)

class Traffic(models.Model):
	# 我觉得可以做两张表格，一张登记有车车主的，
	# 上下班时间，行车路线，可搭载人员数；
	# 一张登记需要平车乘客的上下班时间，路线，
	# 可上下班站点等，这样让大家去看表格，
	# 自己联系拼车伙伴，要不然都在群里说，都记不住
	nick_name = models.CharField(verbose_name='昵称', max_length=20, null=True, blank=True)
	room_no = models.CharField(verbose_name=u'房号', max_length=10, null=True, blank=True)
	begin_time = models.CharField(verbose_name=u'上班时间', max_length=5, null=True, blank=True)
	end_time = models.CharField(verbose_name=u'下班时间', max_length=5, null=True, blank=True)
	route = models.CharField(verbose_name=u'行车路线', max_length=100, null=True, blank=True)
	available = models.IntegerField(verbose_name=u'可搭载人员数', null=True, blank=True)
	is_driver = models.NullBooleanField(verbose_name=u'是否为车主', null=True, blank=True)	
	mobile_no = models.CharField(verbose_name=u'联系电话', max_length=15, null=True, blank=True)
	is_open = models.NullBooleanField(verbose_name=u'是否公开', null=True, blank=True)
	user_ip = models.GenericIPAddressField(null=True)
	user_agent = models.CharField(max_length=200, null=True)
