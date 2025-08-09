#include "ConfigManager.h"
#include "ESPNowManager.h"
#include "OTAManager.h"
#include <WiFi.h>
#include <HTTPClient.h>

// Configuration file paths
const char* CONFIG_FILE = "/config.json";
const char* ESPNOW_CONFIG_FILE = "/espnow_config.json";
const char* WIFI_CONFIG_FILE = "/wifi_config.json";
const char* OTA_URL_FILE = "/ota_url.json";

// WiFi configuration
String wifi_ssid = "";
String wifi_password = "";
bool wifi_connected = false;

// OTA URL storage
String ota_url = "";

// Load WiFi configuration from SPIFFS
void loadWiFiConfiguration() {
    if (SPIFFS.exists(WIFI_CONFIG_FILE)) {
        File file = SPIFFS.open(WIFI_CONFIG_FILE, "r");
        if (file) {
            StaticJsonDocument<512> doc;
            DeserializationError error = deserializeJson(doc, file);
            file.close();
            
            if (!error) {
                wifi_ssid = doc["ssid"] | "";
                wifi_password = doc["password"] | "";
                
                if (wifi_ssid.length() > 0) {
                    Serial.printf("Loaded WiFi config: SSID=%s (not connecting yet)\n", wifi_ssid.c_str());
                }
            } else {
                Serial.println("Failed to parse WiFi config file");
            }
        } else {
            Serial.println("Failed to open WiFi config file");
        }
    }
}

// Update WiFi configuration
bool updateWiFiConfig(const char* ssid, const char* password) {
    if (!ssid || strlen(ssid) == 0) {
        Serial.println("ERROR: Invalid SSID");
        return false;
    }
    
    Serial.printf("Updating WiFi configuration: SSID=%s\n", ssid);
    
    // Save WiFi configuration to SPIFFS
    StaticJsonDocument<512> doc;
    doc["ssid"] = ssid;
    doc["password"] = password ? password : "";
    
    File file = SPIFFS.open(WIFI_CONFIG_FILE, "w");
    if (file) {
        size_t bytes_written = serializeJson(doc, file);
        file.close();
        
        if (bytes_written > 0) {
            wifi_ssid = String(ssid);
            wifi_password = String(password ? password : "");
            Serial.println("WiFi configuration saved successfully");
            return true;
        } else {
            Serial.println("ERROR: Failed to write WiFi configuration");
            return false;
        }
    } else {
        Serial.println("ERROR: Failed to open WiFi config file for writing");
        return false;
    }
}

// Load configuration from SPIFFS
void loadConfiguration() {
    if (!SPIFFS.begin(true)) {
        Serial.println("Failed to mount SPIFFS, using default configuration");
        return;
    }
    
    // Load WiFi configuration (but don't connect yet)
    loadWiFiConfiguration();
    
    // Load OTA URL configuration
    loadOTAUrl();
    
    // Load drone configuration
    if (SPIFFS.exists(CONFIG_FILE)) {
        File file = SPIFFS.open(CONFIG_FILE, "r");
        if (file) {
            StaticJsonDocument<512> doc;
            DeserializationError error = deserializeJson(doc, file);
            file.close();
            
            if (!error) {
                uint8_t new_drone_id = doc["drone_id"] | 1;
                if (new_drone_id > 0 && new_drone_id <= 255) {
                    extern uint8_t drone_id;
                    drone_id = new_drone_id;
                    Serial.printf("Loaded drone ID: %d\n", drone_id);
                } else {
                    Serial.println("Invalid drone ID in config, using default");
                }
            } else {
                Serial.println("Failed to parse config file, using defaults");
            }
        } else {
            Serial.println("Failed to open config file, using defaults");
        }
    } else {
        // First boot - save default config
        StaticJsonDocument<512> doc;
        extern uint8_t drone_id;
        doc["drone_id"] = drone_id;
        
        File file = SPIFFS.open(CONFIG_FILE, "w");
        if (file) {
            serializeJson(doc, file);
            file.close();
            Serial.printf("Saved default drone ID: %d\n", drone_id);
        } else {
            Serial.println("Failed to save default config");
        }
    }
    
    // Load ESP-NOW configuration
    if (SPIFFS.exists(ESPNOW_CONFIG_FILE)) {
        File file = SPIFFS.open(ESPNOW_CONFIG_FILE, "r");
        if (file) {
            StaticJsonDocument<512> doc;
            DeserializationError error = deserializeJson(doc, file);
            file.close();
            
            if (!error) {
                uint8_t network_id = doc["network_id"] | 0x12;
                uint8_t channel = doc["channel"] | 1;
                uint8_t tx_power = doc["tx_power"] | 11;
                bool encrypt = doc["encrypt"] | false;
                
                // Validate configuration values
                if (channel >= 1 && channel <= 13 && 
                    tx_power >= 0 && tx_power <= 20 &&
                    network_id > 0) {
                    extern ESPNowConfig espnow_config;
                    espnow_config.network_id = network_id;
                    espnow_config.channel = channel;
                    espnow_config.tx_power = tx_power;
                    espnow_config.encrypt = encrypt;
                    Serial.printf("Loaded ESP-NOW config: network_id=%d, channel=%d\n", 
                                 espnow_config.network_id, espnow_config.channel);
                } else {
                    Serial.println("Invalid ESP-NOW config values, using defaults");
                }
            } else {
                Serial.println("Failed to parse ESP-NOW config file, using defaults");
            }
        } else {
            Serial.println("Failed to open ESP-NOW config file, using defaults");
        }
    } else {
        // First boot - save default ESP-NOW config
        StaticJsonDocument<512> doc;
        extern ESPNowConfig espnow_config;
        doc["network_id"] = espnow_config.network_id;
        doc["channel"] = espnow_config.channel;
        doc["tx_power"] = espnow_config.tx_power;
        doc["encrypt"] = espnow_config.encrypt;
        
        File file = SPIFFS.open(ESPNOW_CONFIG_FILE, "w");
        if (file) {
            serializeJson(doc, file);
            file.close();
            Serial.printf("Saved default ESP-NOW config: network_id=%d, channel=%d\n", 
                         espnow_config.network_id, espnow_config.channel);
        } else {
            Serial.println("Failed to save default ESP-NOW config");
        }
    }
    
    // Check for pending OTA update after loading all configurations
    if (checkAndExecutePendingOTA()) {
        // OTA update was started, this function will not return
        return;
    }
}

// Save ESP-NOW configuration to SPIFFS and restart
void saveESPNowConfigAndRestart(uint8_t network_id, uint8_t wifi_channel, uint8_t tx_power) {
    // Validate input parameters
    if (wifi_channel < 1 || wifi_channel > 13) {
        Serial.println("ERROR: Invalid WiFi channel, must be 1-13");
        return;
    }
    
    if (network_id == 0) {
        Serial.println("ERROR: Invalid network ID, must be non-zero");
        return;
    }
    
    if (tx_power > 20) {
        Serial.println("ERROR: Invalid TX power, must be 0-20");
        return;
    }
    
    StaticJsonDocument<512> doc;
    extern ESPNowConfig espnow_config;
    doc["network_id"] = network_id;
    doc["channel"] = wifi_channel;
    doc["tx_power"] = tx_power;
    doc["encrypt"] = espnow_config.encrypt;
    
    File file = SPIFFS.open(ESPNOW_CONFIG_FILE, "w");
    if (file) {
        size_t bytes_written = serializeJson(doc, file);
        file.close();
        
        if (bytes_written > 0) {
            Serial.printf("Saved new ESP-NOW config: network_id=%d, channel=%d\n", 
                         network_id, wifi_channel);
            Serial.println("Restarting ESP32...");
            delay(100);
            ESP.restart();
        } else {
            Serial.println("ERROR: Failed to write ESP-NOW configuration");
        }
    } else {
        Serial.println("ERROR: Failed to open ESP-NOW config file for writing");
    }
} 

// Load OTA URL from SPIFFS
void loadOTAUrl() {
    if (SPIFFS.exists(OTA_URL_FILE)) {
        File file = SPIFFS.open(OTA_URL_FILE, "r");
        if (file) {
            StaticJsonDocument<512> doc;
            DeserializationError error = deserializeJson(doc, file);
            file.close();
            
            if (!error) {
                ota_url = doc["ota_url"] | "";
                if (ota_url.length() > 0) {
                    Serial.printf("Loaded OTA URL: %s\n", ota_url.c_str());
                }
            } else {
                Serial.println("Failed to parse OTA URL file");
            }
        } else {
            Serial.println("Failed to open OTA URL file");
        }
    }
}

// Save OTA URL to SPIFFS
bool saveOTAUrl(const char* url) {
    if (!url || strlen(url) == 0) {
        Serial.println("ERROR: Invalid OTA URL");
        return false;
    }
    
    Serial.printf("Saving OTA URL: %s\n", url);
    
    // Save OTA URL to SPIFFS
    StaticJsonDocument<512> doc;
    doc["ota_url"] = url;
    
    File file = SPIFFS.open(OTA_URL_FILE, "w");
    if (file) {
        size_t bytes_written = serializeJson(doc, file);
        file.close();
        
        if (bytes_written > 0) {
            ota_url = String(url);
            Serial.println("OTA URL saved successfully");
            return true;
        } else {
            Serial.println("ERROR: Failed to write OTA URL");
            return false;
        }
    } else {
        Serial.println("ERROR: Failed to open OTA URL file for writing");
        return false;
    }
} 

// Check for pending OTA update and execute it
bool checkAndExecutePendingOTA() {
    if (SPIFFS.exists("/pending_ota.json")) {
        Serial.println("=== Found pending OTA update ===");
        
        File file = SPIFFS.open("/pending_ota.json", "r");
        if (file) {
            StaticJsonDocument<512> doc;
            DeserializationError error = deserializeJson(doc, file);
            file.close();
            
            if (!error && doc["pending_ota"]) {
                Serial.println("Pending OTA update confirmed, starting update...");
                
                // Delete the pending file first
                SPIFFS.remove("/pending_ota.json");
                
                // Start OTA update with saved URL
                if (ota_url.length() > 0 && wifi_ssid.length() > 0) {
                    Serial.printf("Starting OTA update with URL: %s\n", ota_url.c_str());
                    startOTAUpdate(ota_url.c_str());
                    return true;
                } else {
                    Serial.println("ERROR: Missing WiFi credentials or OTA URL");
                    return false;
                }
            }
        }
    }
    return false;
} 