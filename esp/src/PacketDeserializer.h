#ifndef PACKET_DESERIALIZER_H
#define PACKET_DESERIALIZER_H

#include "Packet.h"

// CRC16 calculation function declaration
uint16_t calculateCRC16(const uint8_t* data, size_t length);

class PacketDeserializer {
public:
    void processReceivedData();

private:
    void handleReceivedPacket(const uint8_t* data, size_t length, uint8_t packet_type);

    uint8_t rx_buffer[RX_BUFFER_SIZE];
    int rx_buffer_pos = 0;
    bool searching_preamble = true;
    uint8_t header_buffer[sizeof(PacketHeader)];
    int header_pos = 0;
};

#endif // PACKET_DESERIALIZER_H