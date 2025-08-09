#include <Arduino.h>
#include <HardwareSerial.h>
#include <esp_task_wdt.h>
#include "Packet.h"
#include "PacketDeserializer.h"
#include "Statistics.h"
#include "ESPNowManager.h"
#include "ConfigManager.h"
#include "OTAManager.h"

// External variables
extern bool wifi_connected;
#ifdef TEST_MODE
#include "telemetry_generator.h"
#endif
#include "ConfigManager.h"
#include "OTAManager.h"

// External variables
extern bool wifi_connected;

#ifdef TEST_MODE
#include "telemetry_generator.h"
#endif

#if defined(CONFIG_IDF_TARGET_ESP32C3)
// ESP32-C3
#define RX1_PIN 3
#define TX1_PIN 4
#define RTS_PIN 5
#define CTS_PIN 6
#else
// ESP32, ESP32S2
#define RX1_PIN 16
#define TX1_PIN 17
#define RTS_PIN 18
#define CTS_PIN 21
#endif

// System configuration
#define WATCHDOG_TIMEOUT_S 10

// Production system components
Statistics stats;
PacketDeserializer deserializer;
ESPNowManager espNowManager;

// System state
bool system_initialized = false;
unsigned long last_heartbeat = 0;
uint8_t drone_id = 1; // Will be loaded from config file
ESPNowConfig espnow_config;

#ifdef TEST_MODE
// Test mode variables
unsigned long last_test_telemetry = 0;
const unsigned long TEST_TELEMETRY_INTERVAL = TEST_TELEM_INTERVAL; // Send telemetry every 4ms (250 packets per second)
uint32_t test_packets_sent = 0;
#endif

#ifdef TEST_MODE
// Test mode telemetry generation and sending
void sendTestTelemetry() {
    unsigned long now = millis();
    
    if (now - last_test_telemetry >= TEST_TELEMETRY_INTERVAL) {
        // Generate random telemetry packet
        TelemetryPacket packet = TelemetryGenerator::generateRandomTelemetry(
            drone_id, 
            espnow_config.network_id
        );
        
        // Send the packet
        if (espNowManager.sendTelemetryPacket(packet)) {
            test_packets_sent++;
            // Serial.printf("TEST: Sent telemetry packet #%lu - Drone:%d Pos(%.2f,%.2f,%.2f) Vel(%.2f,%.2f,%.2f)\n",
            //     test_packets_sent,
            //     packet.drone_id,
            //     packet.x, packet.y, packet.z,
            //     packet.vx, packet.vy, packet.vz
            // );
        } else {
            Serial.println("TEST: Failed to send telemetry packet");
        }
        
        last_test_telemetry = now;
    }
}
#endif

// System health check
void systemHealthCheck() {
    unsigned long now = millis();
    
    // Reset watchdog
    esp_task_wdt_reset();
    
    // Check system components
    if (now - last_heartbeat > 5000) {
        Serial.printf("HEARTBEAT: Drone %d - Uptime: %lu ms, Free heap: %d KB, WiFi: %s\n", 
                     drone_id, now, ESP.getFreeHeap() / 1024, 
                     wifi_connected ? "Connected" : "Disconnected");
        last_heartbeat = now;
    }
    
    // Check critical errors
    if (ESP.getFreeHeap() < 10000) {
        Serial.println("WARNING: Low memory!");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("=== CLOVER SWARM ESP-NOW BRIDGE ===");
    Serial.printf("Firmware Version: 1.0.0\n");
    Serial.printf("Build Date: %s %s\n", __DATE__, __TIME__);
    Serial.printf("Free heap: %d KB\n", ESP.getFreeHeap() / 1024);
    
#ifdef TEST_MODE
    Serial.println("*** TEST MODE ENABLED - Random Telemetry Generation ***");
#endif
    
    // Initialize watchdog early to prevent conflicts
    esp_task_wdt_init(WATCHDOG_TIMEOUT_S * 1000, true);
    esp_task_wdt_add(NULL);
    Serial.println("Watchdog initialized");
    
    // WiFi event handler is registered in OTAManager when needed
    
    // Load configuration (with improved error handling)
    loadConfiguration();
    
    // Initialize UART with production settings
    Serial.println("Initializing UART1...");
    Serial1.setRxBufferSize(4096);
    Serial1.setTxBufferSize(4096);
    
    Serial1.begin(921600, SERIAL_8N1, RX1_PIN, TX1_PIN);
    Serial.println("UART1 basic settings initialized");
    
    // Try to set hardware flow control
    if (RTS_PIN != -1 && CTS_PIN != -1) {
        if (Serial1.setPins(RX1_PIN, TX1_PIN, CTS_PIN, RTS_PIN)) {
            Serial1.setHwFlowCtrlMode(UART_HW_FLOWCTRL_CTS_RTS);
            Serial.printf("UART1 flow control enabled: RTS=%d, CTS=%d\n", RTS_PIN, CTS_PIN);
        } else {
            Serial.println("WARNING: Failed to set UART1 flow control pins");
        }
    }
    
    Serial.printf("UART1: 921600 baud, RX:%d TX:%d RTS:%d CTS:%d\n", 
                 RX1_PIN, TX1_PIN, RTS_PIN, CTS_PIN);
    
    // Initialize ESP-NOW with loaded configuration
    Serial.println("Initializing ESP-NOW...");
    int retry_count = 0;
    bool espnow_initialized = false;
    
    while (!espNowManager.init(espnow_config) && retry_count < 5) {
        Serial.printf("ESP-NOW init failed, retry %d/5\n", ++retry_count);
        delay(1000);
    }
    
    if (retry_count >= 5) {
        Serial.println("WARNING: ESP-NOW initialization failed after 5 retries!");
        Serial.println("Continuing without ESP-NOW...");
    } else {
        espnow_initialized = true;
        Serial.println("ESP-NOW initialized successfully");
    }
    
    // Initialize statistics
    stats.start_time = millis();
    stats.last_stats_time = stats.start_time;
    stats.uart.last_interval_start = stats.start_time;
    stats.espnow.last_interval_start = stats.start_time;
    
#ifdef TEST_MODE
    // Initialize telemetry generator for test mode
    TelemetryGenerator::init();
    Serial.println("TEST: Telemetry generator initialized");
#endif
    
    system_initialized = true;
    last_heartbeat = millis();
    
    Serial.printf("Drone %d initialized successfully\n", drone_id);
    Serial.printf("UART: 921600 baud, RX:%d TX:%d RTS:%d CTS:%d\n", 
                 RX1_PIN, TX1_PIN, RTS_PIN, CTS_PIN);
    Serial.println("WiFi: Disconnected (will connect only for OTA updates)");
    Serial.printf("ESP-NOW: %s\n", espnow_initialized ? "ENABLED" : "DISABLED");
    Serial.println("System ready for operation");
    Serial.println("=====================================");
}

void loop() {
    if (!system_initialized) {
        delay(100);
        return;
    }
    
    // Memory safety check
    if (ESP.getFreeHeap() < 5000) {
        Serial.println("CRITICAL: Very low memory, skipping loop iteration");
        delay(100);
        return;
    }
    
    // Process incoming UART data from ROS
    deserializer.processReceivedData();
    
#ifdef TEST_MODE
    // Send test telemetry packets
    sendTestTelemetry();
#endif
    
    // System health monitoring
    systemHealthCheck();
    
    // Print statistics less frequently in production
    static unsigned long last_stats = 0;
    static unsigned long last_debug = 0;
    unsigned long now = millis();
    
    if (now - last_stats >= 10000) { // Every 10 seconds
        stats.print();
#ifdef TEST_MODE
        Serial.printf("TEST: Total test packets sent: %lu\n", test_packets_sent);
        int8_t power = 0;
        esp_wifi_get_max_tx_power(&power);
        Serial.printf("DEBUG: esp_wifi_max_tx_power: %d\n", power);
#endif
        last_stats = now;
    }
    
    // Additional debug output every 30 seconds
    if (now - last_debug >= 30000) {
        Serial.printf("DEBUG: System running - Free heap: %d KB, Uptime: %lu ms\n", 
                     ESP.getFreeHeap() / 1024, now);
        last_debug = now;
    }
    
    // Small delay to prevent watchdog timeout
    delay(1);
}