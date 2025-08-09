#!/usr/bin/env python3
import threading
import time

from .packets import PacketType


class InterfaceStats:
    def __init__(self):
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_corrupted = 0
        self.bytes_sent = 0
        self.bytes_received = 0

        # Statistics by packet type
        self.packets_sent_by_type = {ptype: 0 for ptype in PacketType}
        self.packets_received_by_type = {ptype: 0 for ptype in PacketType}
        self.bytes_sent_by_type = {ptype: 0 for ptype in PacketType}
        self.bytes_received_by_type = {ptype: 0 for ptype in PacketType}


class Statistics:
    def __init__(self):
        self.uart = InterfaceStats()
        self.espnow = InterfaceStats()
        self.start_time = time.time()
        self.last_stats_time = self.start_time
        self.lock = threading.Lock()

    # Legacy properties for backward compatibility
    @property
    def packets_sent(self):
        return self.uart.packets_sent

    @property
    def packets_received(self):
        return self.uart.packets_received

    @property
    def packets_corrupted(self):
        return self.uart.packets_corrupted

    @property
    def bytes_sent(self):
        return self.uart.bytes_sent

    @property
    def bytes_received(self):
        return self.uart.bytes_received

    @property
    def packets_sent_by_type(self):
        return self.uart.packets_sent_by_type

    @property
    def packets_received_by_type(self):
        return self.uart.packets_received_by_type

    @property
    def bytes_sent_by_type(self):
        return self.uart.bytes_sent_by_type

    @property
    def bytes_received_by_type(self):
        return self.uart.bytes_received_by_type
