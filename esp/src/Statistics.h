#ifndef STATISTICS_H
#define STATISTICS_H

#include <Arduino.h>

struct InterfaceStats {
    unsigned long packets_sent = 0;
    unsigned long packets_received = 0;
    unsigned long packets_corrupted = 0;
    unsigned long bytes_sent = 0;
    unsigned long bytes_received = 0;
    
    // For PPS calculation - packets in last interval
    unsigned long packets_sent_last_interval = 0;
    unsigned long packets_received_last_interval = 0;
    unsigned long last_interval_start = 0;
    
    // PPS values for averaging during statistics output
    float current_tx_pps = 0.0f;
    float current_rx_pps = 0.0f;
    float avg_tx_pps = 0.0f;
    float avg_rx_pps = 0.0f;
    unsigned long pps_samples_count = 0;
    
    struct {
        unsigned long packets_sent = 0;
        unsigned long packets_received = 0;
        unsigned long bytes_sent = 0;
        unsigned long bytes_received = 0;
    } by_type[9];
};

struct Statistics {
    InterfaceStats uart;
    InterfaceStats espnow;
    unsigned long start_time = 0;
    unsigned long last_stats_time = 0;
    unsigned long last_pps_update = 0;

    void print();
    void updatePPSAverages();
};

#endif // STATISTICS_H