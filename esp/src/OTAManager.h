#ifndef OTA_MANAGER_H
#define OTA_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Update.h>

// Function declarations
bool startOTAUpdate(const char* ota_url);
bool connectToWiFi(const char* ssid, const char* password, unsigned long timeout_ms = 10000);
void safeWiFiDisconnect();

#endif // OTA_MANAGER_H 