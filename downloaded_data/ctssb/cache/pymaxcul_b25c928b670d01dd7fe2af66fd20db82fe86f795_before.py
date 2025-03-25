# -*- coding: utf-8 -*-
"""
    maxcul.communication
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    There are two communication classes available which should run in their own thread.
    CULComThread performs low-level serial communication, CULMessageThread performs high-level
    communication and spawns a CULComThread for its low-level needs.

    Generally just use CULMessageThread unless you have a good reason not to.

    :copyright: (c) 2014 by Markus Ullmann.
    :license: BSD, see LICENSE for more details.
"""

# environment constants

# python imports
from datetime import datetime
import queue
import threading
import time

# environment imports
import logging

# custom imports
from maxcul._exceptions import MoritzError
from maxcul._messages import (
    MoritzMessage,
    PairPingMessage, PairPongMessage,
    TimeInformationMessage,
    SetTemperatureMessage,
    ThermostatStateMessage,
    AckMessage,
    ShutterContactStateMessage,
    WallThermostatStateMessage,
    WallThermostatControlMessage,
    WakeUpMessage
)
from maxcul._io import CulIoThread
from maxcul._const import (
    EVENT_DEVICE_PAIRED, EVENT_DEVICE_REPAIRED, EVENT_THERMOSTAT_UPDATE,
    ATTR_DEVICE_ID, ATTR_DESIRED_TEMPERATURE, ATTR_MEASURED_TEMPERATURE,
    ATTR_MODE, ATTR_BATTERY_LOW
)

# local constants
LOGGER = logging.getLogger(__name__)

# Hardcodings based on FHEM recommendations
DEFAULT_CUBE_ID = 0x123456

DEFAULT_DEVICE = '/dev/ttyUSB0'
DEFAULT_BAUDRATE = '38400'
DEFAULT_PAIRING_TIMOUT = 30

BACKOFF_INTERVAL = 5
MAX_ATTEMPTS = 5


class MaxConnection(threading.Thread):
    """High level message processing"""

    def __init__(
            self,
            device_path=DEFAULT_DEVICE,
            baudrate=DEFAULT_BAUDRATE,
            sender_id=DEFAULT_CUBE_ID,
            callback=None,
            paired_devices=None):
        super().__init__()
        self.sender_id = sender_id
        self.com_thread = CulIoThread(device_path, baudrate)
        self.stop_requested = threading.Event()
        self._pairing_enabled = threading.Event()
        self._paired_devices = paired_devices or []
        self._outstanding_acks = {}
        self.callback = callback
        self._msg_count = 0

    def run(self):
        self.com_thread.start()
        while not self.stop_requested.is_set():
            self._receive_message()
            self._resend_message()
            time.sleep(0.3)

    def stop(self, timeout=None):
        LOGGER.info("Stopping MAXCUL")
        self.com_thread.stop(timeout)
        self.stop_requested.set()
        self.join(timeout)

    def enable_pairing(self, duration=DEFAULT_PAIRING_TIMOUT):
        LOGGER.info("Enable pairing for %d seconds", duration)
        self._pairing_enabled.set()

        def clear_pair():
            self._pairing_enabled.clear()
        threading.Timer(duration, clear_pair).start()

    def set_temperature(self, receiver_id, temperature, mode):
        LOGGER.debug(
            "Setting temperature for %d to %d %s",
            receiver_id, temperature, mode)
        msg = SetTemperatureMessage(
            counter=self._next_counter(),
            sender_id=self.sender_id,
            receiver_id=receiver_id,
            desired_temperature=float(temperature),
            mode=mode
        )
        if self._send_message(msg):
            self._await_ack(msg)

    def wakeup(self, receiver_id):
        LOGGER.debug("Waking device %d", receiver_id)
        msg = WakeUpMessage(
            counter=self._next_counter(),
            receiver_id=receiver_id)
        if self._send_message(msg):
            self._await_ack(msg)

    def _next_counter(self):
        self._msg_count += 1
        return self._msg_count

    def _receive_message(self):
        try:
            received_msg = self.com_thread.read_queue.get(True, 0.05)
            message = MoritzMessage.decode_message(received_msg[:-2])
            signal_strength = int(received_msg[-2:], base=16)
            self._handle_message(message, signal_strength)
        except queue.Empty:
            pass
        except Exception as err:
            LOGGER.error(
                "Exception <%s> was raised while parsing message '%s'. Please consider reporting this as a bug.",
                err,
                received_msg)

    def _send_message(self, msg):
        LOGGER.debug("Sending message %s", msg)
        try:
            raw_message = msg.encode_message()
            self.com_thread.enqueue_command(raw_message)
            return True
        except Exception as err:
            LOGGER.error(
                "Exception <%s> was raised while encoding message %s. Please consider reporting this as a bug.",
                err,
                msg)
            return False

    def _await_ack(self, msg):
        now = int(time.monotonic())
        self._outstanding_acks[msg.counter] = (now, 1, msg)

    def _resend_message(self):
        now = int(time.monotonic())
        for counter, (when, attempt, msg) in self._outstanding_acks.items():
            if when + BACKOFF_INTERVAL < now and attempt == MAX_ATTEMPTS:
                del self._outstanding_acks[counter]
                LOGGER.warn("Did not receive an ACK for message %s", msg)
                continue
            if when + BACKOFF_INTERVAL < now:
                self._send_message(msg)
                self._outstanding_acks[counter] = (now, attempt + 1, msg)

    def _send_ack(self, msg):
        ack_msg = msg.respond_with(
            AckMessage,
            counter=msg.counter,
            sender_id=self.sender_id)
        self._send_message(ack_msg)

    def _send_timeinformation(self, msg):
        resp_msg = msg.respond_with(
            TimeInformationMessage,
            counter=self._next_counter(),
            sender_id=self.sender_id,
            datetime=datetime.now()
        )
        self._send_message(resp_msg)

    def _send_pong(self, msg):
        resp_msg = msg.respond_with(
            PairPongMessage,
            counter=self._next_counter(),
            sender_id=self.sender_id,
            devicetype='Cube'
        )
        if self.com_thread.has_send_budget:
            if self._send_message(resp_msg):
                self._paired_devices.append(msg.sender_id)
                return True
            return False
        LOGGER.info(
            "NOT responding to pair send budget is insufficient to be on time")
        return False

    def _handle_message(self, msg, signal_strenth):
        """Internal function to respond to incoming messages where appropriate"""
        if msg.receiver_id != 0 and msg.receiver_id != self.sender_id:
            # discard messages not addressed to us
            return

        LOGGER.debug("Received message %s (%d)", msg, signal_strenth)

        if isinstance(msg, PairPingMessage):
            # Some peer wants to pair. Let's see...
            if msg.receiver_id == 0x0:
                # pairing after factory reset
                if not self._pairing_enabled.is_set():
                    LOGGER.info(
                        "Pairing requested but pairing disabled, not pairing to new device")
                    return
                if self._send_pong(msg):
                    self._call_callback(
                        EVENT_DEVICE_PAIRED, {
                            ATTR_DEVICE_ID: msg.sender_id})
            elif msg.receiver_id == self.sender_id:
                # pairing after battery replacement
                if self._send_pong(msg):
                    self._call_callback(
                        EVENT_DEVICE_REPAIRED, {
                            ATTR_DEVICE_ID: msg.sender_id})
            else:
                # pair to someone else after battery replacement, don't care
                LOGGER.debug(
                    "pair after battery replacement sent to other device 0x%X, ignoring",
                    msg.receiver_id)
            return

        if msg.receiver_id == 0 and msg.sender_id not in self._paired_devices:
            # discard broadcast messages from devices we are not paired with
            return

        if isinstance(msg, TimeInformationMessage):
            if not msg.datetime:
                # time information requested
                self._send_timeinformation(msg)

        elif isinstance(msg, ThermostatStateMessage):
            self._send_ack(msg)
            self._propagate_thermostat_change(msg)

        elif isinstance(msg, AckMessage):
            if msg.counter in self._outstanding_acks:
                del self._outstanding_acks[msg.counter]
            if msg.state == "ok":
                self._propagate_thermostat_change(msg)

        elif isinstance(msg, ShutterContactStateMessage, WallThermostatStateMessage, SetTemperatureMessage, WallThermostatControlMessage):
            self._send_ack(msg)

        else:
            LOGGER.warning(
                "Unhandled Message of type %s, contains %s",
                msg.__class__.__name__, msg)

    def _propagate_thermostat_change(self, msg):
        payload = {
            ATTR_DEVICE_ID: msg.sender_id,
            ATTR_MEASURED_TEMPERATURE: msg.measured_temperature,
            ATTR_DESIRED_TEMPERATURE: msg.desired_temperature,
            ATTR_MODE: msg.mode,
            ATTR_BATTERY_LOW: msg.battery_low

        }
        self._call_callback(EVENT_THERMOSTAT_UPDATE, payload)

    def _call_callback(self, event, payload):
        if self.callback:
            try:
                self.callback(event, payload)
            except Exception as err:
                LOGGER.warning(
                    "Error while calling callback for thermostat update: %s", err)
