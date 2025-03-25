import argparse
import asyncio
import operator
import subprocess
from functools import reduce

from tqdm import tqdm

from .cases import *
from .fors import Recorder
from .parser import TestParser


class TestMacro:

    def __init__(self):
        self._lock = False
        self._cases = []
        self._exes = []
        self._for = []
        self._file_templates = [
            (MacroYAML, ('yaml', 'yml', )),
        ]
        self._for_templates = {
            'record': Recorder.fromCase,
        }
        self._exit_code = 0

    @property
    def exitCode(self):
        return self._exit_code

    def load(self, filename: str):
        try:
            data = MacroYAML(self._lock, filename, dump=False)._data
        except FileNotFoundError as e:
            print(e)
            self._exit(1)
            return False
        parser = TestParser()
        if 'cases' in data.keys():
            for c in data['files']:
                filename, cases = next(iter(c.items()))
                c = self.addFile(filename)  # TODO addCase
                for values in cases:
                    key, values = next(iter(values.items()))
                    c.addCase(key, parser.parse(values))
        if 'for' in data.keys():
            for f in data['for']:
                command, args = next(iter(f.items()))
                if not isinstance(args, list) and not isinstance(args, dict):
                    args = [args]
                self._for.append((self._for_templates[command], args))
        if 'exes' in data.keys():
            for cmd in data['exes']:
                self.addExec(cmd)
        return True
                

    def addFile(self, filename: str, filetype: str = None):
        assert not self._lock, 'Appending while computing is not allowed'
        filetype = (filetype or filename.split('.')[-1]).lower()
        for cls, cases in self._file_templates:
            if filetype in cases:
                case = cls(self._check_lock, filename)
                self._cases.append(case)
                return case
        raise NotImplementedError(f'Unsupported format: {filetype}')

    def addFor(self, function, args):
        self._for.append((function, args))

    def addExec(self, command: str):
        # TODO arguments
        self._exes.append(command)

    def addFileTemplate(self, cls: MacroCase, *cases):
        self._file_templates.append(cls, cases)

    def addForTemplate(self, command: str, builder):
        self._for_templates[command] = builder

    def _check_lock(self):
        return self._lock

    def _init(self):
        for c in self._cases:
            c._init()

    def _step(self):
        for c in self._cases:
            if not c._step():
                return False
        return True

    def _dump(self):
        if not len(self._cases):
            return []
        return reduce(operator.add, [c._dump() for c in self._cases])

    async def iterate(self):
        self._lock = True
        self._init()

        row = self.__row__()
        # TODO simplification
        if len(self._cases) == 1:
            row = [r.split('.')[-1] for r in row]
        row = [r[-10:] for r in row]
        print(('{:>12s}' * len(row)).format(*row))

        # TODO more pretty
        with tqdm(total=len(self)) as pbar:
            on_error = True
            while True:
                case = self._dump() 
                pbar.set_description(''.join(
                    '{:>12s}'.format(c[1][-10:]) if isinstance(c[1], str)
                    else '{:>12g}'.format(c[1])
                    for c in case
                ))
                # for
                for _fun, _args in self._for:
                    await _fun(case)(*_args)
                # exec
                for _cmd in self._exes:
                    if await self._execute(_cmd):
                        on_error = True
                        break
                if on_error:
                    break
                yield case
                # update
                await asyncio.sleep(0.1)
                pbar.update()
                if self._step():
                    break
        self._lock = False

    async def _execute(self, command: str):
        # spawn process
        try:
            process = subprocess.Popen(command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except FileNotFoundError as e:
            print(f'\n{e}')
            self._exit(1)
            return True
        # await
        while True:
            retcode = process.poll()
            if retcode is not None:
                break
            else:
                await asyncio.sleep(0.01)
                continue
        # (output, err) = process.communicate()
        exit_code = process.wait()
        if exit_code != 0:
            self._exit(exit_code)
            return True
        return False

    def _exit(self, exit_code: int):
        self._lock = False
        self._exit_code = int(exit_code)

    def __row__(self):
        if not len(self._cases):
            return []
        return reduce(operator.add, [c.__row__() for c in self._cases])

    def __len__(self):
        if not len(self._cases):
            return 0
        return reduce(operator.mul, [len(c) for c in self._cases])


async def _main(macro, loop, filepath: str):
    if macro.load(filepath):
        async for _ in macro.iterate():
            pass
    loop.stop()


def main():
    parser = argparse.ArgumentParser(description='Simple fully automatic macro.')
    parser.add_argument('-p', metavar='PATH', type=str, default='case.yml',
                        help='a yaml file containing test cases')
    args = parser.parse_args()

    macro = TestMacro()

    loop = asyncio.get_event_loop()
    asyncio.ensure_future(_main(macro, loop, args.p))
    loop.run_forever()

    exit(macro.exitCode)
