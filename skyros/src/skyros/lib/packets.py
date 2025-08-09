#!/usr/bin/env python3
import struct
from dataclasses import dataclass
from enum import IntEnum

# Packet constants
PACKET_PREAMBLE = 0xAA55  # correct value for little-endian format
MAX_PAYLOAD_SIZE = 128

# Packet header format
HEADER_FORMAT = (
    "<HBBB"  # little-endian: uint16 (preamble), uint8 (size), uint8 (type), uint8 (network_id)
)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


# Packet types
class PacketType(IntEnum):
    TELEMETRY = 1
    COMMAND = 2
    STATUS = 3
    SENSOR_DATA = 4
    CONFIG = 5
    BULK_DATA = 6
    PING = 7
    ACK = 8
    CUSTOM_MESSAGE = 9


# Packet formats (without header and CRC)
TELEMETRY_FORMAT = "<Bffffff"  # little-endian: uint8, 6 floats (x, y, z, vx, vy, vz)
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_FORMAT) + 2  # +2 for CRC

COMMAND_FORMAT = "<BBH"  # command_id, target_id, param
COMMAND_SIZE = struct.calcsize(COMMAND_FORMAT) + 2  # +2 for CRC

STATUS_FORMAT = "<BBHH"  # drone_id, status_code, battery_mv, error_flags
STATUS_SIZE = struct.calcsize(STATUS_FORMAT) + 2  # +2 for CRC

SENSOR_FORMAT = "<Bfff"  # sensor_id, value1, value2, value3
SENSOR_SIZE = struct.calcsize(SENSOR_FORMAT) + 2  # +2 for CRC

CONFIG_FORMAT = "<BBB"  # network_id, wifi_channel, tx_power
CONFIG_SIZE = struct.calcsize(CONFIG_FORMAT) + 2  # +2 for CRC

PING_FORMAT = "<I"  # timestamp
PING_SIZE = struct.calcsize(PING_FORMAT) + 2  # +2 for CRC

ACK_FORMAT = "<BBH"  # ack_type, ack_id, status
ACK_SIZE = struct.calcsize(ACK_FORMAT) + 2  # +2 for CRC

CUSTOM_MESSAGE_FORMAT = "<126s"  # 126 bytes of custom data
CUSTOM_MESSAGE_SIZE = struct.calcsize(CUSTOM_MESSAGE_FORMAT) + 2  # +2 for CRC


@dataclass
class PacketHeader:
    preamble: int
    payload_size: int
    packet_type: int
    network_id: int


@dataclass
class TelemetryPacket:
    header: PacketHeader
    drone_id: int
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    crc: int


@dataclass
class CommandPacket:
    header: PacketHeader
    command_id: int
    target_id: int
    param: int
    crc: int


@dataclass
class StatusPacket:
    header: PacketHeader
    drone_id: int
    status_code: int
    battery_mv: int
    error_flags: int
    crc: int


@dataclass
class SensorPacket:
    header: PacketHeader
    sensor_id: int
    value1: float
    value2: float
    value3: float
    crc: int


@dataclass
class ConfigPacket:
    header: PacketHeader
    network_id: int
    wifi_channel: int
    tx_power: int
    crc: int


@dataclass
class PingPacket:
    header: PacketHeader
    timestamp: int
    crc: int


@dataclass
class AckPacket:
    header: PacketHeader
    ack_type: int
    ack_id: int
    status: int
    crc: int


@dataclass
class CustomMessagePacket:
    header: PacketHeader
    custom_data: bytes
    crc: int
