#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <AESLib.h>
#include <Base64.h>

#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

AESLib aesLib;

// --- Replace with your hotspot credentials ---
const char* ssid = "Galaxy S24 044E";
const char* password = "cwr8i9vi97nih3m";

// --- Replace with your PC hotspot IP running Flask ---
const char* serverUrl = "http://10.201.11.92:5000/api/upload";  // <-- PC hotspot IP

byte aes_key[] = "Sixteen byte key"; // 16 bytes

// ---------- PKCS7 padding ----------
String pad16(String msg) {
  int pad = 16 - (msg.length() % 16);
  for (int i = 0; i < pad; i++) msg += char(pad);
  return msg;
}

// ---------- AES ECB + Base64 Encryption ----------
String encryptAES(String msg) {
  msg = pad16(msg);
  int inputLen = msg.length();
  byte input[inputLen + 1];
  msg.getBytes(input, inputLen + 1);

  byte output[128];
  byte iv[16] = {0}; // ECB ignores IV

  int encLen = aesLib.encrypt(input, inputLen, output, aes_key, 128, iv);

  char b64[128];
  base64_encode(b64, (char*)output, encLen);
  return String(b64);
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  dht.begin();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry++;
    if(retry > 40){ // Timeout after ~20s
      Serial.println("\nFailed to connect to WiFi");
      return;
    }
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
}

// ---------- Main loop ----------
void loop() {
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println("Failed to read from DHT");
    delay(10000);
    return;
  }

  String tempStr = String(temp, 2);
  String humStr  = String(hum, 2);

  String encTemp = encryptAES(tempStr);
  String encHum  = encryptAES(humStr);

  Serial.println("Temp: " + tempStr + " | Encrypted: " + encTemp);
  Serial.println("Hum: " + humStr + " | Encrypted: " + encHum);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    String postData = "{\"temperature\":\"" + encTemp + "\",\"humidity\":\"" + encHum + "\"}";
    int code = http.POST(postData);

    if (code > 0) Serial.println("POST success: " + String(code));
    else Serial.println("POST failed: " + String(code) + " | " + http.errorToString(code).c_str());

    http.end();
  } else {
    Serial.println("WiFi disconnected, trying to reconnect...");
    WiFi.reconnect();
  }

  delay(10000); // Send data every 10s
}
