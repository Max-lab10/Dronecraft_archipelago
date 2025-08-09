#include "crc_utils.h"

// CRC16 calculation function (matching controller)
uint16_t calculateCRC16(const uint8_t* data, size_t length) {
    if (!data || length < 3) return 0;
    
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length - 2; i++) {
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