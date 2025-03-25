from django.test import TestCase
from django.utils import timezone

from getresults_aliquot.models import Aliquot, AliquotType
from getresults_patient.models import Patient
from getresults_receive.models import Receive

from ..admin import AliquotAdmin
from ..filters import AliquotPatientFilter


class TestAliquotPaitentFilter(TestCase):

    def setUp(self):

        self.patient = Patient.objects.create(
            patient_identifier='P12345678',
            protocol='protocol_1',
            registration_datetime=timezone.now())

        self.receive = Receive.objects.create(
            receive_identifier='AA34567',
            patient=self.patient,
            receive_datetime=timezone.now())

        self.aliquot_type = AliquotType.objects.create(
            name='whole blood', alpha_code='WB', numeric_code='02')

    def test_aliquot_patient_filter(self):
        """Test if the queryset will filter by patient protocol."""
        Aliquot.objects.create(
            receive=self.receive,
            aliquot_identifier='AA3456700000201',
            aliquot_type=self.aliquot_type,
        )
        patient_filter = AliquotPatientFilter(
            None,
            {'receive__patient__protocol': self.receive.patient.protocol},
            Aliquot, AliquotAdmin
        )
        aliquot = patient_filter.queryset(None, Aliquot.objects.all())[0]
        self.assertEqual(aliquot.receive.patient.protocol, self.patient.protocol)
