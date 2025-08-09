#ifndef PACKET_H
#define PACKET_H

#include <Arduino.h>

// Packet constants
#define PACKET_PREAMBLE 0xAA55
#define MAX_PAYLOAD_SIZE 128
#define RX_BUFFER_SIZE 256

// Packet header structure
struct PacketHeader {
    uint16_t preamble;
    uint8_t payload_size;
    uint8_t packet_type;
    uint8_t network_id;
} __attribute__((packed));

// Packet types enum
enum PacketType {
    TELEMETRY = 1,
    COMMAND = 2,
    DRONE_STATUS = 3,
    SENSOR_DATA = 4,
    CONFIG = 5,
    BULK_DATA = 6,
    PING = 7,
    ACK = 8,
    CUSTOM_MESSAGE = 9,
    OTA_CONFIG = 10  // Объединенный пакет для OTA и конфигурации
};

// Packet structures
struct ConfigPacket {
    PacketHeader header;
    uint8_t network_id;
    uint8_t wifi_channel;
    uint8_t tx_power;
    uint16_t crc;
} __attribute__((packed));

struct CustomMessagePacket {
    PacketHeader header;
    uint8_t custom_data[126];
    uint16_t crc;
} __attribute__((packed));

struct TelemetryPacket {
    PacketHeader header;
    uint8_t drone_id;
    float x;
    float y;
    float z;
    float vx;
    float vy;
    float vz;
    uint16_t crc;
} __attribute__((packed));

struct CommandPacket {
    PacketHeader header;
    uint8_t command_id;
    uint8_t target_id;
    uint16_t param;
    uint16_t crc;
} __attribute__((packed));

struct StatusPacket {
    PacketHeader header;
    uint8_t drone_id;
    uint8_t status_code;
    uint16_t battery_mv;
    uint16_t error_flags;
    uint16_t crc;
} __attribute__((packed));

struct SensorPacket {
    PacketHeader header;
    uint8_t sensor_id;
    float value1;
    float value2;
    float value3;
    uint16_t crc;
} __attribute__((packed));

struct PingPacket {
    PacketHeader header;
    uint32_t timestamp;
    uint16_t crc;
} __attribute__((packed));

struct AckPacket {
    PacketHeader header;
    uint8_t ack_type;
    uint8_t ack_id;
    uint16_t status;
    uint16_t crc;
} __attribute__((packed));

// Объединенный OTA и конфигурационный пакет (до 125 байт)
struct OtaConfigPacket {
    PacketHeader header;
    uint8_t drone_id;
    uint8_t config_flags;  // Биты: 0=OTA, 1=WiFi, 2=Restart
    char ssid[24];         // Уменьшенный размер SSID
    char password[32];     // Уменьшенный размер пароля
    char ota_url[48];      // Уменьшенный размер URL
    uint16_t crc;
} __attribute__((packed));

#endif // PACKET_H