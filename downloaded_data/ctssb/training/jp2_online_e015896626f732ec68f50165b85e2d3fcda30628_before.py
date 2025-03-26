from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.forms import ValidationError
from familias.models import Familia, Integrante, Alumno
from administracion.models import Escuela
from perfiles_usuario.models import Capturista
from perfiles_usuario.utils import ADMINISTRADOR_GROUP
from .forms import DeleteEstudioForm, RecoverEstudioForm
from .models import Estudio


class RecoverDeleteFormsTest(TestCase):
    """
    Suite to test the forms to Delete and Recover studies.

    Attributes
    ----------
    elerik : User
        User that will be used as a capturista in order to fill all everything
        related with familia.
    familia1 : Familia
        Used in tests that depend on creating an object related to a familia.
    estudio1 : Estudio
        Used in test for changing it's status, to eliminado.
    integrante1 : Integrante
        Used in tests to check it becomes inactive.
    integrante2 : Integrante
        Used in tests to check it becomes inactive.
    alumno1 : Alumno
        Used in tests to check if it becomes inactive.
    escuela : Used in tests that depend on creating an object related to an escuela
    capturista : Capturista
        Asociated with the User, as this object is required for permissions and
        creation.
    """

    def setUp(self):
        """ This sets up the database with the necessary values for the testing of the
        DeleteEstudioForm
        """
        self.elerik = User.objects.create_user(
            username='erikiano',
            email='latelma@junipero.sas',
            password='vacalalo',
            first_name='erik',
            last_name='suapellido')

        self.escuela = Escuela.objects.create(nombre='Juan Pablo')

        self.capturista = Capturista.objects.create(user=self.elerik)

        numero_hijos_inicial = 3
        estado_civil_inicial = 'soltero'
        localidad_inicial = 'salitre'
        self.familia1 = Familia.objects.create(numero_hijos_diferentes_papas=numero_hijos_inicial,
                                               estado_civil=estado_civil_inicial,
                                               localidad=localidad_inicial)

        self.estudio1 = Estudio.objects.create(capturista=self.capturista,
                                               familia=self.familia1)

        self.integrante1 = Integrante.objects.create(familia=self.familia1,
                                                     nombres='Rick',
                                                     apellidos='Astley',
                                                     nivel_estudios='doctorado',
                                                     fecha_de_nacimiento='1996-02-26')

        self.integrante2 = Integrante.objects.create(familia=self.familia1,
                                                     nombres='Rick',
                                                     apellidos='Astley',
                                                     nivel_estudios='doctorado',
                                                     fecha_de_nacimiento='1996-02-26')

        self.alumno1 = Alumno.objects.create(integrante=self.integrante2,
                                             numero_sae='5876',
                                             escuela=self.escuela)

    def test_delete_estudio_capturista(self):
        """ This tests that the save method of the form, changes the status
        of the estudio, as well as the activo value of all related 'people'.
        The user deleting in this case is a capturista.
        """
        form_data = {'id_estudio': self.estudio1.id}
        form = DeleteEstudioForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save(user_id=self.capturista.pk)
        estudio = Estudio.objects.get(pk=self.estudio1.pk)
        self.assertEqual(estudio.status, Estudio.ELIMINADO_CAPTURISTA)
        integrante = Integrante.objects.get(pk=self.integrante1.pk)
        self.assertEqual(integrante.activo, False)
        integrante = Integrante.objects.get(pk=self.integrante2.pk)
        self.assertEqual(integrante.activo, False)
        alumno = Alumno.objects.get(pk=self.alumno1.pk)
        self.assertEqual(alumno.activo, False)

    def test_delete_estudio_admin(self):
        """ This tests that the save method of the form, changes the status
        of the estudio, as well as the activo value of all related 'people'.
        The user deleting in this case is an administrative.
        """
        administrators = Group.objects.get_or_create(name=ADMINISTRADOR_GROUP)[0]
        administrators.user_set.add(self.elerik)
        administrators.save()

        form_data = {'id_estudio': self.estudio1.id}
        form = DeleteEstudioForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save(user_id=self.capturista.user.pk)
        estudio = Estudio.objects.get(pk=self.estudio1.pk)
        self.assertEqual(estudio.status, Estudio.ELIMINADO_ADMIN)
        integrante = Integrante.objects.get(pk=self.integrante1.pk)
        self.assertEqual(integrante.activo, False)
        integrante = Integrante.objects.get(pk=self.integrante2.pk)
        self.assertEqual(integrante.activo, False)
        alumno = Alumno.objects.get(pk=self.alumno1.pk)
        self.assertEqual(alumno.activo, False)

    def test_recover_study_valid_data(self):
        """ Test that the form is valid provided valid data.

        """
        self.estudio1.status = Estudio.ELIMINADO_CAPTURISTA
        self.estudio1.save()
        form = RecoverEstudioForm({'id_estudio': self.estudio1.pk})
        self.assertTrue(form.is_valid())

    def test_recover_study_valid_data2(self):
        """ Test that the form is valid.

        """
        self.estudio1.status = Estudio.ELIMINADO_ADMIN
        self.estudio1.save()
        form = RecoverEstudioForm({'id_estudio': self.estudio1.pk})
        self.assertTrue(form.is_valid())

    def test_recover_study_invalid(self):
        """ Test the form is invalid if study does not exist.

        """
        form = RecoverEstudioForm({'id_estudio': -1})
        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):
            form.clean()

    def test_recover_study_invalid2(self):
        """ Test the form is invalid if the study is not deleted.

        We check with a study that has all status except
        deleted by admin and capturista.
        """
        opts = Estudio.get_options_status()
        for s in filter(lambda x: 'eliminado' not in x, opts.values()):
            self.estudio1.status = s
            self.estudio1.save()
            form = RecoverEstudioForm({'id_estudio': self.estudio1.pk})
            self.assertFalse(form.is_valid())
            with self.assertRaises(ValidationError):
                form.clean()

    def test_recover_deleted_admin(self):
        """ Test that the form correctly updates the status of a deleted
        study by an admin, and changes the members from inactive to active.
        """
        self.estudio1.status = Estudio.ELIMINADO_ADMIN
        self.estudio1.save()
        self.integrante1.activo = False
        self.integrante1.save()
        self.integrante2.activo = False
        self.integrante2.save()
        self.alumno1.activo = False
        self.alumno1.save()

        form = RecoverEstudioForm({'id_estudio': self.estudio1.pk})
        self.assertTrue(form.is_valid())
        form.save()
        estudio = Estudio.objects.get(pk=self.estudio1.pk)
        self.assertEqual(estudio.status, Estudio.APROBADO)

        integrante1 = Integrante.objects.get(pk=self.integrante1.pk)
        self.assertTrue(integrante1.activo)
        integrante2 = Integrante.objects.get(pk=self.integrante2.pk)
        self.assertTrue(integrante2.activo)
        self.assertTrue(integrante2.alumno_integrante.activo)

    def test_recover_deleted_capturista(self):
        """ Test that the form correctly updates the status of a deleted
        study by a capturista, and changes the members from inactive to active.
        """
        self.estudio1.status = Estudio.ELIMINADO_CAPTURISTA
        self.estudio1.save()
        self.integrante1.activo = False
        self.integrante1.save()
        self.integrante2.activo = False
        self.integrante2.save()
        self.alumno1.activo = False
        self.alumno1.save()

        form = RecoverEstudioForm({'id_estudio': self.estudio1.pk})
        self.assertTrue(form.is_valid())
        form.save()
        estudio = Estudio.objects.get(pk=self.estudio1.pk)
        self.assertEqual(estudio.status, Estudio.BORRADOR)

        integrante1 = Integrante.objects.get(pk=self.integrante1.pk)
        self.assertTrue(integrante1.activo)
        integrante2 = Integrante.objects.get(pk=self.integrante2.pk)
        self.assertTrue(integrante2.activo)
        self.assertTrue(integrante2.alumno_integrante.activo)
