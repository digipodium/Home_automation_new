# main.py -- FINAL COMPLETE SYSTEM WITH DHT11

from umqtt.simple import MQTTClient
from machine import Pin, PWM, ADC
import time
import dht

# ============================================
# Adafruit IO
# ============================================
# AIO_USERNAME = "triple_m"
# AIO_KEY      = "aio_ekcg26P4h0Ej8ObLbd3akHB2VNiE"
AIO_USERNAME = "amanpandya77"
AIO_KEY      = "aio_dPYj26TU4AhKmDnMrMzEkLih9kGy"

AIO_SERVER   = "io.adafruit.com"
CLIENT_ID    = "esp32_home_auto"

FEED_RELAY1  = AIO_USERNAME + "/feeds/relay1"
FEED_RELAY2  = AIO_USERNAME + "/feeds/relay2"
FEED_RELAY3  = AIO_USERNAME + "/feeds/relay3"
FEED_RELAY4  = AIO_USERNAME + "/feeds/relay4"

FEED_SERVO   = AIO_USERNAME + "/feeds/servo"
FEED_DOOR    = AIO_USERNAME + "/feeds/door-status"

# ✅ NEW FEEDS
FEED_TEMP    = AIO_USERNAME + "/feeds/temperature"
FEED_HUM     = AIO_USERNAME + "/feeds/humidity"

# ============================================
# GPIO
# ============================================
relay1 = Pin(27, Pin.OUT, value=1)
relay2 = Pin(26, Pin.OUT, value=1)
relay3 = Pin(14, Pin.OUT, value=1)  # LDR CONTROLLED
relay4 = Pin(25, Pin.OUT, value=1)

servo  = PWM(Pin(13), freq=50)
ir     = Pin(33, Pin.IN)
ldr    = ADC(Pin(34))

# ✅ DHT11
dht_sensor = dht.DHT11(Pin(32))  # Change pin if needed

ldr.atten(ADC.ATTN_11DB)
ldr.width(ADC.WIDTH_12BIT)

# ============================================
# CONFIG
# ============================================
LDR_THRESHOLD = 500
DOOR_OPEN = 90
DOOR_CLOSE = 0

door_open = False
door_timer = 0
door_mode = "AUTO"

# ===== STATE TRACKING =====
last_states = {
    "relay1": None,
    "relay2": None,
    "relay3": None,
    "relay4": None,
    "door": None,
    "temp": None,
    "hum": None
}

# ============================================
# FUNCTIONS
# ============================================

def set_servo(angle):
    duty = int(26 + (angle / 180) * (128 - 26))
    servo.duty(duty)

def publish_if_changed(client, feed, key, value):
    if last_states[key] != value:
        try:
            client.publish(feed, str(value))
            print("[PUBLISH]", feed, "→", value)
            last_states[key] = value
        except:
            pass

def control_relay(pin, state):
    if state.upper() in ("1", "ON"):
        pin.value(0)
        return "1"
    else:
        pin.value(1)
        return "0"

def control_relay3(ldr_val):
    if ldr_val < LDR_THRESHOLD:
        relay3.value(0)
        return "0"
    else:
        relay3.value(1)
        return "1"

# ===== DOOR =====

def open_door(client, mode="AUTO"):
    global door_open, door_timer, door_mode

    if not door_open:
        print("[DOOR] Opening via", mode)
        set_servo(DOOR_OPEN)
        door_open = True
        door_mode = mode

        if mode == "AUTO":
            door_timer = time.time()

        client.publish(FEED_SERVO, "ON")

def close_door(client):
    global door_open

    if door_open:
        print("[DOOR] Closing")
        set_servo(DOOR_CLOSE)
        door_open = False

        client.publish(FEED_SERVO, "OFF")

# ============================================
# MQTT
# ============================================

def mqtt_callback(topic, msg):
    topic = topic.decode()
    msg = msg.decode().strip()

    print("[MQTT]", topic, msg)

    if topic == FEED_RELAY1:
        state = control_relay(relay1, msg)
        publish_if_changed(client, FEED_RELAY1, "relay1", state)

    elif topic == FEED_RELAY2:
        state = control_relay(relay2, msg)
        publish_if_changed(client, FEED_RELAY2, "relay2", state)

    elif topic == FEED_RELAY4:
        state = control_relay(relay4, msg)
        publish_if_changed(client, FEED_RELAY4, "relay4", state)

    # 🚪 SERVO CONTROL
    elif topic == FEED_SERVO:
        if msg.upper() in ("ON", "1"):
            open_door(client, mode="MANUAL")
        elif msg.upper() in ("OFF", "0"):
            close_door(client)

def connect():
    global client
    client = MQTTClient(
        CLIENT_ID,
        AIO_SERVER,
        user=AIO_USERNAME,
        password=AIO_KEY
    )
    client.set_callback(mqtt_callback)
    client.connect()

    client.subscribe(FEED_RELAY1)
    client.subscribe(FEED_RELAY2)
    client.subscribe(FEED_RELAY4)
    client.subscribe(FEED_SERVO)

    return client

# ============================================
# MAIN
# ============================================

def main():
    client = connect()

    while True:
        try:
            client.check_msg()

            # ===== LDR → RELAY3 =====
            ldr_val = ldr.read()
            relay3_state = control_relay3(ldr_val)

            # ===== IR → AUTO DOOR =====
            if ir.value() == 0:
                open_door(client, mode="AUTO")

            # ===== AUTO CLOSE =====
            if door_open and door_mode == "AUTO":
                if time.time() - door_timer > 5:
                    close_door(client)

            # ===== DHT11 SENSOR =====
            try:
                dht_sensor.measure()
                temp = dht_sensor.temperature()
                hum = dht_sensor.humidity()

                publish_if_changed(client, FEED_TEMP, "temp", temp)
                publish_if_changed(client, FEED_HUM, "hum", hum)

            except Exception as e:
                print("[DHT ERROR]", e)

            # ===== PUBLISH ONLY ON CHANGE =====
            publish_if_changed(client, FEED_RELAY3, "relay3", relay3_state)

            publish_if_changed(
                client,
                FEED_DOOR,
                "door",
                "ON" if door_open else "OFF"
            )

            time.sleep(0.5)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

# Run
main()