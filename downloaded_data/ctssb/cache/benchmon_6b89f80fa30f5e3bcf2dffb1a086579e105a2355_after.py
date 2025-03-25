# coding: UTF-8

import argparse
import asyncio
import glob
import logging
import signal
import sys
from itertools import chain
from pathlib import Path
from typing import Tuple

from bench_toolbox.benchmark import LaunchableBenchmark
from bench_toolbox.configs.containers import PerfConfig, RabbitMQConfig
from bench_toolbox.configs.parser import Parser
from bench_toolbox.configs.parsers import BenchParser, PerfParser, RabbitMQParser
from bench_toolbox.monitors import PerfMonitor, PowerMonitor, RDTSCMonitor, ResCtrlMonitor, RuntimeMonitor
from bench_toolbox.monitors.messages.handlers import RabbitMQHandler
from bench_toolbox.utils.hyperthreading import hyper_threading_guard
from .benchmark.constraints.rabbit_mq import RabbitMQConstraint
from .monitors.messages.handlers.hybrid_iso_merger import HybridIsoMerger

MIN_PYTHON = (3, 7)


async def launch(workspace: Path,
                 silent: bool,
                 print_metric_log: bool,
                 verbose: bool) -> bool:
    parser = Parser(PerfParser(), RabbitMQParser(), BenchParser()) \
        .set_local_cfg(workspace / 'config.json')
    perf_config: PerfConfig = parser.parse('perf')
    rabbit_mq_config: RabbitMQConfig = parser.parse('rabbit_mq')

    benches: Tuple[LaunchableBenchmark, ...] = tuple(
            LaunchableBenchmark
                .Builder(bench_cfg, workspace, logging.DEBUG if verbose else logging.INFO)
                .build_constraint(RabbitMQConstraint.Builder(rabbit_mq_config))
                .build_monitor(RDTSCMonitor.Builder(perf_config.interval))
                .build_monitor(ResCtrlMonitor.Builder(perf_config.interval))
                .build_monitor(PerfMonitor.Builder(perf_config))
                .build_monitor(RuntimeMonitor.Builder())
                .build_monitor(PowerMonitor.Builder())
                .add_handler(HybridIsoMerger())
                # .add_handler(PrintHandler())
                .add_handler(RabbitMQHandler(rabbit_mq_config))
                .finalize()
            for bench_cfg in parser.parse('bench')
    )

    current_tasks: Tuple[asyncio.Task, ...] = tuple()
    is_cancelled: bool = False

    def cancel_current_tasks() -> None:
        nonlocal current_tasks, is_cancelled
        is_cancelled = True
        for t in current_tasks:  # type: asyncio.Task
            t.cancel()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, cancel_current_tasks)

    async with hyper_threading_guard(False):
        current_tasks = tuple(asyncio.create_task(bench.start_and_pause(silent)) for bench in benches)
        await asyncio.wait(current_tasks)

        if not is_cancelled:
            for bench in benches:
                bench.resume()

            await asyncio.sleep(0.1)

            current_tasks = tuple(asyncio.create_task(bench.monitor()) for bench in benches)
            await asyncio.wait(current_tasks)

    loop.remove_signal_handler(signal.SIGINT)

    return not is_cancelled


async def main() -> None:
    if sys.version_info < MIN_PYTHON:
        sys.exit('Python {}.{} or later is required.\n'.format(*MIN_PYTHON))

    parser = argparse.ArgumentParser(description='Launch benchmark written in config file.')
    parser.add_argument('config_dir', metavar='PARENT_DIR_OF_CONFIG_FILE', type=str, nargs='+',
                        help='Directory path where the config file (config.json) exist. (support wildcard *)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Print more detail log')
    parser.add_argument('-S', '--silent', action='store_true', help='Do not print any log to stdin. (override -M)')
    parser.add_argument('-M', '--print-metric-log', action='store_true',
                        help='Print all metric related logs to stdout.')
    parser.add_argument('--expt-interval', type=int, default=10, help='interval (sec) to sleep between each experiment')

    args = parser.parse_args()

    dirs: chain[str] = chain(*(glob.glob(path) for path in args.config_dir))

    silent: bool = args.silent
    print_metric_log: bool = args.print_metric_log
    verbose: bool = args.verbose
    interval: int = args.expt_interval

    for i, workspace in enumerate(dirs):
        if i is not 0:
            await asyncio.sleep(interval)

        if not await launch(Path(workspace), silent, print_metric_log and silent, verbose and not silent):
            break
