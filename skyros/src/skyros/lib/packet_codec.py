#!/usr/bin/env python3
import struct
from typing import Optional

from .packets import (
    ACK_SIZE,
    COMMAND_SIZE,
    CONFIG_SIZE,
    CUSTOM_MESSAGE_SIZE,
    HEADER_FORMAT,
    MAX_PAYLOAD_SIZE,
    PACKET_PREAMBLE,
    PING_SIZE,
    SENSOR_SIZE,
    STATUS_SIZE,
    TELEMETRY_FORMAT,
    TELEMETRY_SIZE,
    AckPacket,
    CommandPacket,
    ConfigPacket,
    CustomMessagePacket,
    PacketHeader,
    PacketType,
    PingPacket,
    SensorPacket,
    StatusPacket,
    TelemetryPacket,
)


def calculate_crc16(data: bytes) -> int:
    """Calculate CRC16 (matches ESP32)"""
    crc = 0xFFFF
    for byte in data[:-2]:  # Exclude CRC field
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def pack_packet(packet) -> bytes:
    """Universal packet packing into bytes"""
    # Pack header
    header = struct.pack(
        HEADER_FORMAT,
        packet.header.preamble,
        packet.header.payload_size,
        packet.header.packet_type,
        packet.header.network_id,
    )

    # Pack data based on type
    if isinstance(packet, TelemetryPacket):
        data = struct.pack("<Bffffff", packet.drone_id, packet.x, packet.y, packet.z, packet.vx, packet.vy, packet.vz)
    elif isinstance(packet, CommandPacket):
        data = struct.pack("<BBH", packet.command_id, packet.target_id, packet.param)
    elif isinstance(packet, StatusPacket):
        data = struct.pack(
            "<BBHH", packet.drone_id, packet.status_code, packet.battery_mv, packet.error_flags
        )
    elif isinstance(packet, SensorPacket):
        data = struct.pack("<Bfff", packet.sensor_id, packet.value1, packet.value2, packet.value3)
    elif isinstance(packet, ConfigPacket):
        data = struct.pack("<BBB", packet.network_id, packet.wifi_channel, packet.tx_power)
    elif isinstance(packet, PingPacket):
        data = struct.pack("<I", packet.timestamp)
    elif isinstance(packet, AckPacket):
        data = struct.pack("<BBH", packet.ack_type, packet.ack_id, packet.status)
    elif isinstance(packet, CustomMessagePacket):
        data = struct.pack("<126s", packet.custom_data)
    elif isinstance(packet, bytes):
        # For bulk packets that are already packed
        return packet
    else:
        raise ValueError(f"Unknown packet type: {type(packet)}")

    # Calculate CRC for the entire packet
    temp_packet = header + data + b"\x00\x00"
    crc = calculate_crc16(temp_packet)

    # Add CRC
    return header + data + struct.pack("<H", crc)


def unpack_header(data: bytes) -> Optional[PacketHeader]:
    """Unpack packet header"""
    try:
        preamble, payload_size, packet_type, network_id = struct.unpack(HEADER_FORMAT, data)
        if preamble != PACKET_PREAMBLE:
            return None
        if payload_size > MAX_PAYLOAD_SIZE:
            return None
        return PacketHeader(preamble, payload_size, packet_type, network_id)
    except struct.error:
        return None


def unpack_packet(header: PacketHeader, payload: bytes):
    """Universal packet unpacking from payload"""
    try:
        # Check CRC for all packet types
        if len(payload) < 2:
            return None

        received_crc = struct.unpack("<H", payload[-2:])[0]
        full_data = (
            struct.pack(
                HEADER_FORMAT,
                header.preamble,
                header.payload_size,
                header.packet_type,
                header.network_id,
            )
            + payload[:-2]
            + b"\x00\x00"
        )
        calculated_crc = calculate_crc16(full_data)

        if calculated_crc != received_crc:
            # Suppress frequent CRC error prints
            # print(f"CRC Error - Type: {header.packet_type}, Calculated: 0x{calculated_crc:04X}, Received: 0x{received_crc:04X}")
            return None

        # Unpack based on type
        if header.packet_type == PacketType.TELEMETRY:
            if header.payload_size != TELEMETRY_SIZE:
                return None
            drone_id, x, y, z, vx, vy, vz = struct.unpack(TELEMETRY_FORMAT, payload[:-2])
            return TelemetryPacket(header, drone_id, x, y, z, vx, vy, vz, received_crc)

        elif header.packet_type == PacketType.COMMAND:
            if header.payload_size != COMMAND_SIZE:
                return None
            command_id, target_id, param = struct.unpack("<BBH", payload[:-2])
            return CommandPacket(header, command_id, target_id, param, received_crc)

        elif header.packet_type == PacketType.STATUS:
            if header.payload_size != STATUS_SIZE:
                return None
            drone_id, status_code, battery_mv, error_flags = struct.unpack("<BBHH", payload[:-2])
            return StatusPacket(
                header, drone_id, status_code, battery_mv, error_flags, received_crc
            )

        elif header.packet_type == PacketType.SENSOR_DATA:
            if header.payload_size != SENSOR_SIZE:
                return None
            sensor_id, value1, value2, value3 = struct.unpack("<Bfff", payload[:-2])
            return SensorPacket(header, sensor_id, value1, value2, value3, received_crc)

        elif header.packet_type == PacketType.CONFIG:
            if header.payload_size != CONFIG_SIZE:
                return None
            network_id, wifi_channel, tx_power = struct.unpack("<BBB", payload[:-2])
            return ConfigPacket(header, network_id, wifi_channel, tx_power, received_crc)

        elif header.packet_type == PacketType.BULK_DATA:
            # For bulk data, just return the payload without CRC
            return payload[:-2]

        elif header.packet_type == PacketType.PING:
            if header.payload_size != PING_SIZE:
                return None
            (timestamp,) = struct.unpack("<I", payload[:-2])
            return PingPacket(header, timestamp, received_crc)

        elif header.packet_type == PacketType.ACK:
            if header.payload_size != ACK_SIZE:
                return None
            ack_type, ack_id, status = struct.unpack("<BBH", payload[:-2])
            return AckPacket(header, ack_type, ack_id, status, received_crc)

        elif header.packet_type == PacketType.CUSTOM_MESSAGE:
            if header.payload_size != CUSTOM_MESSAGE_SIZE:
                return None
            (custom_data,) = struct.unpack("<126s", payload[:-2])
            return CustomMessagePacket(header, custom_data, received_crc)

        else:
            print(f"Unknown packet type: {header.packet_type}")
            return None

    except struct.error as e:
        print(f"Struct unpack error for type {header.packet_type}: {e}")
        return None
