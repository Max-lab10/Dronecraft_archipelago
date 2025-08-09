#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_now.h"
#include "esp_crc.h"
#include "esp_timer.h"
#include "esp_mac.h"

static const char *TAG = "SIMPLE_CONTROLLER";

// Захардкоженные настройки
#define WIFI_SSID "RopraFi"
#define WIFI_PASSWORD "impreza555"
#define OTA_URL "http://192.168.0.14:8080/firmware/esp32.bin"
#define ESPNOW_CHANNEL 1
#define PACKET_TYPE_OTA_CONFIG 10
#define PACKET_PREAMBLE 0xAA55
#define NETWORK_ID 18


// Broadcast address
static const uint8_t broadcast_address[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Packet header structure (matching ESP drone expectations)
typedef struct {
    uint16_t preamble;
    uint8_t payload_size;
    uint8_t packet_type;
    uint8_t network_id;
} __attribute__((packed)) packet_header_t;

// OTA config packet structure (matching ESP drone expectations - 113 bytes)
typedef struct {
    packet_header_t header;
    uint8_t drone_id;
    uint8_t config_flags;  // Биты: 0=OTA, 1=WiFi, 2=Restart
    char ssid[24];         // Back to 24 bytes to match ESP drone's 113-byte size
    char password[32];
    char ota_url[48];
    uint16_t crc;
} __attribute__((packed)) ota_config_packet_t;

// Захардкоженные данные для отправки
static const char* HARDCODED_SSID = WIFI_SSID;  // 5 chars, fits in 22-byte field
static const char* HARDCODED_PASSWORD = WIFI_PASSWORD;
static const char* HARDCODED_OTA_URL = OTA_URL;

// ESP-NOW send callback
static void espnow_send_cb(const wifi_tx_info_t *tx_info, esp_now_send_status_t status)
{
    if (status == ESP_NOW_SEND_SUCCESS) {
        ESP_LOGI(TAG, "Packet sent successfully");
    } else {
        ESP_LOGW(TAG, "Failed to send packet");
    }
}

// ESP-NOW receive callback
static void espnow_recv_cb(const esp_now_recv_info *recv_info, const uint8_t *data, int len)
{
    ESP_LOGI(TAG, "Received packet from %02x:%02x:%02x:%02x:%02x:%02x, length: %d", 
             recv_info->src_addr[0], recv_info->src_addr[1], recv_info->src_addr[2],
             recv_info->src_addr[3], recv_info->src_addr[4], recv_info->src_addr[5], len);
}

// Calculate CRC16 for packet validation (matching ESP drone method)
static uint16_t calculate_crc16(const uint8_t* data, size_t len)
{
    if (!data || len < 3) return 0;
    
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len - 2; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// Initialize ESP-NOW (without WiFi connection)
static bool espnow_init(void)
{
    ESP_LOGI(TAG, "Initializing ESP-NOW");
    
    // Initialize WiFi infrastructure (required for ESP-NOW)
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    
    // Set WiFi to STA mode but don't connect to any network
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    
    // Initialize ESP-NOW
    ESP_ERROR_CHECK(esp_now_init());
    
    // Register callbacks
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_cb));
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv_cb));
    
    // Add peer for broadcast
    esp_now_peer_info_t peer_info = {
        .peer_addr = {0},
        .lmk = {0},
        .channel = ESPNOW_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
        .priv = NULL
    };
    memset(peer_info.peer_addr, 0xFF, 6); // Broadcast address
    ESP_ERROR_CHECK(esp_now_add_peer(&peer_info));
    
    ESP_LOGI(TAG, "ESP-NOW initialized successfully (WiFi in STA mode, no connection)");
    return true;
}

// Send OTA config packet
static bool send_ota_config_packet(uint8_t drone_id)
{
    ota_config_packet_t packet;
    memset(&packet, 0, sizeof(packet));
    
    // Fill header
    packet.header.preamble = PACKET_PREAMBLE;
    packet.header.packet_type = PACKET_TYPE_OTA_CONFIG;
    packet.header.network_id = NETWORK_ID;
    
    // Fill packet data
    packet.drone_id = drone_id;
    packet.config_flags = 0x03; // OTA + WiFi flags
    
    // Copy hardcoded strings
    strncpy(packet.ssid, HARDCODED_SSID, sizeof(packet.ssid) - 1);
    strncpy(packet.password, HARDCODED_PASSWORD, sizeof(packet.password) - 1);
    strncpy(packet.ota_url, HARDCODED_OTA_URL, sizeof(packet.ota_url) - 1);
    
    // Calculate payload size (excluding header only)
    // The ESP drone expects: sizeof(PacketHeader) + payload_size = total_size
    // So payload_size = total_size - sizeof(PacketHeader)
    // The payload includes all data except the header
    packet.header.payload_size = sizeof(packet) - sizeof(packet_header_t);
    
    // Calculate CRC (excluding CRC field itself)
    packet.crc = calculate_crc16((uint8_t*)&packet, sizeof(packet) - sizeof(packet.crc));
    
    ESP_LOGI(TAG, "Sending OTA_CONFIG packet to drone %d", drone_id);
    ESP_LOGI(TAG, "  SSID: %s", packet.ssid);
    ESP_LOGI(TAG, "  Password: %s", packet.password);
    ESP_LOGI(TAG, "  OTA URL: %s", packet.ota_url);
    ESP_LOGI(TAG, "  Payload size: %d", packet.header.payload_size);
    ESP_LOGI(TAG, "  Total packet size: %d", sizeof(packet));
    ESP_LOGI(TAG, "  Header size: %d", sizeof(packet_header_t));
    ESP_LOGI(TAG, "  CRC: 0x%04X", packet.crc);
    
    esp_err_t result = esp_now_send(broadcast_address, (uint8_t*)&packet, sizeof(packet));
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send OTA_CONFIG packet: %s", esp_err_to_name(result));
        return false;
    }
    
    return true;
}

// Main task that sends packets in loop
static void packet_sender_task(void *pvParameters)
{
    uint8_t drone_id = 1; // Начинаем с дрона ID 1
    uint32_t packet_count = 0;
    
    ESP_LOGI(TAG, "Starting packet sender task");
    
    while (1) {
        // Отправляем пакет каждые 2 секунды
        if (send_ota_config_packet(drone_id)) {
            packet_count++;
            ESP_LOGI(TAG, "Packet %lu sent to drone %d", packet_count, drone_id);
        }
        
        // Переходим к следующему дрону (1-10)
        drone_id++;
        if (drone_id > 10) {
            drone_id = 1;
        }
        
        // Ждем 200 секунды перед следующей отправкой
        vTaskDelay(pdMS_TO_TICKS(200000));
    }
}

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "=== SIMPLE ESP-NOW CONTROLLER ===");
    ESP_LOGI(TAG, "Firmware Version: 1.0.0");
    ESP_LOGI(TAG, "Build Date: %s %s", __DATE__, __TIME__);

    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Initialize ESP-NOW
    if (!espnow_init()) {
        ESP_LOGE(TAG, "Failed to initialize ESP-NOW");
        return;
    }

    ESP_LOGI(TAG, "Controller initialized successfully");
    ESP_LOGI(TAG, "Network ID: %d", NETWORK_ID);
    ESP_LOGI(TAG, "Channel: %d", ESPNOW_CHANNEL);
    ESP_LOGI(TAG, "Mode: ESP-NOW with WiFi STA (no network connection)");
    ESP_LOGI(TAG, "Starting packet sender task...");
    ESP_LOGI(TAG, "=====================================");

    // Create packet sender task
    xTaskCreate(packet_sender_task, "packet_sender", 4096, NULL, 5, NULL);
} 