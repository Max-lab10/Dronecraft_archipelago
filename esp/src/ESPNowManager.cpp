#include "ESPNowManager.h"
#include "PacketDeserializer.h"
#include "Statistics.h"
#include "ConfigManager.h"
#include "OTAManager.h"
#include "crc_utils.h"

extern Statistics stats;

ESPNowManager* ESPNowManager::instance = nullptr;

ESPNowManager::ESPNowManager() {
    instance = this;
}

bool ESPNowManager::init(const ESPNowConfig& cfg) {
    config = cfg;
    
    // Initialize WiFi using ESP-IDF API to avoid Arduino WiFi event conflicts
    wifi_init_config_t cfg_wifi = WIFI_INIT_CONFIG_DEFAULT();
    esp_err_t err = esp_wifi_init(&cfg_wifi);
    if (err != ESP_OK) {
        Serial.printf("Failed to init WiFi: %s\n", esp_err_to_name(err));
        return false;
    }
    
    // Set WiFi mode to station
    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        Serial.printf("Failed to set WiFi mode: %s\n", esp_err_to_name(err));
        return false;
    }
    
    // Start WiFi
    err = esp_wifi_start();
    if (err != ESP_OK) {
        Serial.printf("Failed to start WiFi: %s\n", esp_err_to_name(err));
        return false;
    }
    
    // Set channel and TX power with error checking
    esp_err_t wifi_result = esp_wifi_set_channel(config.channel, WIFI_SECOND_CHAN_NONE);
    if (wifi_result != ESP_OK) {
        Serial.printf("Failed to set WiFi channel: 0x%X\n", wifi_result);
        return false;
    }
    
    wifi_result = esp_wifi_set_max_tx_power(config.tx_power * 4); // Convert dBm to 0.25dBm units
    if (wifi_result != ESP_OK) {
        Serial.printf("Failed to set TX power: 0x%X\n", wifi_result);
        return false;
    }
    
    // Init ESP-NOW
    esp_err_t result = esp_now_init();
    if (result != ESP_OK) {
        Serial.printf("ESP-NOW init failed: 0x%X\n", result);
        return false;
    }
    
    // Register callbacks
    esp_now_register_send_cb(onDataSent);
    esp_now_register_recv_cb(onDataReceived);
    
    // Register broadcast peer
    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = config.channel;
    peerInfo.encrypt = config.encrypt;
    
    result = esp_now_add_peer(&peerInfo);
    if (result != ESP_OK) {
        Serial.printf("Failed to add broadcast peer: 0x%X\n", result);
        return false;
    }
    
    initialized = true;
    Serial.printf("ESP-NOW initialized: Channel %d, Power %ddBm\n", 
                 config.channel, config.tx_power);
    return true;
}

bool ESPNowManager::addPeer(const uint8_t* peerAddress) {
    esp_now_peer_info_t peer;
    memcpy(peer.peer_addr, peerAddress, 6);
    peer.channel = 0;
    peer.encrypt = false;
    
    if (esp_now_add_peer(&peer) != ESP_OK) {
        Serial.println("Failed to add peer");
        return false;
    }
    
    return true;
}

bool ESPNowManager::validatePacket(const uint8_t* data, size_t len) {
    if (!data || len < sizeof(PacketHeader)) {
        return false;
    }
    
    const PacketHeader* header = (const PacketHeader*)data;
    
    // Check preamble
    if (header->preamble != PACKET_PREAMBLE) {
        return false;
    }
    
    // Check packet size
    if (len != sizeof(PacketHeader) + header->payload_size) {
        return false;
    }
    
    return true;
}

bool ESPNowManager::sendWithRetry(const uint8_t* data, size_t len, uint8_t retries) {
    if (!initialized || !validatePacket(data, len)) {
        send_failures++;
        return false;
    }
    
    for (uint8_t attempt = 0; attempt < retries; attempt++) {
        esp_err_t result = esp_now_send(broadcastAddress, data, len);
        
        if (result == ESP_OK) {
            packets_sent++;
            stats.espnow.packets_sent++;
            stats.espnow.packets_sent_last_interval++;
            stats.espnow.bytes_sent += len;
            return true;
        }
        
        // Wait before retry
        if (attempt < retries - 1) {
            delay(10);
        }
    }
    
    send_failures++;
    Serial.printf("ERROR: ESP-NOW send failed after %d retries\n", retries);
    return false;
}

bool ESPNowManager::sendTelemetryPacket(const TelemetryPacket& packet) {
    return sendWithRetry((uint8_t*)&packet, sizeof(TelemetryPacket));
}

bool ESPNowManager::sendCustomMessagePacket(const CustomMessagePacket& packet) {
    return sendWithRetry((uint8_t*)&packet, sizeof(CustomMessagePacket));
}

bool ESPNowManager::sendCommandPacket(const CommandPacket& packet) {
    return sendWithRetry((uint8_t*)&packet, sizeof(CommandPacket));
}

bool ESPNowManager::sendStatusPacket(const StatusPacket& packet) {
    return sendWithRetry((uint8_t*)&packet, sizeof(StatusPacket));
}

bool ESPNowManager::removePeer(const uint8_t* peerAddress) {
    esp_err_t result = esp_now_del_peer(peerAddress);
    return (result == ESP_OK);
}

void ESPNowManager::setTxPower(int power) {
    config.tx_power = power;
    esp_wifi_set_max_tx_power(power * 4);
}

void ESPNowManager::printStatistics() {
    Serial.printf("ESP-NOW Stats - Sent: %u, Received: %u, Failures: %u, Errors: %u\n",
                 packets_sent, packets_received, send_failures, receive_errors);
}

bool ESPNowManager::sendBroadcast(const uint8_t* data, size_t len) {
    if (!initialized) {
        return false;
    }
    
    esp_err_t result = esp_now_send(broadcastAddress, data, len);
    return (result == ESP_OK);
}

void ESPNowManager::setChannel(int channel) {
    esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);
}

void ESPNowManager::onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
    if (instance) {
        if (status != ESP_NOW_SEND_SUCCESS) {
            instance->send_failures++;
            Serial.printf("ERROR: ESP-NOW send failed to %02X:%02X:%02X:%02X:%02X:%02X\n",
                         mac_addr[0], mac_addr[1], mac_addr[2], 
                         mac_addr[3], mac_addr[4], mac_addr[5]);
        }
    }
}

void ESPNowManager::onDataReceived(const uint8_t *mac_addr, const uint8_t *incomingData, int len) {
    if (!instance) return;
    
    instance->packets_received++;
    
    // Validate minimum packet size
    if (len < sizeof(PacketHeader)) {
        instance->receive_errors++;
        stats.espnow.packets_corrupted++;
        Serial.printf("DEBUG: Packet too small: %d < %d\n", len, sizeof(PacketHeader));
        return;
    }
    
    const PacketHeader* header = (const PacketHeader*)incomingData;
    
    // Validate preamble
    if (header->preamble != PACKET_PREAMBLE) {
        instance->receive_errors++;
        stats.espnow.packets_corrupted++;
        Serial.printf("DEBUG: Invalid preamble: 0x%04X != 0x%04X\n", header->preamble, PACKET_PREAMBLE);
        return;
    }
    
    // Filter by network_id
    if (header->network_id != instance->config.network_id) {
        // Silently drop packets from different networks
        Serial.printf("DEBUG: Dropping packet from network %d (expected %d)\n", 
                     header->network_id, instance->config.network_id);
        return;
    }
    
    // Validate packet size
    if (len != sizeof(PacketHeader) + header->payload_size) {
        instance->receive_errors++;
        stats.espnow.packets_corrupted++;
        Serial.printf("DEBUG: Packet size mismatch: %d != %d + %d\n", 
                     len, sizeof(PacketHeader), header->payload_size);
        return;
    }
    
    // Validate CRC for packets that have it
    if (header->packet_type == OTA_CONFIG && len >= sizeof(OtaConfigPacket)) {
        const OtaConfigPacket* packet = (const OtaConfigPacket*)incomingData;
        uint16_t calculated_crc = calculateCRC16(incomingData, len - 2);
        if (calculated_crc != packet->crc) {
            instance->receive_errors++;
            stats.espnow.packets_corrupted++;
            Serial.printf("ERROR: ESP-NOW CRC mismatch - Type: %d, Calc: 0x%04X, Recv: 0x%04X\n",
                header->packet_type, calculated_crc, packet->crc);
            return;
        }
    }
    
    // Update statistics for valid packets
    stats.espnow.packets_received++;
    stats.espnow.packets_received_last_interval++;
    stats.espnow.bytes_received += len;
    stats.espnow.by_type[header->packet_type].packets_received++;
    stats.espnow.by_type[header->packet_type].bytes_received += len;
    
    // Handle OTA_CONFIG packets (приходят по ESP-NOW)
    if (header->packet_type == OTA_CONFIG) {
        if (len >= sizeof(OtaConfigPacket)) {
            const OtaConfigPacket* packet = (const OtaConfigPacket*)incomingData;
            Serial.printf("Received OTA_CONFIG via ESP-NOW for drone %d:\n", packet->drone_id);
            Serial.printf("  Config flags: 0x%02X\n", packet->config_flags);
            Serial.printf("  SSID: '%s' (length: %d)\n", packet->ssid, strlen(packet->ssid));
            Serial.printf("  Password: '%s' (length: %d)\n", packet->password, strlen(packet->password));
            Serial.printf("  OTA URL: '%s' (length: %d)\n", packet->ota_url, strlen(packet->ota_url));
            
            // Validate WiFi credentials
            if (strlen(packet->ssid) == 0) {
                Serial.println("ERROR: WiFi SSID is empty in OTA_CONFIG packet");
                return;
            }
            
            if (strlen(packet->ssid) > 23) {
                Serial.printf("ERROR: WiFi SSID too long: %d characters (max 23)\n", strlen(packet->ssid));
                return;
            }
            
            if (strlen(packet->password) > 31) {
                Serial.printf("ERROR: WiFi password too long: %d characters (max 31)\n", strlen(packet->password));
                return;
            }
            
            // Save all configuration data to SPIFFS
            Serial.println("  -> Saving configuration data to SPIFFS...");
            
            // Save WiFi configuration
            bool wifi_saved = updateWiFiConfig(packet->ssid, packet->password);
            if (!wifi_saved) {
                Serial.println("ERROR: Failed to save WiFi configuration");
                return;
            }
            
            // Save OTA URL if provided 
            bool ota_saved = true;
            if (strlen(packet->ota_url) > 0) {
                ota_saved = saveOTAUrl(packet->ota_url);
                if (!ota_saved) {
                    Serial.println("ERROR: Failed to save OTA URL");
                    return;
                }
            }
            
            // Create pending OTA file to trigger update after reboot
            StaticJsonDocument<512> pending_doc;
            pending_doc["pending_ota"] = true;
            pending_doc["timestamp"] = millis();
            
            File pending_file = SPIFFS.open("/pending_ota.json", "w");
            if (pending_file) {
                serializeJson(pending_doc, pending_file);
                pending_file.close();
                Serial.println("  -> Pending OTA file created");
            } else {
                Serial.println("ERROR: Failed to create pending OTA file");
                return;
            }
            
            Serial.println("  -> All configuration saved successfully");
            Serial.println("  -> Restarting device to apply configuration...");
            delay(2000);
            ESP.restart();
        }
    }
    
    // Forward all other packets to UART (для ROS)
    size_t written = Serial1.write(incomingData, len);
    if (written == len) {
        Serial1.flush();
    } else {
        instance->receive_errors++;
        Serial.println("ERROR: Failed to forward ESP-NOW packet to UART");
    }
}