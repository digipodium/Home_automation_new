# boot.py -- Connects ESP32 to WiFi on boot
import network
import time

# ============================================
#       WiFi Configuration
# ============================================
WIFI_SSID = "Digipodium_4G"         # <-- Replace with your WiFi name
WIFI_PASSWORD = "digipod@123"  # <-- Replace with your WiFi password

wifi_connected = False

def connect_wifi():
    """Connect to WiFi network and return the station interface."""
    global wifi_connected
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Disconnect if previously connected to a different network
    if wlan.isconnected():
        print("[WiFi] Already connected!")
        print("[WiFi] IP Address:", wlan.ifconfig()[0])
        wifi_connected = True
        return wlan
    
    print("[WiFi] Connecting to", WIFI_SSID, "...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    # Wait up to 20 seconds for connection
    timeout = 20
    while not wlan.isconnected() and timeout > 0:
        print(".", end="")
        time.sleep(1)
        timeout -= 1
    
    if wlan.isconnected():
        print("\n[WiFi] Connected successfully!")
        print("[WiFi] IP Address:", wlan.ifconfig()[0])
        print("[WiFi] Subnet:", wlan.ifconfig()[1])
        print("[WiFi] Gateway:", wlan.ifconfig()[2])
        print("[WiFi] DNS:", wlan.ifconfig()[3])
        wifi_connected = True
    else:
        print("\n[WiFi] Connection FAILED!")
        print("[WiFi] Check: SSID='{}' correct?".format(WIFI_SSID))
        print("[WiFi] Check: Is it a 2.4GHz network? (ESP32 does NOT support 5GHz)")
        print("[WiFi] Check: Password correct?")
        wifi_connected = False
    
    return wlan

# Connect on boot
wlan = connect_wifi()
