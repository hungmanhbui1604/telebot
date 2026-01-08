import paho.mqtt.client as mqtt
import json
import time
import random
import threading

# ================= CONFIGURATION =================
MQTT_BROKER = "localhost"  # Or "127.0.0.1" if running locally
MQTT_PORT = 1883
DEVICE_ID = "esp32_01"
MQTT_USERNAME = ""  # Leave empty if not used
MQTT_PASSWORD = ""

# Topics (Must match your Telebot and ESP32 code)
TOPIC_PUB_FLAME  = "fire_alarm/esp32_01/sensor/flame"
TOPIC_PUB_GAS    = "fire_alarm/esp32_01/sensor/gas"
TOPIC_PUB_STATE  = "fire_alarm/esp32_01/sensor/state"
TOPIC_SUB_BUZZER = "fire_alarm/esp32_01/control/buzzer"
TOPIC_SUB_VALVE  = "fire_alarm/esp32_01/control/valve"

# Global States
buzzer_state = False
valve_state = False
current_mode = "AUTO"  # Just for display

# ================= MQTT CALLBACKS =================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ [Virtual ESP32] Connected to Broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_SUB_BUZZER)
        client.subscribe(TOPIC_SUB_VALVE)
    else:
        print(f"❌ [Virtual ESP32] Connection Failed code={rc}")

def on_message(client, userdata, msg):
    global buzzer_state, valve_state, current_mode
    payload = msg.payload.decode()
    topic = msg.topic

    print(f"\n📩 [Command Received] Topic: {topic} | Payload: {payload}")

    # Logic mimicking ESP32 callback
    if topic == TOPIC_SUB_BUZZER:
        if payload == "ON":
            buzzer_state = True
            print("🔊 BUZZER turned ON")
        elif payload == "OFF":
            buzzer_state = False
            print("🔇 BUZZER turned OFF")
            
    elif topic == TOPIC_SUB_VALVE:
        if payload == "ON":
            valve_state = True
            print("🚰 VALVE turned OPEN")
        elif payload == "OFF":
            valve_state = False
            print("🔒 VALVE turned CLOSED")
    
    # Simulate the "Manual Mode" trigger from ESP32
    current_mode = "MANUAL (10s)"
    
    # Immediately publish updated state (like ESP32 lines 97-106)
    publish_state(client)

# ================= HELPER FUNCTIONS =================
def publish_state(client):
    """Publishes the current Buzzer/Valve state"""
    payload = {
        "device_id": DEVICE_ID,
        "timestamp": int(time.time()),
        "BUZZER_State": buzzer_state,
        "VALVE_State": valve_state
    }
    client.publish(TOPIC_PUB_STATE, json.dumps(payload))
    # print(f"📤 [State Sent] {json.dumps(payload)}")

def simulation_loop(client):
    """Simulates sensor readings changing over time"""
    print("🚀 Simulation Started. Press Ctrl+C to stop.")
    print("   - Normal state for 10 seconds...")
    
    counter = 0
    
    while True:
        timestamp = int(time.time())
        
        # --- 1. SIMULATE SENSOR VALUES ---
        # Default: Safe (1 = High/Safe for DO pins in your logic)
        flame_do = 1 
        flame_ao = random.randint(3000, 4095) # High value = Safe
        
        gas_do = 1
        gas_ao = random.randint(0, 1000)      # Low value = Safe

        # TRIGGER ALARM EVENT periodically (every 15-20 seconds)
        if 15 <= counter % 30 <= 20: 
            print("⚠️ [SIMULATION] GENERATING FIRE ALARM!")
            flame_do = 0              # 0 = Fire Detected
            flame_ao = 500            # Low analog value
            
        if 25 <= counter % 30 <= 28:
            print("⚠️ [SIMULATION] GENERATING GAS LEAK!")
            gas_do = 0                # 0 = Gas Detected
            gas_ao = 3500             # High analog value

        # --- 2. PUBLISH FLAME DATA ---
        flame_json = {
            "device_id": DEVICE_ID,
            "timestamp": timestamp,
            "DO_State": flame_do,
            "AO_Value": flame_ao
        }
        client.publish(TOPIC_PUB_FLAME, json.dumps(flame_json))

        # --- 3. PUBLISH GAS DATA ---
        gas_json = {
            "device_id": DEVICE_ID,
            "timestamp": timestamp,
            "DO_State": gas_do,
            "AO_Value": gas_ao
        }
        client.publish(TOPIC_PUB_GAS, json.dumps(gas_json))

        # --- 4. PUBLISH STATE DATA ---
        # (ESP32 publishes state every loop too)
        publish_state(client)

        time.sleep(1) # Loop every 1 second
        counter += 1

# ================= MAIN =================
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Background thread for listening
        
        simulation_loop(client) # Main thread for publishing

    except KeyboardInterrupt:
        print("\n🛑 Simulation Stopped")
        client.loop_stop()
    except Exception as e:
        print(f"Error: {e}")