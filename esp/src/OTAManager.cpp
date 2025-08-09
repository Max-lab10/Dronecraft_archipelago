#include "OTAManager.h"
#include "ConfigManager.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <Update.h>

// Safe WiFi disconnect function
void safeWiFiDisconnect() {
    Serial.println("Safely disconnecting WiFi...");
    WiFi.disconnect();
    wifi_connected = false;
    delay(100);
}

// WiFi connection using Arduino WiFi API (for use after reboot)
bool connectToWiFi(const char* ssid, const char* password, unsigned long timeout_ms) {
    if (!ssid || strlen(ssid) == 0) {
        Serial.println("ERROR: Invalid SSID");
        return false;
    }
    
    // Check available memory before WiFi operations
    if (ESP.getFreeHeap() < 15000) {
        Serial.println("ERROR: Insufficient memory for WiFi operations");
        return false;
    }
    
    Serial.printf("Connecting to WiFi: SSID='%s', Password length: %d\n", ssid, password ? strlen(password) : 0);
    
    // Use Arduino WiFi API
    WiFi.mode(WIFI_STA);
    
    WiFi.setTxPower(WIFI_POWER_11dBm);
    
    WiFi.begin(ssid, password);
    
    // Wait for connection with timeout
    unsigned long start_time = millis();
    
    while ((millis() - start_time) < timeout_ms) {
        delay(500);
        Serial.print(".");
        
        if (WiFi.status() == WL_CONNECTED) {
            Serial.println();
            wifi_connected = true;
            Serial.printf("WiFi connected: SSID=%s, RSSI=%d, IP=%s\n", 
                         WiFi.SSID().c_str(), WiFi.RSSI(), WiFi.localIP().toString().c_str());
            return true;
        }
        
        // Check for timeout
        if (millis() - start_time >= timeout_ms) {
            Serial.println("\nERROR: WiFi connection timeout");
            WiFi.disconnect();
            return false;
        }
        
        // Check memory during connection attempt
        if (ESP.getFreeHeap() < 8000) {
            Serial.println("\nERROR: Memory too low during WiFi connection");
            WiFi.disconnect();
            return false;
        }
    }
    
    Serial.println("\nERROR: Failed to connect to WiFi");
    WiFi.disconnect();
    return false;
}

// OTA update function with improved error handling
bool startOTAUpdate(const char* ota_url_param) {
    const char* url_to_use = ota_url_param;
    
    // If no URL provided, try to use saved URL
    if (!url_to_use || strlen(url_to_use) == 0) {
        if (ota_url.length() > 0) {
            Serial.printf("Using saved OTA URL: %s\n", ota_url.c_str());
            url_to_use = ota_url.c_str();
        } else {
            Serial.println("ERROR: No OTA URL provided and no saved URL available");
            return false;
        }
    }
    
    if (!url_to_use || strlen(url_to_use) == 0) {
        Serial.println("ERROR: Invalid OTA URL");
        return false;
    }
    
    // Check memory before starting OTA
    if (ESP.getFreeHeap() < 20000) {
        Serial.println("ERROR: Insufficient memory for OTA update");
        return false;
    }
    
    Serial.printf("Starting OTA update from: %s\n", url_to_use);
    
    // Connect to WiFi only when needed for OTA
    if (!wifi_connected) {
        if (wifi_ssid.length() > 0) {
            Serial.println("Connecting to WiFi for OTA update...");
            
            // Try multiple connection attempts
            bool connected = false;
            for (int attempt = 1; attempt <= 3; attempt++) {
                Serial.printf("WiFi connection attempt %d/3...\n", attempt);
                
                if (connectToWiFi(wifi_ssid.c_str(), wifi_password.c_str(), 15000)) {
                    connected = true;
                    break;
                } else {
                    Serial.printf("WiFi connection attempt %d failed\n", attempt);
                    if (attempt < 3) {
                        Serial.println("Waiting 2 seconds before retry...");
                        delay(2000);
                    }
                }
            }
            
            if (!connected) {
                Serial.println("ERROR: Failed to connect to WiFi for OTA update after 3 attempts");
                Serial.println("Restarting device to try again...");
                delay(3000);
                ESP.restart();
                return false;
            }
        } else {
            Serial.println("ERROR: No WiFi credentials available for OTA update");
            return false;
        }
    }
    
    // Check memory again after WiFi connection
    if (ESP.getFreeHeap() < 15000) {
        Serial.println("ERROR: Memory too low after WiFi connection");
        return false;
    }
    
    // Create HTTP client with proper timeout
    HTTPClient http;
    http.setTimeout(30000); // 30 second timeout
    http.setReuse(false); // Don't reuse connection
    
    Serial.println("Connecting to firmware server...");
    http.begin(url_to_use);
    
    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("ERROR: HTTP GET failed, code: %d\n", httpCode);
        http.end();
        Serial.println("Restarting device to try again...");
        delay(3000);
        ESP.restart();
        return false;
    }
    
    int contentLength = http.getSize();
    if (contentLength <= 0) {
        Serial.println("ERROR: Invalid content length");
        http.end();
        return false;
    }
    
    Serial.printf("Downloading firmware: %d bytes\n", contentLength);
    
    // Check if we have enough space for the update
    if (contentLength > UPDATE_SIZE_UNKNOWN) {
        Serial.println("ERROR: Firmware size too large");
        http.end();
        return false;
    }
    
    // Start OTA update
    Serial.println("Starting OTA update process...");
    if (!Update.begin(contentLength)) {
        Serial.printf("ERROR: Not enough space to begin OTA update. Free: %d, Required: %d\n", 
                     ESP.getFreeHeap(), contentLength);
        http.end();
        return false;
    }
    
    // Get the tcp stream
    WiFiClient * stream = http.getStreamPtr();
    
    // Write the firmware with timeout protection
    unsigned long download_start = millis();
    const unsigned long download_timeout = 120000; // 2 minute timeout for download
    
    Serial.println("Downloading firmware data...");
    size_t written = Update.writeStream(*stream);
    Serial.printf("Downloaded %d bytes\n", written);
    
    // Check for download timeout
    if (millis() - download_start > download_timeout) {
        Serial.println("ERROR: OTA download timeout");
        http.end();
        Serial.println("Restarting device to try again...");
        delay(3000);
        ESP.restart();
        return false;
    }
    
    if (written != contentLength) {
        Serial.printf("ERROR: Written size mismatch. Expected: %d, Got: %d\n", contentLength, written);
        http.end();
        return false;
    }
    
    http.end();
    
    // Finalize the update
    if (!Update.end()) {
        Serial.printf("ERROR: OTA update failed: %s\n", Update.errorString());
        return false;
    }
    
    Serial.println("OTA update completed successfully.");
    
    // Clean up configuration files after successful OTA
    Serial.println("Cleaning up configuration files...");
    SPIFFS.remove(WIFI_CONFIG_FILE);
    SPIFFS.remove(OTA_URL_FILE);
    Serial.println("Configuration files cleaned up.");
    
    Serial.println("Restarting with new firmware...");
    delay(2000);
    ESP.restart();
    return true;
} 