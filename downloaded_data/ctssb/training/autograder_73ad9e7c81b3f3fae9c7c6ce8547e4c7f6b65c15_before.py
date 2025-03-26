import autograder as _autograder
import shutil as _shutil
import os.path as _path
import json as _json
import traceback as _traceback

from .meta import CopyToSourceDir
from .template import WriteTemplate

def find_command(*args, path=None):
    for arg in args:
        result = _shutil.which(arg, path)
        if result is not None:
            return result
    raise RuntimeError('Couldn\'t find any of commands {}'.format(args))

class Subprocess(_autograder.Action):
    def __init__(self, name, command, timeout=None):
        self.name = name
        self.command = command
        self.timeout = timeout
    def perform(self, data, work_dir):
        command = find_command(self.command[0], path=work_dir) + self.command[1:]
        result = {
            'operation': ' '.join(command),
            'output': '',
            'return_code': None,
            'success': False,
        }
        data[self.name] = result
        try:
            output = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=work_dir,
                timeout=self.timeout)
            result['return_code'] = 0
            result['output'] = output
            result['success'] = True
            return True
        except subprocess.CalledProcessError as e:
            result['return_code'] = e.returnCode
        except FileNotFoundError:
            result['output'] = 'File not found: {}'.format(command[0])
        except subprocess.TimeoutExpired:
            result['output'] = 'Timed out after: {}'.format(self.timeout)
        except Exception:
            result['output'] = _traceback.format_exc()
        return False

class Make(_autograder.Action):
    def __init__(self, target):
        self._proc = Subprocess(
            name='make_'+target,
            command=[find_command('make'), target])
    def perform(self, data, work_dir):
        return self._proc.perform(data, work_dir)

class CompileCXX(_autograder.Action):
    def __init__(self, filename):
        basename, _ = _path.splitext(filename)
        self._proc = Subprocess(
            name='compilecxx_'+target,
            command=[find_command('g++', 'clang++')] + '-c -Wall -g --std=c++11'.split(' ') + [filename, '-o', basename+'.o'])
    def perform(self, data, work_dir):
        return self._proc.perform(data, work_dir)

class LinkCXX(_autograder.Action):
    def __init__(self, program, objects, libraries=[]):
        basename, _ = _path.splitext(filename)
        self._proc = Subprocess(
            name='linkcxx_'+target,
            command=[find_command('g++', 'clang++')] + '-Wall -g --std=c++11'.split(' ') + objects + ['-o', program])
    def perform(self, data, work_dir):
        return self._proc.perform(data, work_dir)

class ReadFile(_autograder.Action):
    def __init__(self, filename):
        self.filename = filename
    def perform(self, data, work_dir):
        path = _path.join(work_dir, self.filename)
        results = {
            'success': False,
            'operation': 'read {}'.format(path),
        }
        try:
            with open(_path.join(work_dir, self.filename)) as f:
                contents = f.read()
                data[self.filename] = contents
                results['success'] = True
                results['output'] = contents
                data['read_'+self.filename] = results
                return True
        except Exception:
            results['output'] = _traceback.format_exc()
            data['read_'+self.filename] = results
            return False

class ReadJSON(_autograder.Action):
    def __init__(self, filename):
        self.filename = filename
    def perform(self, data, work_dir):
        path = _path.join(work_dir, self.filename)
        results = {
            'success': False,
            'operation': 'read {}'.format(path),
        }
        try:
            with open(_path.join(work_dir, self.filename)) as f:
                js = _json.load(f)
                data[self.filename] = js
                results['success'] = True
                results['output'] = str(js)
                data['read_'+self.filename] = results
                return True
        except Exception:
            results['output'] = _traceback.format_exc()
            data['read_'+self.filename] = results
            return False

class WriteJSON(_autograder.Action):
    def __init__(self, filename):
        self.filename = filename
    def perform(self, data, work_dir):
        path = _path.join(work_dir, self.filename)
        results = {
            'success': False,
            'operation': 'write {}'.format(path),
        }
        try:
            with open(_path.join(work_dir, self.filename), 'w') as f:
                _json.dump(f, data[self.filename])
                results['success'] = True
                results['output'] = str(data[self.filename])
                data['write_'+self.filename] = results
                return True
        except Exception:
            results['output'] = _traceback.format_exc()
            data['write_'+self.filename] = results
            return False

class CalculateGrade(_autograder.Action):
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn
    def perform(self, data, work_dir):
        results = {
            'success': False,
            'operation': 'calculate grade {}'.format(self.name),
        }
        try:
            o = self.fn(data)
            data.setdefault('grades', {})[self.name] = o
            results['success'] = True
            results['output'] = str(o)
            data['calculate_grade_{}'.format(self.name)] = results
            return True
        except Exception:
            results['output'] = _traceback.format_exc()
            data['calculate_grade_{}'.format(self.name)] = results
            return False

class Call(_autograder.Action):
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn
    def perform(self, data, work_dir):
        results = {
            'success': False,
            'operation': 'call {}'.format(self.name),
        }
        try:
            self.fn(data)
            results['success'] = True
            results['output'] = ''
            data['{}'.format(self.name)] = results
            return True
        except Exception:
            results['output'] = _traceback.format_exc()
            data['{}'.format(self.name)] = results
            return False
