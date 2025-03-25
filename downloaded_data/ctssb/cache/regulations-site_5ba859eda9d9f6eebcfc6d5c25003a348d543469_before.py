# vim: set fileencoding=utf-8
from mock import patch
from unittest import TestCase

from regulations.docket import sanitize_fields, Field


class SanitizeFieldsTest(TestCase):
    def setUp(self):
        self.patch_document_fields = patch(
            'regulations.docket.get_document_fields')
        mock_object = self.patch_document_fields.start()
        mock_object.return_value = {
            "required_field": Field(10, True),
            "optional_field": Field(10, False),
        }

    def tearDown(self):
        self.patch_document_fields.stop()

    def test_valid_body(self):
        test_body = {
            "required_field": "Value 1",
            "optional_field": "Value 2"
        }
        valid, message = sanitize_fields(test_body)
        self.assertTrue(valid)

    def test_missing_optional_field(self):
        test_body = {
            "required_field": "Value 1"
        }
        valid, message = sanitize_fields(test_body)
        self.assertTrue(valid)

    def test_missing_required_field(self):
        test_body = {
            "optional_field": "Some value"
        }
        valid, message = sanitize_fields(test_body)
        self.assertFalse(valid)
        self.assertEqual("Field required_field is required", message)

    def test_extra_field(self):
        test_body = {
            "required_field": "Value 1",
            "extra_field": "Value 2"
        }
        valid, message = sanitize_fields(test_body)
        self.assertTrue(valid)
        self.assertTrue("extra_field removed", "extra_field" not in test_body)

    def test_field_too_long(self):
        test_body = {
            "required_field": "Value that exceeds 10 chars",
        }
        valid, message = sanitize_fields(test_body)
        self.assertFalse(valid)
        self.assertEqual("Field required_field exceeds expected length of 10",
                         message)
