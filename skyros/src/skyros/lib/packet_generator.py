#!/usr/bin/env python3
import random
import struct
import time

from .packet_codec import calculate_crc16
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


def generate_telemetry_packet(drone_id=None) -> TelemetryPacket:
    """Generate a telemetry packet with optional specific drone ID"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=TELEMETRY_SIZE,
        packet_type=PacketType.TELEMETRY,
        network_id=0x12,
    )

    packet = TelemetryPacket(
        header=header,
        drone_id=drone_id if drone_id is not None else random.randint(1, 10),
        x=random.uniform(-100.0, 100.0),
        y=random.uniform(-100.0, 100.0),
        z=random.uniform(-50.0, 50.0),
        vx=random.uniform(-10.0, 10.0),
        vy=random.uniform(-10.0, 10.0),
        vz=random.uniform(-5.0, 5.0),
        crc=0,
    )

    return packet


def generate_command_packet() -> CommandPacket:
    """Generate a command packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=COMMAND_SIZE,
        packet_type=PacketType.COMMAND,
        network_id=0x12,
    )

    packet = CommandPacket(
        header=header,
        command_id=random.randint(1, 20),
        target_id=random.randint(1, 10),
        param=random.randint(0, 65535),
        crc=0,
    )

    return packet


def generate_status_packet() -> StatusPacket:
    """Generate a status packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=STATUS_SIZE,
        packet_type=PacketType.STATUS,
        network_id=0x12,
    )

    packet = StatusPacket(
        header=header,
        drone_id=random.randint(1, 10),
        status_code=random.randint(0, 255),
        battery_mv=random.randint(3000, 4200),
        error_flags=random.randint(0, 65535),
        crc=0,
    )

    return packet


def generate_sensor_packet() -> SensorPacket:
    """Generate a sensor data packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=SENSOR_SIZE,
        packet_type=PacketType.SENSOR_DATA,
        network_id=0x12,
    )

    packet = SensorPacket(
        header=header,
        sensor_id=random.randint(1, 5),
        value1=random.uniform(-50.0, 50.0),
        value2=random.uniform(0.0, 100.0),
        value3=random.uniform(-180.0, 180.0),
        crc=0,
    )

    return packet


def generate_config_packet(network_id: int = 0x12, wifi_channel: int = 1, tx_power: int = 20) -> ConfigPacket:
    """Generate a configuration packet
    WARNING: This will cause ESP32 to save config and restart!
    Only use this function intentionally, not in random packet generation.
    """
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=CONFIG_SIZE,
        packet_type=PacketType.CONFIG,
        network_id=network_id,
    )

    packet = ConfigPacket(
        header=header, network_id=network_id, wifi_channel=wifi_channel, tx_power=tx_power, crc=0
    )

    return packet


def generate_bulk_packet() -> bytes:
    """Generate a packet with arbitrary data"""
    # Random size from 10 to MAX_PAYLOAD_SIZE bytes
    payload_size = random.randint(10, MAX_PAYLOAD_SIZE)

    header = struct.pack(HEADER_FORMAT, PACKET_PREAMBLE, payload_size, PacketType.BULK_DATA, 0x12)

    # Generate random data
    data = bytes([random.randint(0, 255) for _ in range(payload_size - 2)])

    # Calculate CRC
    temp_packet = header + data + b"\x00\x00"
    crc = calculate_crc16(temp_packet)

    return header + data + struct.pack("<H", crc)


def generate_ping_packet() -> PingPacket:
    """Generate a ping packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=PING_SIZE,
        packet_type=PacketType.PING,
        network_id=0x12,
    )

    packet = PingPacket(header=header, timestamp=int(time.time() * 1000) & 0xFFFFFFFF, crc=0)

    return packet


def generate_ack_packet() -> AckPacket:
    """Generate an ACK packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE, payload_size=ACK_SIZE, packet_type=PacketType.ACK, network_id=0x12
    )

    packet = AckPacket(
        header=header,
        ack_type=random.randint(1, 8),
        ack_id=random.randint(0, 255),
        status=random.randint(0, 65535),
        crc=0,
    )

    return packet


def generate_custom_message_packet() -> CustomMessagePacket:
    """Generate a custom message packet"""
    header = PacketHeader(
        preamble=PACKET_PREAMBLE,
        payload_size=CUSTOM_MESSAGE_SIZE,
        packet_type=PacketType.CUSTOM_MESSAGE,
        network_id=0x12,
    )

    # Generate random custom data
    custom_data = bytes([random.randint(0, 255) for _ in range(126)])

    packet = CustomMessagePacket(header=header, custom_data=custom_data, crc=0)

    return packet


def generate_random_packet():
    """Generate a random type of packet"""
    packet_generators = [
        (generate_telemetry_packet, 30),  # 30% probability
        (generate_command_packet, 15),  # 15%
        (generate_status_packet, 15),  # 15%
        (generate_sensor_packet, 15),  # 15%
        # CONFIG packets removed from random generation to prevent constant reboots
        (generate_bulk_packet, 10),  # 10%
        (generate_ping_packet, 5),  # 5%
        (generate_ack_packet, 5),  # 5%
        (generate_custom_message_packet, 5),  # 5%
    ]

    # Choose a generator based on weights
    total_weight = sum(weight for _, weight in packet_generators)
    r = random.uniform(0, total_weight)

    cumulative = 0
    for generator, weight in packet_generators:
        cumulative += weight
        if r <= cumulative:
            return generator()

    # Default to telemetry
    return generate_telemetry_packet()
