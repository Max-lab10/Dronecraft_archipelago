#!/usr/bin/env python3
"""
Упрощенный скрипт тестирования ESP-NOW
Автоматически прошивает и тестирует ESP устройства
"""

import sys
import time
import logging
import subprocess
import re
import serial
import serial.tools.list_ports
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

# Добавляем путь к библиотекам skyros
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from esp_flasher import (
    ESPDevice, detect_esp_ports, flash_esp, 
    wait_for_esp_ready, test_espnow_communication
)

# Путь к ESP проекту (относительно корня проекта)
ESP_PROJECT_PATH = str(Path(__file__).parent.parent.parent / "esp")


@dataclass
class ESPTestResult:
    """Результат тестирования ESP устройства"""
    port: str
    success: bool
    tx_pps: float = 0.0
    rx_pps: float = 0.0
    packets_sent: int = 0
    packets_received: int = 0
    timestamp: float = 0.0


class SimpleESPTester:
    """Упрощенный класс для тестирования ESP устройств"""
    
    def __init__(self):
        self.logger = logging.getLogger("SimpleESPTester")
        self.master_esp: Optional[ESPDevice] = None
        self.test_results: List[ESPTestResult] = []
        self.used_ports: List[str] = []
        
        # Конфигурация тестирования
        self.test_duration = 30.0
        self.min_pps_threshold = 200.0  # Минимальный PPS для успешного теста
        self.test_environment = "lolin_s2_mini_test"
    
    def setup_logging(self, verbose: bool = False):
        """Настройка логирования"""
        level = logging.DEBUG if verbose else logging.INFO
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(console_handler)
        
        # Уменьшаем verbosity serial библиотеки
        logging.getLogger("serial").setLevel(logging.WARNING)
    
    def print_banner(self):
        """Вывод баннера"""
        print("=" * 60)
        print("УПРОЩЕННЫЙ ТЕСТЕР ESP-NOW")
        print("=" * 60)
        print("Этот скрипт:")
        print("1. Прошивает master ESP с тестовой прошивкой")
        print("2. Позволяет подключать и тестировать slave ESP устройства")
        print(f"3. Проверяет ESP-NOW связь (>= {self.min_pps_threshold} pps)")
        print("=" * 60)
    
    def select_port(self, available_ports: List[str], device_type: str) -> Optional[str]:
        """Интерактивный выбор порта"""
        if not available_ports:
            print(f"ОШИБКА: Не найдено последовательных портов для {device_type}")
            return None
        
        print(f"\nДоступные порты для {device_type}:")
        for i, port in enumerate(available_ports, 1):
            print(f"  {i}. {port}")
        
        while True:
            try:
                choice = input(f"Выберите порт для {device_type} (1-{len(available_ports)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(available_ports):
                    return available_ports[idx]
                else:
                    print("Неверный выбор, попробуйте снова.")
            except (ValueError, KeyboardInterrupt):
                print("Неверный ввод, введите число.")
    
    def setup_master_esp(self) -> bool:
        """Настройка и прошивка master ESP устройства"""
        print("\n" + "="*50)
        print("ШАГ 1: НАСТРОЙКА MASTER ESP")
        print("="*50)
        print("Подключите ОДНО ESP устройство, которое будет master.")
        print("Это устройство будет отправлять тестовые пакеты другим ESP устройствам.")
        
        input("Нажмите Enter когда master ESP подключен...")
        
        # Обнаружение портов
        ports = detect_esp_ports()
        master_port = self.select_port(ports, "Master ESP")
        if not master_port:
            return False
        
        # Прошивка master ESP
        print(f"\nПрошивка master ESP на {master_port}...")
        flash_success, actual_port = flash_esp(master_port, self.test_environment, esp_project_path=ESP_PROJECT_PATH)
        if not flash_success:
            print("ОШИБКА: Не удалось прошить master ESP")
            return False
        
        # Используем актуальный порт после прошивки
        if actual_port != master_port:
            print(f"Порт ESP изменился с {master_port} на {actual_port} после прошивки")
            master_port = actual_port
        else:
            print(f"Порт ESP остался тем же: {master_port}")
        
        # Отслеживаем master порт
        self.used_ports.append(master_port)
        
        # Ждем перезагрузки
        print("Ожидание перезагрузки ESP...")
        time.sleep(3)
        
        # Подключение к master ESP
        self.master_esp = ESPDevice(master_port, "Master")
        if not self.master_esp.connect():
            print("ОШИБКА: Не удалось подключиться к master ESP")
            return False
        
        # Ждем готовности ESP
        if not wait_for_esp_ready(self.master_esp, timeout=45):
            print("ОШИБКА: Master ESP не стал готовым")
            return False
        
        print("✓ Настройка master ESP завершена успешно!")
        return True
    
    def parse_espnow_rates(self, line: str) -> Optional[Tuple[float, float]]:
        """Парсинг ESP-NOW Rates из строки"""
        # Ищем паттерн "ESP-NOW Rates: TX=238.4 pps, RX=237.0 pps"
        pattern = r'ESP-NOW Rates: TX=([\d.]+) pps, RX=([\d.]+) pps'
        match = re.search(pattern, line)
        
        if match:
            tx_pps = float(match.group(1))
            rx_pps = float(match.group(2))
            return tx_pps, rx_pps
        
        return None
    
    def test_slave_esp(self, slave_port: str) -> bool:
        """Тестирование одного slave ESP устройства"""
        print(f"\nПрошивка slave ESP на {slave_port}...")
        
        # Прошивка slave ESP
        flash_success, actual_port = flash_esp(slave_port, self.test_environment, esp_project_path=ESP_PROJECT_PATH, exclude_ports=self.used_ports)
        if not flash_success:
            print(f"ОШИБКА: Не удалось прошить slave ESP на {slave_port}")
            return False
        
        # Используем актуальный порт после прошивки
        if actual_port != slave_port:
            print(f"Порт ESP изменился с {slave_port} на {actual_port} после прошивки")
            slave_port = actual_port
        else:
            print(f"Порт ESP остался тем же: {slave_port}")
        
        # Отслеживаем slave порт
        self.used_ports.append(slave_port)
        
        # Ждем перезагрузки
        print("Ожидание перезагрузки ESP...")
        time.sleep(3)
        
        # Подключение к slave ESP
        slave_esp = ESPDevice(slave_port, "Slave")
        if not slave_esp.connect():
            print(f"ОШИБКА: Не удалось подключиться к slave ESP на {slave_port}")
            return False
        
        # Ждем готовности ESP
        if not wait_for_esp_ready(slave_esp, timeout=45):
            print("ОШИБКА: Slave ESP не стал готовым")
            slave_esp.disconnect()
            return False
        
        # Запуск теста связи
        print(f"\n🔄 Запуск теста ESP-NOW связи...")
        print(f"Оба устройства будут отправлять пакеты, каждое должно получать >= {self.min_pps_threshold} pps")
        print(f"Целевая скорость: 250 пакетов в секунду на устройство")
        print(f"Длительность теста: {self.test_duration} секунд")
        
        success, results = test_espnow_communication(
            self.master_esp, slave_esp, 
            self.test_duration, int(self.min_pps_threshold)
        )
        
        # Сохраняем результаты
        test_result = ESPTestResult(
            port=slave_port,
            success=success,
            tx_pps=results.get('slave_tx_pps', 0.0),
            rx_pps=results.get('avg_slave_rx_pps', 0.0),  # Используем среднее RX PPS
            packets_sent=results.get('slave_sent', 0),
            packets_received=results.get('slave_received', 0),
            timestamp=time.time()
        )
        self.test_results.append(test_result)
        
        # Очистка
        slave_esp.disconnect()
        
        # Удаляем slave порт из used_ports
        if slave_port in self.used_ports:
            self.used_ports.remove(slave_port)
        
        # Вывод результата
        if success:
            print("✓ ТЕСТ ПРОЙДЕН! Двунаправленная ESP-NOW связь работает корректно.")
        else:
            print("✗ ТЕСТ ПРОВАЛЕН! Обнаружены проблемы с ESP-NOW связью.")
            if not results.get('master_success', True):
                print(f"  - Средняя скорость RX master слишком низкая: {results.get('avg_master_rx_pps', 0):.1f} pps")
            if not results.get('slave_success', True):
                print(f"  - Средняя скорость RX slave слишком низкая: {results.get('avg_slave_rx_pps', 0):.1f} pps")
        
        print(f"  Master: {results.get('master_sent', 0)} отправлено, {results.get('master_received', 0)} получено, TX={results.get('master_tx_pps', 0):.1f} pps, RX={results.get('master_rx_pps', 0):.1f} pps (среднее={results.get('avg_master_rx_pps', 0):.1f})")
        print(f"  Slave: {results.get('slave_sent', 0)} отправлено, {results.get('slave_received', 0)} получено, TX={results.get('slave_tx_pps', 0):.1f} pps, RX={results.get('slave_rx_pps', 0):.1f} pps (среднее={results.get('avg_slave_rx_pps', 0):.1f})")
        print(f"  Всего: {results.get('total_sent', 0)} отправлено, {results.get('total_received', 0)} получено")
        print(f"  Потери пакетов: {results.get('packet_loss_rate', 0):.1f}%")
        
        return success
    
    def interactive_testing_loop(self):
        """Интерактивный цикл для тестирования нескольких slave устройств"""
        print("\n" + "="*50)
        print("ШАГ 2: ТЕСТИРОВАНИЕ SLAVE ESP УСТРОЙСТВ")
        print("="*50)
        print("Теперь вы можете подключать и тестировать несколько ESP устройств.")
        print("Каждое устройство будет автоматически прошито и протестировано.")
        
        device_count = 0
        
        while True:
            device_count += 1
            print(f"\n--- Тестирование устройства #{device_count} ---")
            print("Подключите следующее ESP устройство для тестирования.")
            
            # Получаем текущие порты до подключения нового устройства
            ports_before = detect_esp_ports()
            
            try:
                input("Нажмите Enter когда ESP подключен (или Ctrl+C для завершения)...")
            except KeyboardInterrupt:
                print("\nТестирование завершено пользователем.")
                break
            
            ports_after = detect_esp_ports()
            
            # Обнаруживаем новые порты
            new_ports = [p for p in ports_after if p not in ports_before]
            available_ports = [p for p in new_ports if p not in self.used_ports]
            
            if not available_ports:
                print("Не обнаружено новых ESP портов. Подключите ESP устройство.")
                print(f"Порты до: {ports_before}")
                print(f"Порты после: {ports_after}")
                print(f"Используемые порты: {self.used_ports}")
                continue
            
            print(f"Обнаружены новые порты: {new_ports}")
            print(f"Доступные порты (исключая используемые): {available_ports}")
            
            slave_port = self.select_port(available_ports, f"Slave ESP #{device_count}")
            if not slave_port:
                print("Нет доступных портов, пропускаем...")
                continue
            
            # Тестируем slave устройство
            success = self.test_slave_esp(slave_port)
            
            # Спрашиваем, хочет ли пользователь продолжить
            print(f"\nТест устройства #{device_count} завершен.")
            try:
                continue_testing = input("Тестировать другое устройство? (y/n): ").lower().strip()
                if continue_testing not in ['y', 'yes', '']:
                    break
            except KeyboardInterrupt:
                break
    
    def print_summary(self):
        """Вывод сводки тестов"""
        print("\n" + "="*60)
        print("СВОДКА ТЕСТОВ")
        print("="*60)
        
        if not self.test_results:
            print("Устройства не тестировались.")
            return
        
        passed = sum(1 for r in self.test_results if r.success)
        total = len(self.test_results)
        
        print(f"Всего устройств протестировано: {total}")
        print(f"Пройдено: {passed}")
        print(f"Провалено: {total - passed}")
        print(f"Процент успеха: {(passed/total)*100:.1f}%")
        
        print("\nДетальные результаты:")
        print("-" * 120)
        print(f"{'Порт':<15} {'Статус':<8} {'TX_PPS':<10} {'RX_PPS':<10} {'Среднее_RX':<12} {'Отправлено':<12} {'Получено':<12} {'Потери%':<10}")
        print("-" * 120)
        
        for result in self.test_results:
            status = "ПРОЙДЕН" if result.success else "ПРОВАЛЕН"
            loss_rate = max(0, (result.packets_sent - result.packets_received) / max(result.packets_sent, 1)) * 100
            # Используем rx_pps как среднее значение
            avg_rx_pps = result.rx_pps
            print(f"{result.port:<15} {status:<8} {result.tx_pps:<10.1f} {result.rx_pps:<10.1f} {avg_rx_pps:<12.1f} "
                  f"{result.packets_sent:<12} {result.packets_received:<12} {loss_rate:<10.1f}")
        
        print("-" * 120)
    
    def cleanup(self):
        """Очистка ресурсов"""
        if self.master_esp:
            self.master_esp.disconnect()
    
    def run(self, verbose: bool = False):
        """Основной рабочий процесс тестирования"""
        self.setup_logging(verbose)
        self.print_banner()
        
        try:
            # Шаг 1: Настройка master ESP
            if not self.setup_master_esp():
                print("Не удалось настроить master ESP. Выход.")
                return False
            
            # Шаг 2: Интерактивный цикл тестирования
            self.interactive_testing_loop()
            
            # Шаг 3: Вывод сводки
            self.print_summary()
            
            return True
            
        except KeyboardInterrupt:
            print("\n\nТест прерван пользователем.")
            return False
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка: {e}")
            return False
        finally:
            self.cleanup()


def main():
    """Точка входа"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Упрощенный скрипт тестирования ESP-NOW",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python esp_simple_test.py                 # Запуск с настройками по умолчанию
  python esp_simple_test.py --verbose       # Запуск с подробным логированием
  python esp_simple_test.py --duration 60   # Запуск 60-секундных тестов
        """
    )
    
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true",
        help="Включить подробное логирование"
    )
    
    parser.add_argument(
        "--duration", 
        type=float, 
        default=30.0,
        help="Длительность теста в секундах (по умолчанию: 30)"
    )
    
    parser.add_argument(
        "--min-pps", 
        type=float, 
        default=200.0,
        help="Минимальный PPS для прохождения теста (по умолчанию: 200)"
    )
    
    parser.add_argument(
        "--environment", 
        default="lolin_s2_mini_test",
        help="PlatformIO окружение для использования (по умолчанию: lolin_s2_mini_test)"
    )
    
    args = parser.parse_args()
    
    # Создание и настройка тестера
    tester = SimpleESPTester()
    tester.test_duration = args.duration
    tester.min_pps_threshold = args.min_pps
    tester.test_environment = args.environment
    
    # Запуск теста
    success = tester.run(verbose=args.verbose)
    
    # Выход с соответствующим кодом
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 