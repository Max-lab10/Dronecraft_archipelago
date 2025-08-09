#ifndef CONFIG_MANAGER_H
#define CONFIG_MANAGER_H

#include <Arduino.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>

// Configuration file paths
extern const char* CONFIG_FILE;
extern const char* ESPNOW_CONFIG_FILE;
extern const char* WIFI_CONFIG_FILE;
extern const char* OTA_URL_FILE;

// WiFi configuration
extern String wifi_ssid;
extern String wifi_password;
extern bool wifi_connected;

// OTA URL storage
extern String ota_url;

// Function declarations
void loadConfiguration();
void loadWiFiConfiguration();
bool updateWiFiConfig(const char* ssid, const char* password);
void saveESPNowConfigAndRestart(uint8_t network_id, uint8_t wifi_channel, uint8_t tx_power);
void loadOTAUrl();
bool saveOTAUrl(const char* url);
bool checkAndExecutePendingOTA();

#endif // CONFIG_MANAGER_H 