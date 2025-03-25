from __future__ import absolute_import
from unittest import TestCase
import os
import shutil
from lando.testutil import write_temp_return_filename
from lando.worker.config import WorkerConfig
from lando.worker.worker import LandoWorker
from lando_messaging.messaging import StageJobPayload, RunJobPayload, StoreJobOutputPayload
from mock import patch, MagicMock

LANDO_WORKER_CONFIG = """
host: 10.109.253.74
username: worker
password: workerpass
queue_name: task-queue
"""

class Report(object):
    """
    Builds a text document of steps executed by Lando.
    This makes it easier to assert what operations happened.
    """
    def __init__(self):
        self.text = ''

    def add(self, line):
        self.text += line + '\n'


class FakeSettings(object):
    def __init__(self, config):
        self.config = config
        self.report = Report()
        self.raise_when_run_workflow = False

    def make_lando_client(self, config, outgoing_queue_name):
        return FakeObject("Lando Client", self.report)

    def make_staging_context(self, credentials):
        return FakeObject("Staging Context", self.report)

    def make_download_duke_ds_file(self, file_id, destination_path, user_id):
        return FakeObject("Download file {}.".format(file_id), self.report)

    def make_download_url_file(self, url, destination_path):
        return FakeObject("Download url {}.".format(url), self.report)

    def make_cwl_workflow(self, job_id, working_directory, output_directory, cwl_base_command):
        if self.raise_when_run_workflow:
            raise ValueError("Something went wrong.")
        obj = FakeObject("Run workflow for job {}.".format(job_id), self.report)
        obj.run = obj.run_workflow
        return obj

    def make_upload_duke_ds_folder(self, project_id, source_directory, dest_directory, user_id):
        return FakeObject("Upload folder to DukeDS project: {} dir:{}.".format(project_id, dest_directory), self.report)

class FakeObject(object):
    def __init__(self, run_message, report):
        self.run_message = run_message
        self.report = report

    def job_step_complete(self, payload):
        self.report.add("Send job step complete for job {}.".format(payload.job_id))

    def run(self, context):
        self.report.add(self.run_message)

    def run_workflow(self, cwl_file_url, workflow_object_name, input_json):
        self.report.add(self.run_message)

    def job_step_error(self, payload, message):
        self.report.add("Send job step error for job {}: {}.".format(payload.job_id, message))

    def worker_started(self, queue_name):
        self.report.add("Send worker started message for {}.".format(queue_name))


class FakeInputFile(object):
    def __init__(self, file_type):
        self.file_type = file_type
        self.workflow_name = 'workflow'
        self.dds_files = []
        self.url_files = []
        if file_type == 'dds_file':
            self.dds_files.append(FakeFileData())
        else:
            self.url_files.append(FakeFileData())


class FakeFileData(object):
    def __init__(self):
        self.file_id = 42
        self.user_id = 2
        self.url = 'http:stuff'
        self.destination_path = 'data.txt'


class FakeWorkflow(object):
    def __init__(self):
        self.url = "file:///tmp/test.cwl"
        self.job_order = "{'id':1}"
        self.output_directory = None
        self.object_name = "#main"


class FakeOutputDirectory(object):
    def __init__(self):
        self.dir_name = 'results'
        self.project_id = 1234
        self.dds_user_credentials = 8


class TestLandoWorker(TestCase):
    def _make_worker(self):
        config_filename = write_temp_return_filename(LANDO_WORKER_CONFIG)
        config = WorkerConfig(config_filename)
        self.settings = FakeSettings(config)
        worker = LandoWorker(self.settings, outgoing_queue_name="test")
        return worker

    def test_stage_job(self):
        worker = self._make_worker()
        input_files = [
            FakeInputFile('dds_file'),
            FakeInputFile('url_file')

        ]
        worker.stage_job(StageJobPayload(credentials=None, job_id=1, input_files=input_files, vm_instance_name='test1'))
        report = """
Download file 42.
Download url http:stuff.
Send job step complete for job 1.
        """
        self.assertMultiLineEqual(report.strip(), self.settings.report.text.strip())

    def test_run_job(self):
        worker = self._make_worker()
        workflow = FakeWorkflow()
        worker.run_job(RunJobPayload(job_id=2, workflow=workflow, vm_instance_name='test2'))
        report = """
Run workflow for job 2.
Send job step complete for job 2.
        """
        self.assertMultiLineEqual(report.strip(), self.settings.report.text.strip())

    def test_run_job_raises(self):
        worker = self._make_worker()
        self.settings.raise_when_run_workflow = True
        workflow = FakeWorkflow()
        worker.run_job(RunJobPayload(job_id=2, workflow=workflow, vm_instance_name='test2'))
        result = self.settings.report.text.strip()
        self.assertIn("Send job step error for job 2", result)
        self.assertIn("ValueError: Something went wrong.", result)

    def test_save_output(self):
        worker = self._make_worker()
        outdir = FakeOutputDirectory()
        worker.store_job_output(StoreJobOutputPayload(credentials=None, job_id=3, output_directory=outdir,
                                                      vm_instance_name='test3'))
        report = """
Upload folder to DukeDS project: 1234 dir:results.
Send job step complete for job 3.
        """
        self.assertMultiLineEqual(report.strip(), self.settings.report.text.strip())

    def test_stage_job_creates_working_directory(self):
        worker = self._make_worker()
        input_files = [
            FakeInputFile('dds_file'),
            FakeInputFile('url_file')

        ]
        working_dir = "data_for_job_1"
        if os.path.exists(working_dir):
            shutil.rmtree(working_dir)
        worker.stage_job(StageJobPayload(credentials=None, job_id=1, input_files=input_files, vm_instance_name='test1'))
        self.assertEqual(True, os.path.exists(working_dir))

    @patch('lando.worker.worker.MessageRouter')
    def test_worker_sends_worker_started(self, MockMessageRouter):
        settings = MagicMock()
        worker = LandoWorker(settings, outgoing_queue_name='stuff')
        worker.listen_for_messages()
        settings.make_lando_client.return_value.worker_started.assert_called()
