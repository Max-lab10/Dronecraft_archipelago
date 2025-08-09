#ifndef ESPNOW_MANAGER_H
#define ESPNOW_MANAGER_H

#include <Arduino.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "Packet.h"

#define MAX_PEERS 20
#define BROADCAST_MAC {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}
#define MAX_RETRY_COUNT 3
#define SEND_TIMEOUT_MS 100

// Production ESP-NOW configuration
struct ESPNowConfig {
    uint8_t channel = 1;
    uint8_t tx_power = 11; // dBm
    bool encrypt = false;
    uint8_t network_id = 0x12;
};

class ESPNowManager {
private:
    uint8_t broadcastAddress[6] = BROADCAST_MAC;
    esp_now_peer_info_t peerInfo;
    bool initialized = false;
    ESPNowConfig config;
    
    // Statistics
    uint32_t packets_sent = 0;
    uint32_t packets_received = 0;
    uint32_t send_failures = 0;
    uint32_t receive_errors = 0;
    
    static void onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status);
    static void onDataReceived(const uint8_t *mac_addr, const uint8_t *incomingData, int len);
    
    bool validatePacket(const uint8_t* data, size_t len);
    bool sendWithRetry(const uint8_t* data, size_t len, uint8_t retries = MAX_RETRY_COUNT);
    
public:
    ESPNowManager();
    bool init(const ESPNowConfig& cfg = ESPNowConfig());
    bool addPeer(const uint8_t* peerAddress);
    bool removePeer(const uint8_t* peerAddress);
    
    // Packet sending methods
    bool sendTelemetryPacket(const TelemetryPacket& packet);
    bool sendCustomMessagePacket(const CustomMessagePacket& packet);
    bool sendCommandPacket(const CommandPacket& packet);
    bool sendStatusPacket(const StatusPacket& packet);
    bool sendBroadcast(const uint8_t* data, size_t len);
    
    // Configuration
    void setChannel(int channel);
    void setTxPower(int power);
    ESPNowConfig getConfig() const { return config; }
    
    // Statistics
    void printStatistics();
    uint32_t getPacketsSent() const { return packets_sent; }
    uint32_t getPacketsReceived() const { return packets_received; }
    uint32_t getSendFailures() const { return send_failures; }
    
    static ESPNowManager* instance;
};

#endif // ESPNOW_MANAGER_H