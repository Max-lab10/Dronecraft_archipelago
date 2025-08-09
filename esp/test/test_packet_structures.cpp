#include <unity.h>
#include <Arduino.h>

// Include packet definitions directly
#define PACKET_PREAMBLE 0xAA55
#define MAX_PAYLOAD_SIZE 128

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
    OTA_CONFIG = 10
};

struct PacketHeader {
    uint16_t preamble;
    uint8_t payload_size;
    uint8_t packet_type;
    uint8_t network_id;
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

// Новый объединенный OTA_CONFIG пакет
struct OtaConfigPacket {
    PacketHeader header;
    uint8_t drone_id;
    uint8_t config_flags;  // Биты: 0=OTA, 1=WiFi, 2=Restart
    char ssid[24];         // Уменьшенный размер SSID
    char password[32];     // Уменьшенный размер пароля
    char ota_url[48];      // Уменьшенный размер URL
    uint16_t crc;
} __attribute__((packed));

// Simple CRC16 implementation for testing
uint16_t calculateCRC16(const uint8_t* data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// Test packet structure sizes
void test_packet_sizes() {
    TEST_ASSERT_EQUAL(5, sizeof(PacketHeader));  // 2 + 1 + 1 + 1 = 5 bytes
    TEST_ASSERT_EQUAL(32, sizeof(TelemetryPacket));  // 5 + 1 + 6*4 + 2 = 32 bytes
    TEST_ASSERT_EQUAL(11, sizeof(CommandPacket));  // 5 + 1 + 1 + 2 + 2 = 11 bytes
    TEST_ASSERT_EQUAL(13, sizeof(StatusPacket));  // 5 + 1 + 1 + 2 + 2 + 2 = 13 bytes
    TEST_ASSERT_EQUAL(115, sizeof(OtaConfigPacket));  // 5 + 1 + 1 + 24 + 32 + 48 + 2 = 115 bytes
}

// Test packet preamble constant
void test_packet_preamble() {
    TEST_ASSERT_EQUAL_HEX16(0xAA55, PACKET_PREAMBLE);
}

// Test packet type enumeration
void test_packet_types() {
    TEST_ASSERT_EQUAL(1, TELEMETRY);
    TEST_ASSERT_EQUAL(2, COMMAND);
    TEST_ASSERT_EQUAL(3, DRONE_STATUS);
    TEST_ASSERT_EQUAL(4, SENSOR_DATA);
    TEST_ASSERT_EQUAL(5, CONFIG);
    TEST_ASSERT_EQUAL(6, BULK_DATA);
    TEST_ASSERT_EQUAL(7, PING);
    TEST_ASSERT_EQUAL(8, ACK);
    TEST_ASSERT_EQUAL(9, CUSTOM_MESSAGE);
    TEST_ASSERT_EQUAL(10, OTA_CONFIG);
}

// Test maximum payload size
void test_max_payload_size() {
    TEST_ASSERT_EQUAL(128, MAX_PAYLOAD_SIZE);
}

// Test telemetry packet structure
void test_telemetry_packet_structure() {
    TelemetryPacket packet;
    packet.header.preamble = PACKET_PREAMBLE;
    packet.header.packet_type = TELEMETRY;
    packet.header.payload_size = 25; // 1+4+4+4+4+4+4+2 = 27 bytes payload
    packet.drone_id = 1;
    packet.x = 1.5f;
    packet.y = 2.5f;
    packet.z = 3.5f;
    packet.vx = 0.1f;
    packet.vy = 0.2f;
    packet.vz = 0.3f;
    
    // Calculate CRC
    uint8_t* data = (uint8_t*)&packet;
    packet.crc = calculateCRC16(data, sizeof(TelemetryPacket) - 2);
    
    TEST_ASSERT_EQUAL_HEX16(PACKET_PREAMBLE, packet.header.preamble);
    TEST_ASSERT_EQUAL(TELEMETRY, packet.header.packet_type);
    TEST_ASSERT_EQUAL(1, packet.drone_id);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.5f, packet.x);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 2.5f, packet.y);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 3.5f, packet.z);
}

// Test OTA config packet structure
void test_ota_config_packet_structure() {
    OtaConfigPacket packet;
    packet.header.preamble = PACKET_PREAMBLE;
    packet.header.packet_type = OTA_CONFIG;
    packet.header.payload_size = 108; // 1 + 1 + 24 + 32 + 48 + 2 = 108 bytes payload
    packet.drone_id = 1;
    packet.config_flags = 0x03; // OTA + WiFi flags
    
    strcpy(packet.ssid, "MyWiFi");
    strcpy(packet.password, "password123");
    strcpy(packet.ota_url, "http://example.com/firmware.bin");
    
    // Calculate CRC
    uint8_t* data = (uint8_t*)&packet;
    packet.crc = calculateCRC16(data, sizeof(OtaConfigPacket) - 2);
    
    TEST_ASSERT_EQUAL_HEX16(PACKET_PREAMBLE, packet.header.preamble);
    TEST_ASSERT_EQUAL(OTA_CONFIG, packet.header.packet_type);
    TEST_ASSERT_EQUAL(1, packet.drone_id);
    TEST_ASSERT_EQUAL(0x03, packet.config_flags);
    TEST_ASSERT_EQUAL_STRING("MyWiFi", packet.ssid);
    TEST_ASSERT_EQUAL_STRING("password123", packet.password);
    TEST_ASSERT_EQUAL_STRING("http://example.com/firmware.bin", packet.ota_url);
}

// Test that OTA config packet fits within 125 bytes
void test_ota_config_packet_size_limit() {
    TEST_ASSERT_LESS_OR_EQUAL(125, sizeof(OtaConfigPacket));
    TEST_ASSERT_EQUAL(115, sizeof(OtaConfigPacket)); // Exact size
}

// Test config flags functionality
void test_config_flags() {
    uint8_t flags = 0;
    
    // Test individual flags
    flags |= 0x01; // OTA flag
    TEST_ASSERT_TRUE(flags & 0x01);
    TEST_ASSERT_FALSE(flags & 0x02);
    TEST_ASSERT_FALSE(flags & 0x04);
    
    flags |= 0x02; // WiFi flag
    TEST_ASSERT_TRUE(flags & 0x01);
    TEST_ASSERT_TRUE(flags & 0x02);
    TEST_ASSERT_FALSE(flags & 0x04);
    
    flags |= 0x04; // Restart flag
    TEST_ASSERT_TRUE(flags & 0x01);
    TEST_ASSERT_TRUE(flags & 0x02);
    TEST_ASSERT_TRUE(flags & 0x04);
    
    // Test combined flags
    TEST_ASSERT_EQUAL(0x07, flags);
}

void RUN_UNITY_TESTS() {
    UNITY_BEGIN();
    
    RUN_TEST(test_packet_sizes);
    RUN_TEST(test_packet_preamble);
    RUN_TEST(test_packet_types);
    RUN_TEST(test_max_payload_size);
    RUN_TEST(test_telemetry_packet_structure);
    RUN_TEST(test_ota_config_packet_structure);
    RUN_TEST(test_ota_config_packet_size_limit);
    RUN_TEST(test_config_flags);
    
    UNITY_END();
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("=== PACKET STRUCTURE TESTS ===");
    RUN_UNITY_TESTS();
}

void loop() {
    // Tests run once in setup()
}