#ifndef CRC_UTILS_H
#define CRC_UTILS_H

#include <stdint.h>
#include <stddef.h>

// CRC16 calculation function (matching controller)
uint16_t calculateCRC16(const uint8_t* data, size_t length);

#endif // CRC_UTILS_H 