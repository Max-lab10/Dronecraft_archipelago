#ifndef TELEMETRY_GENERATOR_H
#define TELEMETRY_GENERATOR_H

#include <Arduino.h>
#include "Packet.h"

// Test mode telemetry generation functions
class TelemetryGenerator {
private:
    static uint32_t seed;
    static bool initialized;
    
    // Random number generation
    static void initRandom();
    static float randomFloat(float min, float max);
    static int randomInt(int min, int max);
    
public:
    // Initialize the generator
    static void init();
    
    // Generate random telemetry packet
    static TelemetryPacket generateRandomTelemetry(uint8_t drone_id, uint8_t network_id);
    
    // Generate telemetry with specific ranges
    static TelemetryPacket generateTelemetryInRange(
        uint8_t drone_id, 
        uint8_t network_id,
        float x_min, float x_max,
        float y_min, float y_max,
        float z_min, float z_max,
        float v_min, float v_max
    );
    
    // Calculate CRC for packets
    static uint16_t calculateCRC(const uint8_t* data, size_t len);
};

#endif // TELEMETRY_GENERATOR_H 