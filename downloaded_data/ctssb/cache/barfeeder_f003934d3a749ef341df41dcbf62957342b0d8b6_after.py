#!/usr/bin/env python
import i3ipc
import json
import logging
import math
import os
import signal
import time
from daemonize import Daemonize
from datetime import datetime
from optparse import OptionParser
from queue import Queue
from random import random
from subprocess import Popen, PIPE, DEVNULL
from threading import Thread, Event

colors = {
    "background": "#ff282828",
    "foreground": "#ffebdbb2",
    "cursor": "#fffff000",
    "light red": "#fffb4934",
    "dark red": "#ffcc241d",
    "light magenta": "#ffd3869b",
    "dark magenta": "#ffb16286",
    "light blue": "#ff83a598",
    "dark blue": "#ff458588",
    "light cyan": "#ff8ec07c",
    "dark cyan": "#ff689d6a",
    "light yellow": "#fffabd2f",
    "dark yellow": "#ffd79921",
    "light green": "#ffb8bb26",
    "dark green": "#ff98971a",
    "light white": "#fffbf1c7",
    "dark white": "#ffdbae93",
    "light black": "#ff665c54",
    "dark black": "#ff1d2021",
}
icons = {
    "battery": {
        "discharging": [
            "",
            "",
            "",
            "",
            "",
        ],
        "charging": ""
    },
    "date": "",
    "time": "",
    "cpu": "",
    "memory": "",
    "disk": "",
    "network": {
        "upspeed": "",
        "downspeed": "",
        "type": {
            "wireless": "",
            "wired": ""
        }
    },
    "temperature": "", # no icons yet :(
}

class StatusThread(Thread):
    def __init__(self, source_id, queue):
        super().__init__()
        self.id = source_id
        self.q = queue
        self._stopper = Event()
        self.logger = logging.getLogger("barfeeder.%s" % self.id)

    def stop_worker(self):
        self.logger.debug("Worker %s asked to stop" % self.id)
        self._stopper.set()

    def stopped(self):
        return self._stopper.isSet()


class DummyThread(StatusThread):
    """For test purposes"""
    def run(self):
        i = 0
        while True:
            if self.stopped():
                return
            self.q.put({ 
                "id": self.id,
                "output": i
            })
            time.sleep(0.5 + 0.5 * random())
            i += 1


class DateTimeThread(StatusThread):
    def __init__(self, source_id, queue,
            timeout=3):
        super().__init__(source_id, queue)
        self.timeout = timeout
        self.logger.info("Created DateTimeThread with source %s" % source_id)

    def format_output(self, current_date, current_time):
        return (
            "%%{B%s T2}   %s %%{T1} %s   "
            "%%{T2}%s  %%{T1}%s   %%{F- B-}"
        ) % (
            colors["light black"],
            icons["date"],
            current_date,
            icons["time"],
            current_time
        )

    def run(self):
        self.logger.info("Starting DateTimeThread with source %s" % self.id)
        previous_date = ""
        previous_time = ""
        while True:
            if self.stopped():
                return
            now = datetime.now()
            current_date = now.strftime('%d-%m-%Y')
            current_time = now.strftime('%H:%M')

            if previous_date != current_date or previous_time != current_time:
                self.q.put({
                    "id": self.id,
                    "output": self.format_output(current_date, current_time)
                })
            previous_date = current_date
            previous_time = current_time
            time.sleep(self.timeout)


class BatteryThread(StatusThread):
    def __init__(self, source_id, queue,
            timeout=3,
            sys_capa_file="/sys/class/power_supply/BAT0/capacity",
            sys_ac_file="/sys/class/power_supply/AC/online"):
        super().__init__(source_id, queue)
        self.timeout = timeout
        self.sys_capa_file = sys_capa_file
        self.sys_ac_file = sys_ac_file
        self.logger.info("Created BatteryThread with source %s" % source_id)

    def format_output(self, capacity, ac_status):
        if isinstance(capacity, str):
            capacity = int(capacity)
        capacity = min(capacity, 100)
        icon = ""
        fg_color = colors["foreground"]
        bg_color = colors["light black"]
        if ac_status == "1" or ac_status == "C":
            icon = icons["battery"]["charging"]
        else:
            index = math.floor(capacity * len(icons["battery"]["discharging"]) / 100 - 1)
            icon = icons["battery"]["discharging"][index]

        if capacity < 10:
            fg_color = colors["light red"]
            bg_color = colors["light red"]
        elif capacity < 25:
            fg_color = colors["light yellow"]
        elif capacity >= 98:
            fg_color = colors["light green"]

        return "%%{+u U%s B%s} %%{F%s T2} %s %%{T1}%s%%  %%{-u B-}" % (
            fg_color,
            bg_color,
            colors["foreground"],
            icon,
            capacity
        )

    def run(self):
        self.logger.info("Starting BatteryThread with source %s" % self.id)
        current_capa = ""
        previous_capa = ""
        current_ac = ""
        previous_ac = ""
        while True:
            if self.stopped():
                return
            with open(self.sys_capa_file, 'r') as f:
                current_capa = f.read().rstrip()

            with open(self.sys_ac_file, 'r') as f:
                current_ac = f.read().rstrip()

            if previous_capa != current_capa and previous_ac != current_ac:
                self.q.put({
                    "id": self.id,
                    "output": self.format_output(current_capa, current_ac)
                })
                previous_capa = current_capa
                previous_ac = current_ac
            time.sleep(self.timeout)


class I3Thread(StatusThread):
    def __init__(self, source_id, queue,
            timeout=1):
        super().__init__(source_id, queue)
        self.timeout = timeout
        self.setup_i3_connection()
        self.logger.info("Created I3Thread with source %s" % source_id)

    def quit(self):
        self.logger.debug("Quitting i3 ipc main loop")
        self.i3.main_quit()

    def stop_worker(self):
        self.logger.debug("Worker %s asked to stop" % self.id)
        self._stopper.set()
        self.quit()

    def setup_i3_connection(self):
        self.i3 = i3ipc.Connection()

        callback = lambda i3conn, event: self.on_ws_change(i3conn, event)
        self.i3.on('workspace::focus', callback)
        self.on_ws_change(self.i3, None)

    def get_state(self, workspace, event=None):
        if workspace.focused:
            if event is None or workspace.name == event.current.name:
                return "focused"
            else:
                return "active"
        if workspace.urgent:
            return "urgent"
        else:
            return "inactive"

    def on_ws_change(self, i3conn, event):
        out = "%%{F%s B%s T1}" % (
            colors["foreground"],
            colors["background"]
        )

        active_outputs = [
            output['name']
            for output in i3conn.get_outputs()
            if output['active']
        ]
        for ws in i3conn.get_workspaces():
            name = ws.name[1:]
            if not ws.output in active_outputs:
                continue
            state = self.get_state(ws, event)
            if state == "focused":
                out += "%%{+u B%s U%s T1}   %s   %%{-u B%s F%s}" %(
                    colors["light black"],
                    colors["light red"],
                    name,
                    colors["background"],
                    colors["foreground"]
                )
            else:
                out += "%%{F%s T1}   %s   %%{B- F-}" % (
                    colors["light black"],
                    name
                )

        self.q.put({
            "id": self.id,
            "output": out
        })

    def run(self):
        self.logger.info("Starting I3Thread with source %s" % self.id)
        self.i3.main()


class ConkyThread(StatusThread):
    def __init__(self, source_id, queue):
        super().__init__(source_id, queue)
        self.logger.info("Created ConkyThread with source %s" % source_id)

    def format_output(self, raw_output):
        elements = json.loads(raw_output)
        output = ""

        if "cpu" in elements:
            output += "%%{T2}  %s  %%{T1}%s%% %%{F- B-}" % (
                icons["cpu"],
                elements["cpu"]
            )

        if "memory" in elements:
            #output += "%%{F%s T3}  %%{T2}%s %s" % (
            output += "%%{T2}  %s  %%{T1}%s %%{F- B-}" % (
                icons["memory"],
                elements["memory"]
            )

        if "interfaces" in elements:
            for interface_name in elements["interfaces"]:
                intf = elements["interfaces"][interface_name]
                intf_type = "wired"
                if "status" in intf and intf["status"] == "up":
                    if "type" in intf and intf["type"] in icons["network"]["type"]:
                        intf_type = intf["type"]

                    additionnal_info = ""
                    if intf_type == "wireless" and "ssid" in intf and "quality" in intf:
                        additionnal_info = "%s %s%%" % (
                            intf["ssid"],
                            intf["quality"]
                        )
                    output += "%%{T2}  %s  %%{T1}%s %s %s %s %s %%{F- B-}" % (
                        icons["network"]["type"][intf_type],
                        additionnal_info,
                        icons["network"]["upspeed"],
                        intf["upspeed"],
                        icons["network"]["downspeed"],
                        intf["downspeed"]
                    )

        if "disks" in elements:
            for disk in elements["disks"]:
                output += "%%{T2}  %s  %%{T1}%s %s%% %%{F- B-}" % (
                    icons["disk"],
                    disk,
                    elements["disks"][disk]
                )
        if "temperature" in elements:
            for temp in elements["temperature"]:
                output += "%%{T2}  %s  %%{T1}%s %s°C %%{F- B-}" % (
                    icons["temperature"],
                    temp,
                    elements["temperature"][temp]
                )
        return output

    def run(self):
        self.logger.info("Starting ConkyThread with source %s" % self.id)
        conky_config = os.path.realpath(
            os.path.join(
                os.path.dirname(__file__),
                "conkyrc"
            )
        )
        with Popen(["conky", "-c", conky_config],
                   stdout=PIPE,
                   stderr=DEVNULL,
                   bufsize=1,
                   universal_newlines=True) as p:
            self.logger.info("ConkyThread[%s] started conky subprocess")
            for line in p.stdout:
                if self.stopped():
                    p.kill()
                    return
                self.q.put({
                    "id": self.id,
                    "output": self.format_output(line)
                })


status_queue = Queue()
source_threads = {
    "i3": I3Thread("i3", status_queue),
    "battery": BatteryThread("battery", status_queue),
    "datetime": DateTimeThread("datetime", status_queue),
    "conky": ConkyThread("conky", status_queue),
}
statuses = {
    "i3": "",
    "battery": "",
    "datetime": "",
    "conky": "",
}
lemonbar_cmd = [
    "lemonbar",
    "-p",
    "-f", "NotoSans-8",
    "-f", "FontAwesome-9",
    "-g", "x22",
    "-B", colors["background"],
    "-F", colors["foreground"],
    "-u", "3"
]
workers = []
stopping = False
daemon = None
logger = logging.getLogger('barfeeder')


def quit_handler(signum, frame):
    global stopping
    global status_queue

    stopping = True
    status_queue.empty()
    status_queue.put_nowait({})

    logger.critical("Received an interruption signal (%d)" % signum)
    logger.debug("Stopping all workers")
    for worker in workers:
        logger.debug("Stopping %s worker" % worker.id)
        worker.stop_worker()

    logger.debug("Joining all workers")
    for worker in workers:
        logger.debug("Joining %s worker" % worker.id)
        worker.join()
    logger.critical("Cleanly interrupted")

def start_workers():
    for source, worker in source_threads.items():
        logger.debug("Creating and running %s worker" % source)
        worker.setDaemon(True)
        worker.start()
        workers.append(worker)

    signal.signal(signal.SIGINT, quit_handler)
    signal.signal(signal.SIGTERM, quit_handler)

    with Popen(lemonbar_cmd,
               stdin=PIPE,
               stdout=DEVNULL,
               stderr=DEVNULL,
               bufsize=1,
               universal_newlines=True) as p:
        while True:
            obj = status_queue.get()
            if stopping:
                logger.debug("Stopping lemonbar")
                p.kill()
                return

            logger.debug("New status taken from the queue: %s" % obj)
            statuses[obj["id"]] = obj["output"]
            threads_output = (
                "%%{U%s l}%s "
                "%%{r}%s%s%s\n"
            ) % (
                colors["light red"],
                statuses["i3"],
                statuses["conky"],
                statuses["battery"],
                statuses["datetime"]
            )
            p.stdin.write(threads_output)
            status_queue.task_done()

def setup_logging(log_level, log_file, foreground):
    logger.setLevel(log_level)

    if foreground:
        formatter = logging.Formatter('%(levelname)-8s %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s %(levelname)-8s %(message)s',
            datefmt='%Y/%m/%d %H:%M:%S'
        )
        log_file_handler = logging.FileHandler(log_file, mode='w')
        log_file_handler.setLevel(logging.DEBUG)
        log_file_handler.setFormatter(formatter)

        logger.addHandler(log_file_handler)

def main():
    parser = OptionParser()
    parser.add_option("-F", "--foreground",
                      dest="foreground",
                      help="stay on foreground and print logging on stdout",
                      action="store_true",
                      default=False)
    parser.add_option("-d", "--debug",
                      dest="debug",
                      help="add debug information",
                      action="store_true",
                      default=False)
    (options, args) = parser.parse_args()

    log_level = logging.INFO

    if options.debug:
        log_level = logging.DEBUG

    root_dir = os.path.realpath(os.path.dirname(__file__))
    pid_file = os.path.join(root_dir, "barfeeder.pid")
    log_file = os.path.join(root_dir, "barfeeder.log")
    setup_logging(log_level, log_file, options.foreground)

    keep_fds = [ handler.stream.fileno() for handler in logger.handlers ]

    daemon = Daemonize(
        app="barfeeder",
        pid=pid_file,
        action=start_workers,
        keep_fds=keep_fds,
        logger=logger,
        verbose=options.debug,
        foreground=options.foreground,
        chdir=root_dir
    )
    daemon.start()

if __name__ == "__main__":
    main()
