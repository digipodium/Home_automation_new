# main.py -- Full Home Automation System for ESP32
# Controls: 4 Relays, Servo, DHT11, LDR, Auto LED, Auto Fan
# Platform: Adafruit IO via MQTT

from umqtt.simple import MQTTClient
from machine import Pin, PWM, ADC
import network
import dht
import time
import gc

# ============================================
#       Adafruit IO Configuration
# ============================================
AIO_USERNAME = "amanpandya77"
AIO_KEY      = "aio_OzFJ46Z9VnK0iihDiZW0ld9W9ENu"

AIO_SERVER   = "io.adafruit.com"
AIO_PORT     = 1883
CLIENT_ID    = "esp32_home_auto"

# ============================================
#   Adafruit IO Feed Names
#   Create ALL these feeds on your dashboard
# ============================================
# Relay feeds (receive commands)
FEED_RELAY1  = AIO_USERNAME + "/feeds/relay1"
FEED_RELAY2  = AIO_USERNAME + "/feeds/relay2"
FEED_RELAY3  = AIO_USERNAME + "/feeds/relay3"
FEED_RELAY4  = AIO_USERNAME + "/feeds/relay4"

# Servo feed (receive angle 0-180)
FEED_SERVO   = AIO_USERNAME + "/feeds/servo"

# Sensor feeds (publish data TO Adafruit IO)
FEED_TEMP    = AIO_USERNAME + "/feeds/temperature"
FEED_HUMID   = AIO_USERNAME + "/feeds/humidity"
FEED_LDR     = AIO_USERNAME + "/feeds/ldr"

# Auto-control status feeds (publish status TO Adafruit IO)
FEED_FAN_STATUS = AIO_USERNAME + "/feeds/fan-status"
FEED_LED_STATUS = AIO_USERNAME + "/feeds/led-status"

# ============================================
#   GPIO PIN MAPPING
# ============================================
#   Component       | GPIO | Type
#   ----------------+------+--------
#   Relay 1         |  26  | Output
#   Relay 2         |  27  | Output
#   Relay 3         |  14  | Output
#   Relay 4         |  12  | Output
#   Servo Motor     |  13  | PWM Out
#   DHT11 Sensor    |   4  | Digital In
#   LDR Sensor      |  34  | Analog In (ADC)
#   LED (auto/LDR)  |   5  | Output
#   Fan (auto/DHT)  |  18  | Output
#   Onboard LED     |   2  | Output
# ============================================

# --- Relay Pins (Active LOW) ---
RELAY1_PIN = 26
RELAY2_PIN = 27
RELAY3_PIN = 14
RELAY4_PIN = 12

relay1 = Pin(RELAY1_PIN, Pin.OUT, value=1)  # OFF
relay2 = Pin(RELAY2_PIN, Pin.OUT, value=1)  # OFF
relay3 = Pin(RELAY3_PIN, Pin.OUT, value=1)  # OFF
relay4 = Pin(RELAY4_PIN, Pin.OUT, value=1)  # OFF

# --- Servo Motor (PWM on GPIO 13) ---
SERVO_PIN = 13
servo_pwm = PWM(Pin(SERVO_PIN), freq=50)  # 50Hz for servo
servo_pwm.duty(0)  # Start at 0 (no signal)

# --- DHT11 Temperature & Humidity Sensor ---
DHT_PIN = 4
dht_sensor = dht.DHT11(Pin(DHT_PIN))

# --- LDR Sensor (Analog input) ---
LDR_PIN = 34
ldr_adc = ADC(Pin(LDR_PIN))
ldr_adc.atten(ADC.ATTN_11DB)   # Full range: 0-3.3V
ldr_adc.width(ADC.WIDTH_12BIT) # 12-bit resolution: 0-4095

# --- LED controlled by LDR (auto light) ---
LED_PIN = 5
auto_led = Pin(LED_PIN, Pin.OUT, value=0)  # OFF

# --- Fan controlled by DHT11 (auto fan) ---
FAN_PIN = 18
auto_fan = Pin(FAN_PIN, Pin.OUT, value=0)  # OFF

# --- Onboard LED for status ---
led = Pin(2, Pin.OUT, value=0)

# ============================================
#   Auto-control Thresholds
# ============================================
LDR_DARK_THRESHOLD = 1000    # Below this = dark = LED ON (adjust as needed)
TEMP_FAN_THRESHOLD = 30      # Above this °C = fan ON (adjust as needed)

# ============================================
#   Feed-to-Relay Mapping
# ============================================
feed_relay_map = {
    FEED_RELAY1: relay1,
    FEED_RELAY2: relay2,
    FEED_RELAY3: relay3,
    FEED_RELAY4: relay4,
}

relay_names = {
    FEED_RELAY1: "Relay 1",
    FEED_RELAY2: "Relay 2",
    FEED_RELAY3: "Relay 3",
    FEED_RELAY4: "Relay 4",
}


# ============================================
#   Helper Functions
# ============================================

def blink_led(times=3, delay=0.15):
    """Blink onboard LED for visual feedback."""
    for _ in range(times):
        led.value(1)
        time.sleep(delay)
        led.value(0)
        time.sleep(delay)


def set_servo_angle(angle):
    """
    Move servo to specified angle (0-180 degrees).
    Servo PWM: duty 26 (~0.5ms) = 0°, duty 128 (~2.5ms) = 180°
    """
    angle = max(0, min(180, int(angle)))
    # Map 0-180 to duty cycle 26-128 (for 50Hz PWM)
    duty = int(26 + (angle / 180) * (128 - 26))
    servo_pwm.duty(duty)
    print("[SERVO] Angle set to: {}°  (duty={})".format(angle, duty))


def control_relay(relay_pin, state, name="Relay"):
    """Control relay: '1'/'ON' = ON, '0'/'OFF' = OFF (active LOW)."""
    state_str = state.upper().strip()
    
    if state_str in ("1", "ON"):
        relay_pin.value(0)   # LOW = ON for active-low relay
        print("[RELAY] {} -> ON".format(name))
        blink_led(1)
    elif state_str in ("0", "OFF"):
        relay_pin.value(1)   # HIGH = OFF for active-low relay
        print("[RELAY] {} -> OFF".format(name))
        blink_led(2)
    else:
        print("[RELAY] {} -> Unknown command: '{}'".format(name, state))


def read_dht11():
    """Read temperature and humidity from DHT11. Returns (temp, humidity) or (None, None)."""
    try:
        dht_sensor.measure()
        temp = dht_sensor.temperature()  # °C
        humid = dht_sensor.humidity()    # %
        print("[DHT11] Temp: {}°C  Humidity: {}%".format(temp, humid))
        return temp, humid
    except OSError as e:
        print("[DHT11] Read error: {}".format(e))
        return None, None


def read_ldr():
    """Read LDR analog value. Returns 0-4095 (low = bright, high = dark)."""
    value = ldr_adc.read()
    print("[LDR] Light level: {} (0=bright, 4095=dark)".format(value))
    return value


def auto_control_led(ldr_value):
    """Automatically turn LED ON when dark, OFF when bright."""
    if ldr_value < LDR_DARK_THRESHOLD:
        # Bright - LED OFF
        if auto_led.value() != 0:
            auto_led.value(0)
            print("[AUTO-LED] Bright detected -> LED OFF")
        return "0"
    else:
        # Dark - LED ON
        if auto_led.value() != 1:
            auto_led.value(1)
            print("[AUTO-LED] Dark detected -> LED ON")
        return "1"


def auto_control_fan(temperature):
    """Automatically turn fan ON when temperature exceeds threshold."""
    if temperature is None:
        return "0"
    
    if temperature >= TEMP_FAN_THRESHOLD:
        if auto_fan.value() != 1:
            auto_fan.value(1)
            print("[AUTO-FAN] Temp {}°C >= {}°C -> FAN ON".format(temperature, TEMP_FAN_THRESHOLD))
        return "1"
    else:
        if auto_fan.value() != 0:
            auto_fan.value(0)
            print("[AUTO-FAN] Temp {}°C < {}°C -> FAN OFF".format(temperature, TEMP_FAN_THRESHOLD))
        return "0"


# ============================================
#   MQTT Functions
# ============================================

def mqtt_callback(topic, msg):
    """Handle incoming MQTT messages from Adafruit IO."""
    topic = topic.decode("utf-8")
    msg = msg.decode("utf-8")
    
    print("\n[MQTT] Received: topic='{}' msg='{}'".format(topic, msg))
    
    # Relay control
    if topic in feed_relay_map:
        relay_pin = feed_relay_map[topic]
        name = relay_names.get(topic, "Unknown")
        control_relay(relay_pin, msg, name)
    
    # Servo control
    elif topic == FEED_SERVO:
        try:
            angle = int(float(msg))
            set_servo_angle(angle)
        except ValueError:
            print("[SERVO] Invalid angle: '{}'".format(msg))
    
    else:
        print("[MQTT] Unrecognized feed: {}".format(topic))


def wait_for_wifi():
    """Wait until WiFi is connected."""
    wlan = network.WLAN(network.STA_IF)
    
    if wlan.isconnected():
        print("[MAIN] WiFi connected: {}".format(wlan.ifconfig()[0]))
        return True
    
    print("[MAIN] Waiting for WiFi...")
    for i in range(30):
        if wlan.isconnected():
            print("\n[MAIN] WiFi connected: {}".format(wlan.ifconfig()[0]))
            return True
        print(".", end="")
        time.sleep(1)
    
    print("\n[MAIN] ERROR: No WiFi! Check boot.py credentials.")
    return False


def connect_adafruit():
    """Connect to Adafruit IO and subscribe to control feeds."""
    print("\n[MQTT] Connecting to Adafruit IO...")
    print("[MQTT] Server: {}:{}".format(AIO_SERVER, AIO_PORT))
    print("[MQTT] Username: {}".format(AIO_USERNAME))
    
    client = MQTTClient(
        CLIENT_ID,
        AIO_SERVER,
        port=AIO_PORT,
        user=AIO_USERNAME,
        password=AIO_KEY,
        keepalive=60
    )
    
    client.set_callback(mqtt_callback)
    
    try:
        client.connect()
    except OSError as e:
        print("[MQTT] Connection FAILED: {}".format(e))
        print("[MQTT] Check: Internet access? AIO credentials?")
        raise
    
    print("[MQTT] Connected to Adafruit IO!")
    
    # Subscribe to command feeds (relays + servo)
    subscribe_feeds = [
        FEED_RELAY1, FEED_RELAY2, FEED_RELAY3, FEED_RELAY4,
        FEED_SERVO
    ]
    for feed in subscribe_feeds:
        client.subscribe(feed)
        print("[MQTT] Subscribed: {}".format(feed))
    
    blink_led(5, 0.1)
    return client


def publish_sensor_data(client, temp, humid, ldr_value, fan_status, led_status):
    """Publish sensor readings to Adafruit IO feeds."""
    try:
        if temp is not None:
            client.publish(FEED_TEMP, str(temp))
            print("[PUB] Temperature: {}°C".format(temp))
            time.sleep(1)  # Adafruit IO rate limit (free: 30/min)
        
        if humid is not None:
            client.publish(FEED_HUMID, str(humid))
            print("[PUB] Humidity: {}%".format(humid))
            time.sleep(1)
        
        client.publish(FEED_LDR, str(ldr_value))
        print("[PUB] LDR: {}".format(ldr_value))
        time.sleep(1)
        
        client.publish(FEED_FAN_STATUS, fan_status)
        print("[PUB] Fan Status: {}".format("ON" if fan_status == "1" else "OFF"))
        time.sleep(1)
        
        client.publish(FEED_LED_STATUS, led_status)
        print("[PUB] LED Status: {}".format("ON" if led_status == "1" else "OFF"))
        
    except OSError as e:
        print("[PUB] Publish error: {}".format(e))
        raise


# ============================================
#   MAIN LOOP
# ============================================

def main():
    print("\n" + "=" * 50)
    print("  ESP32 Home Automation System")
    print("  Adafruit IO MQTT - Full Edition")
    print("=" * 50)
    print("\n--- Pin Mapping ---")
    print("  Relay 1      -> GPIO {}".format(RELAY1_PIN))
    print("  Relay 2      -> GPIO {}".format(RELAY2_PIN))
    print("  Relay 3      -> GPIO {}".format(RELAY3_PIN))
    print("  Relay 4      -> GPIO {}".format(RELAY4_PIN))
    print("  Servo Motor  -> GPIO {}".format(SERVO_PIN))
    print("  DHT11 Sensor -> GPIO {}".format(DHT_PIN))
    print("  LDR Sensor   -> GPIO {} (ADC)".format(LDR_PIN))
    print("  Auto LED     -> GPIO {}".format(LED_PIN))
    print("  Auto Fan     -> GPIO {}".format(FAN_PIN))
    print("\n--- Thresholds ---")
    print("  LDR Dark     : < {} -> LED ON".format(LDR_DARK_THRESHOLD))
    print("  Temp High    : > {}°C -> Fan ON".format(TEMP_FAN_THRESHOLD))
    print()
    
    # Step 1: Ensure WiFi
    if not wait_for_wifi():
        print("\n[MAIN] HALTED - Fix WiFi in boot.py and reset.")
        return
    
    client = None
    last_sensor_read = 0
    SENSOR_INTERVAL = 10  # Read sensors every 10 seconds
    
    while True:
        try:
            # Connect to Adafruit IO if needed
            if client is None:
                client = connect_adafruit()
                print("\n[MAIN] System ready! Listening for commands...\n")
            
            # Check for incoming MQTT commands
            client.check_msg()
            
            # Read sensors and auto-control at intervals
            now = time.time()
            if now - last_sensor_read >= SENSOR_INTERVAL:
                last_sensor_read = now
                
                print("\n--- Sensor Reading ---")
                
                # Read DHT11
                temp, humid = read_dht11()
                
                # Read LDR
                ldr_value = read_ldr()
                
                # Auto-control LED based on LDR
                led_status = auto_control_led(ldr_value)
                
                # Auto-control Fan based on temperature
                fan_status = auto_control_fan(temp)
                
                # Publish all sensor data to Adafruit IO
                publish_sensor_data(client, temp, humid, ldr_value, fan_status, led_status)
                
                print("--- End Reading ---\n")
            
            time.sleep(0.1)
            gc.collect()
            
        except OSError as e:
            print("\n[ERROR] Connection lost: {}".format(e))
            print("[MAIN] Reconnecting in 5 seconds...")
            client = None
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n[MAIN] Shutting down...")
            for r in [relay1, relay2, relay3, relay4]:
                r.value(1)  # Relays OFF
            auto_led.value(0)    # LED OFF
            auto_fan.value(0)    # Fan OFF
            servo_pwm.duty(0)    # Servo stop signal
            if client:
                client.disconnect()
            print("[MAIN] All devices OFF. Goodbye!")
            break


# Run
main()