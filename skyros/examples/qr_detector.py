import rospy
from std_msgs.msg import String

def read_string_from_topic(topic_name='/name_of_topic', timeout=5.0):
    try:
        msg = rospy.wait_for_message(topic_name, String, timeout=timeout)
        return msg.data 
    except rospy.exceptions.ROSException as e:
        rospy.logwarn(f"Не удалось получить сообщение: {e}")
        return None
    

# Пример использования (внутри уже запущенного узла)





def decoding_qr(qr_code):
    """Парсит QR-код и возвращает информацию"""
    if len(qr_code) != 6:
        raise ValueError("wrong format")
    
    recipe_id = int(qr_code[0])
    qr_position = int(qr_code[1])
    blocks = qr_code[2:6]
    
    recipes = {
        0: "pick",
        1: "axe", 
        2: "mace"
    }
    
    print(f"Recepie: {recipes.get(recipe_id, 'unknown')}")
    print(f"Position QR: {qr_position}")
    print(f"Blocks: {blocks}")
    
    return recipe_id, qr_position, blocks

# В main.py:
with Drone(network_id=0x52, wifi_channel=6) as drone:
    # Взлёт для сканирования
    drone.takeoff(z=1.5)
    drone.wait(2)
    
    # Сканирование QR-кода
    print("scanning...")
    qr_code = scan_qr_code()
    print(f"QR's found: {qr_code}")
    
    # Парсинг информации
    recipe_id, qr_position, blocks = decoding_qr(qr_code)