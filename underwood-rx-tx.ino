const int ROW_PINS[] = {10, 9, 8, 7, 6, 5, 4, 3};
const int COL_PINS[] = {14, 15, 16, 17, 18, 19, 20, 21};
const int SHIFT_PIN = 2;
const int IR_PIN = 11;
const int PULSE_GAP_MS = 125;
const int DEBOUNCE_COUNT = 4;
const int DEBOUNCE_COUNT_READ = 8;

const int NUM_ROWS = sizeof(ROW_PINS) / sizeof(ROW_PINS[0]);
const int NUM_COLS = sizeof(COL_PINS) / sizeof(COL_PINS[0]);

unsigned long lastPulseTime[NUM_ROWS][NUM_COLS];
int debounceCounter[NUM_ROWS][NUM_COLS];

const char KEYS[8][8] = {
  {'\0', '1', '2', '3', '4', '6', '5', '\t'},
  {21, '\'', ';', 'l', 'k', 'j', 'h', '\0'},
  {'\0', '/', '.', ',', 'm', 'n', 'b', '\0'},
  {'\0', 'q', 'w', 'e', 'r', 't', '7', '\0'},
  {'\0', 'a', 's', 'd', 'f', 'y', '\0', '\0'},
  {'\0', '\0', 'p', 'o', 'i', 'u', 127, '\0'},
  {'\0', '=', '-', '0', '9', '8', '\r', 22},
  {'\0', 'z', 'x', 'c', 'v', 'g', ' ', '\0'}
};

const char SHIFT_KEYS[8][8] = {
  {'\0', '!', '@', '#', '$', '¢', '%', '\0'},
  {'\0', '"', ':', 'L', 'K', 'J', 'H', '\0'},
  {'\0', '?', '>', '<', 'M', 'N', 'B', '\0'},
  {'\0', 'Q', 'W', 'E', 'R', 'T', '&', '\0'},
  {'\0', 'A', 'S', 'D', 'F', 'Y', '\0', '\0'},
  {'\0', '\0', 'P', 'O', 'I', 'U', 26, '\0'},
  {'\0', '+', '_', ')', '(', '*', '\0', '\0'},
  {'\0', 'Z', 'X', 'C', 'V', 'G', '\0', '\0'}
};

bool isReceiving;
String outboundString = "";

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < NUM_ROWS; i++) {
    pinMode(ROW_PINS[i], INPUT_PULLUP);
    digitalWrite(ROW_PINS[i], HIGH);
    for (int j = 0; j < NUM_COLS; j++) {
      lastPulseTime[i][j] = 0;
      debounceCounter[i][j] = 0;
    }
  }

  for (int i = 0; i < NUM_COLS; i++) {
    pinMode(COL_PINS[i], INPUT_PULLUP);
    digitalWrite(COL_PINS[i], HIGH);
  }

  pinMode(SHIFT_PIN, INPUT_PULLUP);
  digitalWrite(SHIFT_PIN, HIGH);
  
  pinMode(IR_PIN, INPUT_PULLUP);
  digitalWrite(IR_PIN, HIGH);

  delay(2500);
  // The string to be sent
  String message = ". . . loading . . . ";
  // Send each character of the string with a delay of 0.2 seconds
  for (int i = 0; i < message.length(); i++) {
    sendCharacter(message[i]);
    delay(100);  // Delay between characters
  }
}

void loop() {

    // Only proceed with serial communication if the IR sensor is active
        if (Serial.available() > 0) {
            char character = Serial.read();
            sendCharacter(character);
        } else {
            scanKeyboard();
        }
}

void scanKeyboard() {
  bool shift = digitalRead(SHIFT_PIN) == LOW;

  for (int row = 0; row < NUM_ROWS; row++) {
    int rowState = digitalRead(ROW_PINS[row]);

    if (rowState == LOW) {
      for (int col = 0; col < NUM_COLS; col++) {
        int colState = digitalRead(COL_PINS[col]);

        if (colState == LOW) {
          unsigned long currentTime = millis();

          if (currentTime - lastPulseTime[row][col] > PULSE_GAP_MS) {
            debounceCounter[row][col]++;

            if (debounceCounter[row][col] == DEBOUNCE_COUNT_READ) {
              if (row == 6 && col == 6) {
                if (outboundString.length() > 0) {
                  Serial.println(outboundString);
                  outboundString = "";
                }
              } else {
                char key = shift ? SHIFT_KEYS[row][col] : KEYS[row][col];
                if (key == 21 || key == 22 || key == 127 || key == 26) {
                Serial.println(key);
                } else {
                outboundString += key;
                }
              }

              lastPulseTime[row][col] = currentTime;
            }
          }
        } else {
          debounceCounter[row][col] = 0;
        }
      }
    }
  }
}

void sendCharacter(char character) {
  int row = -1;
  int col = -1;
  bool shift = false;
  
  if(character == -1) {
    isReceiving = false;
  }
  
    // Handle special characters
  if (character == '\b') {  // Backspace
    row = 5;
    col = 6;
  } else if (character == '\r') {  // Carriage return
    row = 6;
    col = 6;
    
    if (digitalRead(IR_PIN) == HIGH) {
    while (digitalRead(IR_PIN) == HIGH) {
    	// wait for paper reload
    }
    delay(2500);
    }

  } else if (character == 30) {
    isReceiving = true;
    
    if (digitalRead(IR_PIN) == HIGH) {
    while (digitalRead(IR_PIN) == HIGH) {
    	// wait for paper reload
    }
    delay(2500);
    }

  } else if (character == 31) {
    isReceiving = false;
  } else {

  // Find the position of the character in the matrix
  for (int i = 0; i < 8; i++) {
    for (int j = 0; j < 8; j++) {
      if (KEYS[i][j] == character) {
        row = i;
        col = j;
        break;
      }
      else if (SHIFT_KEYS[i][j] == character) {
        row = i;
        col = j;
        shift = true;
        break;
      }
    }
    if (row != -1) break;
  }
  }
    
  if (row != -1 && col != -1) {
    // Assert the row and column pins
    for (int i = 0; i < DEBOUNCE_COUNT; i++) {
      if (shift) {
          pinMode(SHIFT_PIN, OUTPUT);
          digitalWrite(SHIFT_PIN, LOW);
      }
      
      while (digitalRead(COL_PINS[col]) == HIGH) {
        pinMode(ROW_PINS[row], OUTPUT);
        digitalWrite(ROW_PINS[row], HIGH);
      }
      
      // Wait for the column pin to go back HIGH
      while (digitalRead(COL_PINS[col]) == LOW) {
        pinMode(ROW_PINS[row], OUTPUT);
        digitalWrite(ROW_PINS[row], LOW);
      }
      
    }
    
    digitalWrite(ROW_PINS[row], HIGH);
    pinMode(ROW_PINS[row], INPUT_PULLUP);
    pinMode(SHIFT_PIN, INPUT_PULLUP);

    delay(100);
 
  }
}
