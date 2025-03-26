import tempfile
import threading
import time
from datetime import datetime, timedelta

import pygen
from unittest_helper import BaseDockerTestCase


class UpdateTest(BaseDockerTestCase):
    app = None

    def setUp(self):
        super(UpdateTest, self).setUp()

        self.target_file = tempfile.NamedTemporaryFile()
        self.target_path = self.target_file.name

        self.count_signal_calls = 0

    def tearDown(self):
        super(UpdateTest, self).tearDown()

        self.target_file.close()

        if hasattr(self, 'app') and self.app:
            self.app.api.close()

    def read_contents(self):
        with open(self.target_path, 'r') as output_file:
            return output_file.read()

    def test_updates_target(self):
        self.app = pygen.PyGen(target=self.target_path,
                               interval=[0],
                               template="""#
            {% for container in containers %}
                __{{ container.name }}__
            {% endfor %}""")

        c1 = self.start_container()

        self.app.update_target()

        content = self.read_contents()

        self.assertIn('__%s__' % c1.name, content)

        c2 = self.start_container()

        self.app.update_target()

        content = self.read_contents()

        self.assertIn('__%s__' % c1.name, content)
        self.assertIn('__%s__' % c2.name, content)

        c1.stop()

        self.app.update_target()

        content = self.read_contents()

        self.assertNotIn('__%s__' % c1.name, content)
        self.assertIn('__%s__' % c2.name, content)

    def test_does_not_replace_unchanged_content(self):
        self.app = pygen.PyGen(target=self.target_path,
                               interval=[0],
                               template="""#
            {% for container in containers %}
                __{{ container.name }}__
            {% endfor %}""")

        original_signal_func = self.app.timer.function

        def counting_signal(*args, **kwargs):
            self.count_signal_calls += 1
            original_signal_func(*args, **kwargs)

        self.app.timer.function = counting_signal

        self.start_container()

        self.assertEqual(0, self.count_signal_calls)

        self.app.update_target()

        self.assertEqual(1, self.count_signal_calls)

        self.app.update_target()

        self.assertEqual(1, self.count_signal_calls)

        self.app.update_target()

        self.assertEqual(1, self.count_signal_calls)

    def test_watch(self):
        self.app = pygen.PyGen(target=self.target_path,
                               interval=[0],
                               template="""#
            {% for container in containers %}
                __{{ container.name }}__{{ container.health }}__
            {% endfor %}""")

        original_signal_func = self.app.timer.function

        def counting_signal(*args, **kwargs):
            self.count_signal_calls += 1
            original_signal_func(*args, **kwargs)

        self.app.timer.function = counting_signal

        self.assertEqual(0, self.count_signal_calls)

        def run(_flags):
            since = datetime.utcnow()

            while _flags['run']:
                until = datetime.utcnow() + timedelta(seconds=1)
                self.app.watch(since=since, until=until)

                since = until - timedelta(seconds=1)

        flags = {'run': True}
        try:
            thread = threading.Thread(target=run, args=(flags,))
            thread.start()

            self.assertEqual(0, self.count_signal_calls)

            c1 = self.start_container(healthcheck={
                'Test': ['CMD-SHELL', 'exit 0'],
                'Interval': 500000000
            })

            time.sleep(1.2)

            self.assertSignalHasCalled(times=2)  # start + healthy
            self.assertIn('__%s__' % c1.name, self.read_contents())

            c2 = self.start_container()

            time.sleep(1.2)

            self.assertSignalHasCalled(times=3)
            self.assertIn('__%s__' % c1.name, self.read_contents())
            self.assertIn('__%s__' % c2.name, self.read_contents())

            c1.stop()

            time.sleep(1.2)

            self.assertSignalHasCalled(times=4)
            self.assertNotIn('__%s__' % c1.name, self.read_contents())
            self.assertIn('__%s__' % c2.name, self.read_contents())

            flags['run'] = False
            thread.join()

            self.assertSignalHasCalled(times=4)

        except:
            flags['run'] = False
            raise

    def assertSignalHasCalled(self, times):
        for _ in range(10):
            if self.count_signal_calls >= times:
                break

            time.sleep(0.2)

        self.assertGreaterEqual(self.count_signal_calls, times)
