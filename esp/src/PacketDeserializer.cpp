#include "PacketDeserializer.h"
#include "Statistics.h"
#include "ESPNowManager.h"
#include "ConfigManager.h"
#include "crc_utils.h"

extern Statistics stats;
extern ESPNowManager espNowManager;
extern void saveESPNowConfigAndRestart(uint8_t network_id, uint8_t wifi_channel, uint8_t tx_power);

void PacketDeserializer::processReceivedData() {
    while (Serial1.available()) {
        uint8_t byte = Serial1.read();
        
        if (searching_preamble) {
            header_buffer[header_pos++] = byte;
            
            if (header_pos >= 2) {
                uint16_t potential_preamble = (header_buffer[1] << 8) | header_buffer[0];
                if (potential_preamble == PACKET_PREAMBLE) {
                    searching_preamble = false;
                    header_pos = 2;
                } else {
                    header_buffer[0] = header_buffer[1];
                    header_pos = 1;
                }
            }
        } else {
            if (header_pos < sizeof(PacketHeader)) {
                header_buffer[header_pos++] = byte;
                
                if (header_pos == sizeof(PacketHeader)) {
                    PacketHeader* header = (PacketHeader*)header_buffer;
                    if (header->payload_size > MAX_PAYLOAD_SIZE || 
                        header->payload_size < 2) {
                        searching_preamble = true;
                        header_pos = 0;
                        stats.uart.packets_corrupted++;
                        Serial.printf("ERROR: Invalid UART payload size: %d\n", header->payload_size);
                        continue;
                    }
                    rx_buffer_pos = 0;
                }
            } else {
                if (rx_buffer_pos < RX_BUFFER_SIZE) {
                    rx_buffer[rx_buffer_pos++] = byte;
                    
                    PacketHeader* header = (PacketHeader*)header_buffer;
                    if (rx_buffer_pos >= header->payload_size) {
                        uint8_t full_packet[RX_BUFFER_SIZE + sizeof(PacketHeader)];
                        memcpy(full_packet, header_buffer, sizeof(PacketHeader));
                        memcpy(full_packet + sizeof(PacketHeader), rx_buffer, header->payload_size);
                        
                        uint16_t calculated_crc = calculateCRC16(full_packet, sizeof(PacketHeader) + header->payload_size);
                        uint16_t received_crc = *((uint16_t*)(rx_buffer + header->payload_size - 2));
                        
                        if (calculated_crc == received_crc) {
                            stats.uart.packets_received++;
                            stats.uart.packets_received_last_interval++;
                            stats.uart.bytes_received += sizeof(PacketHeader) + header->payload_size;
                            handleReceivedPacket(full_packet, sizeof(PacketHeader) + header->payload_size, header->packet_type);
                        } else {
                            stats.uart.packets_corrupted++;
                            Serial.printf("ERROR: UART CRC mismatch - Type: %d, Calc: 0x%04X, Recv: 0x%04X\n",
                                header->packet_type, calculated_crc, received_crc);
                        }
                        
                        searching_preamble = true;
                        header_pos = 0;
                        rx_buffer_pos = 0;
                    }
                } else {
                    // Buffer overflow - reset and search for new preamble
                    searching_preamble = true;
                    header_pos = 0;
                    rx_buffer_pos = 0;
                    stats.uart.packets_corrupted++;
                    Serial.println("ERROR: UART buffer overflow, resetting");
                }
            }
        }
    }
}

void PacketDeserializer::handleReceivedPacket(const uint8_t* data, size_t length, uint8_t packet_type) {
    stats.uart.by_type[packet_type].packets_received++;
    stats.uart.by_type[packet_type].bytes_received += length;

    switch(packet_type) {
        case CONFIG: {
            if (length >= sizeof(ConfigPacket)) {
                const ConfigPacket* packet = (const ConfigPacket*)data;
                Serial.printf("Received CONFIG packet: network_id=%d, wifi_channel=%d, tx_power=%d\n", 
                             packet->network_id, packet->wifi_channel, packet->tx_power);
                
                // Save configuration and restart ESP32
                saveESPNowConfigAndRestart(packet->network_id, packet->wifi_channel, packet->tx_power);
            }
            break;
        }
        case TELEMETRY: {
            if (length >= sizeof(TelemetryPacket)) {
                const TelemetryPacket* packet = (const TelemetryPacket*)data;
                
                if (!espNowManager.sendTelemetryPacket(*packet)) {
                    Serial.println("ERROR: Failed to forward telemetry via ESP-NOW");
                }
            }
            break;
        }
        case CUSTOM_MESSAGE: {
            if (length >= sizeof(CustomMessagePacket)) {
                const CustomMessagePacket* packet = (const CustomMessagePacket*)data;
                
                if (!espNowManager.sendCustomMessagePacket(*packet)) {
                    Serial.println("ERROR: Failed to forward custom message via ESP-NOW");
                }
            }
            break;
        }
        case COMMAND: {
            if (length >= sizeof(CommandPacket)) {
                const CommandPacket* packet = (const CommandPacket*)data;
                
                if (!espNowManager.sendCommandPacket(*packet)) {
                    Serial.println("ERROR: Failed to forward command via ESP-NOW");
                }
            }
            break;
        }
        case DRONE_STATUS: {
            if (length >= sizeof(StatusPacket)) {
                const StatusPacket* packet = (const StatusPacket*)data;
                
                if (!espNowManager.sendStatusPacket(*packet)) {
                    Serial.println("ERROR: Failed to forward status via ESP-NOW");
                }
            }
            break;
        }
        case SENSOR_DATA: {
            // No logging for sensor data - too verbose
            break;
        }
        case PING: {
            break;
        }
        case ACK: {
            // No logging for ACK packets - too verbose
            break;
        }
        case BULK_DATA: {
            // No logging for bulk data - too verbose
            break;
        }
        default: {
            Serial.printf("Unknown packet type: %d\n", packet_type);
            break;
        }
    }
}