#include <WiFi.h>
#include <WebServer.h>

/* ================= WIFI ================= */
const char* ssid = "ESP32_Trolley";
const char* password = "12345678";
WebServer server(80);

/* ================= MOTOR PINS ================= */
#define IN1 4
#define IN2 5
#define IN3 6
#define IN4 7
#define ENA 15
#define ENB 16

/* ================= ULTRASONIC PINS ================= */
#define FR_TRIG 12
#define FR_ECHO 13

#define FL_TRIG 14
#define FL_ECHO 17

/* ================= ALERT PIN ================= */
#define LED_BUZZER_PIN 2

bool followMode = false;
bool hybridMode = false;

unsigned long lastFollowTime = 0;

String currentAction = "Idle";

/* ================= MOTOR ================= */
void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  currentAction = "STOP";
}

void forward() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  currentAction = "FORWARD";
}

void backward() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  currentAction = "BACKWARD";
}

void left() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  currentAction = "LEFT";
}

void right() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  currentAction = "RIGHT";
}

/* ================= ULTRASONIC ================= */
long readDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW); delayMicroseconds(2);
  digitalWrite(trigPin, HIGH); delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 30000);
  if (duration == 0) return 400;
  return duration * 0.034 / 2;
}

bool obstacleDetected() {
  long fl = readDistance(FL_TRIG, FL_ECHO);
  delay(30);
  long fr = readDistance(FR_TRIG, FR_ECHO);
  return (fl < 30 || fr < 30);
}

/* ================= ALERT ================= */
void triggerAlert() {
  digitalWrite(LED_BUZZER_PIN, HIGH);
  delay(200);
  digitalWrite(LED_BUZZER_PIN, LOW);
}

/* ================= DELAY EXECUTION ================= */
void runAction(void (*func)(), int ms) {
  func();
  delay(ms);
  stopMotors();
  delay(200);
}

/* ================= MACROS ================= */
void runCode(String code) {
  hybridMode = true;
  followMode = false;

  if (code == "6E2025") {
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 2000);
    runAction(right, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(backward, 2000);
    runAction(right, 600);
    stopMotors();
  }

  else if (code == "B885TZ") {
    runAction(right, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 2000);
    runAction(left, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 2000);
    stopMotors();
  }

  else if (code == "A1X9") {
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 1500);
    runAction(left, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 1500);
    stopMotors();
  }

  else if (code == "Z99K") {
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(backward, 2000);
    runAction(left, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 2000);
    stopMotors();
  }

  else if (code == "TROLLEY") {
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 1000);
    runAction(right, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(forward, 1000);
    runAction(left, 600);
    if (obstacleDetected()) { triggerAlert(); stopMotors(); hybridMode = false; return; }
    runAction(backward, 1000);
    stopMotors();
  }

  else {
    currentAction = "INVALID CODE";
  }

  hybridMode = false;
}

/* ================= WEB ================= */
void handleRoot() {
  String page = R"rawliteral(
  <!DOCTYPE html>
  <html>
  <head>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <style>
      body{background:#111;color:white;text-align:center;font-family:Arial;}
      button{width:120px;height:60px;margin:8px;font-size:18px;border-radius:12px;border:none;}
      .f{background:#4CAF50;}
      .b{background:#f44336;}
      .lr{background:#2196F3;}
      .s{background:#555;}
      .auto{background:#ff9800;width:200px;}
      input{padding:10px;font-size:16px;border-radius:10px;border:none;width:200px;}
    </style>
  </head>
  <body>

    <h2>ESP32 Trolley</h2>
    <h3 id="status">Status: Idle</h3>

    <button class="f" onclick="cmd('/F')">Forward</button><br>
    <button class="lr" onclick="cmd('/L')">Left</button>
    <button class="s" onclick="cmd('/S')">Stop</button>
    <button class="lr" onclick="cmd('/R')">Right</button><br>
    <button class="b" onclick="cmd('/B')">Backward</button><br><br>

    <button class="auto" onclick="cmd('/AUTO')">Follow Mode</button>

    <h3>Hybrid Mode</h3>
    <input id="code" placeholder="Enter Code">
    <button onclick="sendCode()">Run</button>

    <script>
      function cmd(c){ fetch(c); }

      function sendCode(){
        let c = document.getElementById("code").value;
        fetch("/code?val="+c);
      }

      setInterval(()=>{
        fetch("/status").then(r=>r.text()).then(t=>{
          document.getElementById("status").innerHTML="Status: "+t;
        });
      },500);

    </script>

  </body>
  </html>
  )rawliteral";

  server.send(200, "text/html", page);
}

/* ================= HANDLERS ================= */
void handleForward(){ followMode=false; hybridMode=false; forward(); server.send(200); }
void handleBackward(){ followMode=false; hybridMode=false; backward(); server.send(200); }
void handleLeft(){ followMode=false; hybridMode=false; left(); server.send(200); }
void handleRight(){ followMode=false; hybridMode=false; right(); server.send(200); }
void handleStop(){ followMode=false; hybridMode=false; stopMotors(); server.send(200); }
void handleAuto(){ followMode=true; hybridMode=false; server.send(200); }

void handleCode(){
  String code = server.arg("val");
  runCode(code);
  server.send(200,"text/plain","OK");
}

void handleStatus(){
  server.send(200,"text/plain",currentAction);
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);

  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);

  pinMode(FL_TRIG, OUTPUT); pinMode(FL_ECHO, INPUT);
  pinMode(FR_TRIG, OUTPUT); pinMode(FR_ECHO, INPUT);
  pinMode(LED_BUZZER_PIN, OUTPUT);

  digitalWrite(ENA, HIGH);
  digitalWrite(ENB, HIGH);
  stopMotors();

  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);

  Serial.println("WiFi Started");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/F", handleForward);
  server.on("/B", handleBackward);
  server.on("/L", handleLeft);
  server.on("/R", handleRight);
  server.on("/S", handleStop);
  server.on("/AUTO", handleAuto);
  server.on("/code", handleCode);
  server.on("/status", handleStatus);

  server.begin();
}

/* ================= LOOP ================= */
void loop() {
  server.handleClient();

  if (followMode && !hybridMode && millis() - lastFollowTime > 150) {
    lastFollowTime = millis();

    long fr = readDistance(FR_TRIG, FR_ECHO);
    delay(30);
    long fl = readDistance(FL_TRIG, FL_ECHO);

    // Obstacle check — stop and alert, stay in follow mode
    if (fl < 30 || fr < 30) {
      stopMotors();
      triggerAlert();
      return;
    }

    if (fr < 25) { left(); return; }
    if (fl < 25) { right(); return; }

    long front = (fr + fl) / 2;
    if (front > 30) forward();
    else stopMotors();
  }
}