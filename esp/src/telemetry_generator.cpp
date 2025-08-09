#include "telemetry_generator.h"
#include <random>

// Static member initialization
uint32_t TelemetryGenerator::seed = 0;
bool TelemetryGenerator::initialized = false;

void TelemetryGenerator::init() {
    if (!initialized) {
        // Use analog noise to seed the random number generator
        seed = analogRead(36) + analogRead(39) + analogRead(34) + analogRead(35);
        randomSeed(seed);
        initialized = true;
        Serial.printf("TelemetryGenerator initialized with seed: %lu\n", seed);
    }
}

void TelemetryGenerator::initRandom() {
    if (!initialized) {
        init();
    }
}

float TelemetryGenerator::randomFloat(float min, float max) {
    initRandom();
    return min + (max - min) * (float)random(1000) / 1000.0f;
}

int TelemetryGenerator::randomInt(int min, int max) {
    initRandom();
    return random(min, max + 1);
}

TelemetryPacket TelemetryGenerator::generateRandomTelemetry(uint8_t drone_id, uint8_t network_id) {
    TelemetryPacket packet;
    
    // Initialize header
    packet.header.preamble = PACKET_PREAMBLE;
    packet.header.payload_size = sizeof(TelemetryPacket) - sizeof(PacketHeader);
    packet.header.packet_type = TELEMETRY;
    packet.header.network_id = network_id;
    
    // Set drone ID
    packet.drone_id = drone_id;
    
    // Generate random position data (typical drone flight range)
    packet.x = randomFloat(20.0f, 50.0f);   // X position: -50 to 50 meters
    packet.y = randomFloat(-50.0f, -20.0f);   // Y position: -50 to 50 meters
    packet.z = randomFloat(10.0f, 30.0f);     // Z position: 0 to 30 meters (altitude)
    
    // Generate random velocity data (typical drone speeds)
    packet.vx = randomFloat(-1.0f, 1.0f);  // X velocity: -10 to 10 m/s
    packet.vy = randomFloat(-1.0f, 1.0f);  // Y velocity: -10 to 10 m/s
    packet.vz = randomFloat(-1.0f, 1.0f);    // Z velocity: -5 to 5 m/s
    
    // Calculate CRC (excluding the CRC field itself)
    packet.crc = calculateCRC((uint8_t*)&packet, sizeof(TelemetryPacket) - sizeof(uint16_t));
    
    return packet;
}

TelemetryPacket TelemetryGenerator::generateTelemetryInRange(
    uint8_t drone_id, 
    uint8_t network_id,
    float x_min, float x_max,
    float y_min, float y_max,
    float z_min, float z_max,
    float v_min, float v_max
) {
    TelemetryPacket packet;
    
    // Initialize header
    packet.header.preamble = PACKET_PREAMBLE;
    packet.header.payload_size = sizeof(TelemetryPacket) - sizeof(PacketHeader);
    packet.header.packet_type = TELEMETRY;
    packet.header.network_id = network_id;
    
    // Set drone ID
    packet.drone_id = drone_id;
    
    // Generate position data within specified ranges
    packet.x = randomFloat(x_min, x_max);
    packet.y = randomFloat(y_min, y_max);
    packet.z = randomFloat(z_min, z_max);
    
    // Generate velocity data within specified ranges
    packet.vx = randomFloat(-v_min, v_max);
    packet.vy = randomFloat(-v_min, v_max);
    packet.vz = randomFloat(-v_min, v_max);
    
    // Calculate CRC (excluding the CRC field itself)
    packet.crc = calculateCRC((uint8_t*)&packet, sizeof(TelemetryPacket) - sizeof(uint16_t));
    
    return packet;
}

uint16_t TelemetryGenerator::calculateCRC(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x0001) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc = crc >> 1;
            }
        }
    }
    
    return crc;
} 