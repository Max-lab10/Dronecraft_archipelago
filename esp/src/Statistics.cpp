#include "Statistics.h"

void Statistics::updatePPSAverages() {
    unsigned long current_time = millis();
    
    // Update PPS every second
    if (current_time - last_pps_update >= 1000) {
        // Calculate PPS for UART interface
        if (uart.last_interval_start > 0) {
            unsigned long interval_time = current_time - uart.last_interval_start;
            if (interval_time > 0) {
                uart.current_tx_pps = (uart.packets_sent_last_interval * 1000.0f) / interval_time;
                uart.current_rx_pps = (uart.packets_received_last_interval * 1000.0f) / interval_time;
                
                // Accumulate for averaging
                uart.avg_tx_pps += uart.current_tx_pps;
                uart.avg_rx_pps += uart.current_rx_pps;
                uart.pps_samples_count++;
            }
        }
        
        // Calculate PPS for ESP-NOW interface
        if (espnow.last_interval_start > 0) {
            unsigned long interval_time = current_time - espnow.last_interval_start;
            if (interval_time > 0) {
                espnow.current_tx_pps = (espnow.packets_sent_last_interval * 1000.0f) / interval_time;
                espnow.current_rx_pps = (espnow.packets_received_last_interval * 1000.0f) / interval_time;
                
                // Accumulate for averaging
                espnow.avg_tx_pps += espnow.current_tx_pps;
                espnow.avg_rx_pps += espnow.current_rx_pps;
                espnow.pps_samples_count++;
            }
        }
        
        // Reset interval counters and start new interval
        uart.packets_sent_last_interval = 0;
        uart.packets_received_last_interval = 0;
        espnow.packets_sent_last_interval = 0;
        espnow.packets_received_last_interval = 0;
        
        uart.last_interval_start = current_time;
        espnow.last_interval_start = current_time;
        
        last_pps_update = current_time;
    }
}

void Statistics::print() {
    unsigned long current_time = millis();
    unsigned long elapsed_time = current_time - start_time;
    unsigned long interval_time = current_time - last_stats_time;
    
    // Update PPS averages
    updatePPSAverages();
    
    if (interval_time >= 10000) { // Print every 10 seconds
        // Calculate averages for the period
        float uart_tx_avg = (uart.pps_samples_count > 0) ? uart.avg_tx_pps / uart.pps_samples_count : 0.0f;
        float uart_rx_avg = (uart.pps_samples_count > 0) ? uart.avg_rx_pps / uart.pps_samples_count : 0.0f;
        float espnow_tx_avg = (espnow.pps_samples_count > 0) ? espnow.avg_tx_pps / espnow.pps_samples_count : 0.0f;
        float espnow_rx_avg = (espnow.pps_samples_count > 0) ? espnow.avg_rx_pps / espnow.pps_samples_count : 0.0f;
        
        Serial.println("=== ESP32 BRIDGE STATISTICS ===");
        Serial.printf("Uptime: %lu ms\n", elapsed_time);
        
        // UART Statistics
        Serial.println("\n--- UART INTERFACE ---");
        Serial.printf("TX: %lu packets, %lu bytes\n", uart.packets_sent, uart.bytes_sent);
        Serial.printf("RX: %lu packets, %lu bytes, %lu corrupted\n", 
                     uart.packets_received, uart.bytes_received, uart.packets_corrupted);
        
        if (elapsed_time > 0) {
            Serial.printf("UART Rates: TX=%.1f pps, RX=%.1f pps\n", uart_tx_avg, uart_rx_avg);
        }
        
        if (uart.packets_received + uart.packets_corrupted > 0) {
            float uart_error_rate = (uart.packets_corrupted * 100.0f) / (uart.packets_received + uart.packets_corrupted);
            Serial.printf("UART Error Rate: %.2f%%\n", uart_error_rate);
        }
        
        // ESP-NOW Statistics
        Serial.println("\n--- ESP-NOW INTERFACE ---");
        Serial.printf("TX: %lu packets, %lu bytes\n", espnow.packets_sent, espnow.bytes_sent);
        Serial.printf("RX: %lu packets, %lu bytes, %lu corrupted\n", 
                     espnow.packets_received, espnow.bytes_received, espnow.packets_corrupted);
        
        if (elapsed_time > 0) {
            Serial.printf("ESP-NOW Rates: TX=%.1f pps, RX=%.1f pps\n", espnow_tx_avg, espnow_rx_avg);
        }
        
        if (espnow.packets_received + espnow.packets_corrupted > 0) {
            float espnow_error_rate = (espnow.packets_corrupted * 100.0f) / (espnow.packets_received + espnow.packets_corrupted);
            Serial.printf("ESP-NOW Error Rate: %.2f%%\n", espnow_error_rate);
        }
        
        Serial.println("================================");
        
        // Reset accumulated data for next period
        uart.avg_tx_pps = 0.0f;
        uart.avg_rx_pps = 0.0f;
        uart.pps_samples_count = 0;
        espnow.avg_tx_pps = 0.0f;
        espnow.avg_rx_pps = 0.0f;
        espnow.pps_samples_count = 0;
        
        last_stats_time = current_time;
    }
}