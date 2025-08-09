idf_component_register(SRCS "main.cpp"
                       INCLUDE_DIRS "."
                       REQUIRES console esp_wifi esp_netif nvs_flash json)
