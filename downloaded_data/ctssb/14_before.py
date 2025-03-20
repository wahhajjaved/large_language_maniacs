from dexy.reporter import Reporter
from jinja2 import FileSystemLoader
from jinja2 import Environment
import datetime
import os
import shutil

class RunReporter(Reporter):
    ALLREPORTS = True
    ALIASES = ['run']

    def run(self, wrapper):
        latest_report_dir = os.path.join(wrapper.log_dir, 'run-latest')

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
        report_dir = os.path.join(wrapper.log_dir, "run-%s" % timestamp)
        report_filename = os.path.join(report_dir, 'index.html')

        # Remove any existing directory (unlikely)
        shutil.rmtree(report_dir, ignore_errors=True)

        # Copy template files (e.g. .css files)
        template_dir = os.path.join(os.path.dirname(__file__), 'files')
        shutil.copytree(template_dir, report_dir)

        env_data = {}

        env_data['batch_id'] = wrapper.batch_id
        env_data['batch_info'] = wrapper.batch_info

        env = Environment()
        env.loader = FileSystemLoader(os.path.dirname(__file__))
        template = env.get_template('template.html')

        template.stream(env_data).dump(report_filename, encoding="utf-8")

        # Copy this to run-latest
        # TODO symlink instead?
        shutil.rmtree(latest_report_dir, ignore_errors=True)
        shutil.copytree(report_dir, latest_report_dir)
