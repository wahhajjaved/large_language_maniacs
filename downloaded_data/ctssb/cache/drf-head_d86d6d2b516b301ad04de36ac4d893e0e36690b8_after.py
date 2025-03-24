from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from theapp import models
from six.moves.urllib.parse import urlparse

class ModelTest(TestCase):
	def setUp(self):
		self.client = APIClient()
	def tearDown(self):
		pass
	
	def test_model_head1(self):
		model = models.Model.objects.create(name="model1")
		url = reverse('model-detail', args=('model1',))
		response = self.client.head(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
