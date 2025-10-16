from ultralytics import YOLO
import cv2, easyocr, time, serial, threading, sys
import firebase_admin
from firebase_admin import credentials, db
from utils import check_ocr_output

# FIREBASE SETUP 
cred = credentials.Certificate('smart-gate-pi/firebase-service-account.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://smart-gate-app-landmark-uni-default-rtdb.europe-west1.firebasedatabase.app/'
})
db_ref = db.reference()

# Retry logic for Firebase writes
def set_firebase_data(ref, data, retries=3):
    for attempt in range(retries):
        try:
            ref.set(data)
            return
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(1)

# SERIAL SETUP
serial_lock = threading.Lock()
try:
    ser = serial.Serial('COM7', 9600, timeout=1)
    time.sleep(2)
    print("Serial connection established")
except Exception as e:
    print(f"Failed to open serial connection: {e}")
    sys.exit(1)

# START FIREBASE LISTENER THREAD 
def firebase_command_listener():
    command_ref = db_ref.child('gates/main-gate/command')

    def on_command_update(snapshot):
        command = snapshot.data
        if not command or 'action' not in command:
            print("No valid command received")
            return

        print(f"Received command from Firebase: {command}")
        try:
            action = command['action'].upper()
            with serial_lock:
                ser.write((action + '\n').encode())
                print(f"Sent to Arduino: {action}")

                start_time = time.time()
                while time.time() - start_time < 5:
                    if ser.in_waiting > 0:
                        response = ser.readline().decode().strip()
                        print(f"Arduino response: {response}")
                        break
                else:
                    raise Exception("No response from Arduino")

            status = 'open' if 'opened' in response.lower() else 'closed'
            db_ref.child('gates/main-gate/status').set(status)

            log_ref = db_ref.child('logs').push()
            log_ref.set({
                'plate': command.get('plate', 'manual'),
                'action': f"Gate {status}",
                'timestamp': int(time.time() * 1000),
                'userId': command.get('triggeredBy', 'unknown'),
                'success': True
            })

        except Exception as e:
            print(f"Error processing Firebase command: {e}")
            log_ref = db_ref.child('logs').push()
            log_ref.set({
                'plate': command.get('plate', 'manual'),
                'action': f"Gate {command.get('action', 'unknown')} failed",
                'timestamp': int(time.time() * 1000),
                'userId': command.get('triggeredBy', 'unknown'),
                'success': False
            })

    try:
        command_ref.listen(on_command_update)
    except Exception as e:
        print(f"Error setting up Firebase listener: {e}")
        sys.exit(1)

listener_thread = threading.Thread(target=firebase_command_listener, daemon=True)
listener_thread.start()

# YOLO MODEL
object_detection_model = YOLO('models\\license_plate_detector.pt')

# MAIN LOOP
print("Listening for vehicle detection from Arduino...")

try:
    while True:
        time.sleep(0.2)
        capture_time = time.localtime()
        year = capture_time.tm_year
        month = f'{capture_time.tm_mon:02d}'
        day = f'{capture_time.tm_mday:02d}'
        hour = f'{capture_time.tm_hour:02d}'
        minute = f'{capture_time.tm_min:02d}'
        second = f'{capture_time.tm_sec:02d}'

        with serial_lock:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
            else:
                line = None
        print(line)
        if line and line == 'DETECTED':
          print("Vehicle detected, capturing image...")

          camera = cv2.VideoCapture(0)
          if not camera.isOpened():
              print("Error: Could not open camera.")
              continue

          ret, frame = camera.read()
          if not ret:
              camera.release()
              print("Error: Failed to capture image.")
              continue

          image_path = f"captured\\image_{day}{month}{year}_{hour}{minute}{second}.jpg"
          cv2.imwrite(image_path, frame)
          camera.release()
          print(f"Image saved: {image_path}")

          detection = object_detection_model.predict(image_path, conf = 0.4, save=True)
          license_plates = detection[0].boxes.xyxy.tolist()

          if not license_plates:
              print("No license plate detected.")
              continue

          x1, y1, x2, y2 = map(int, license_plates[0])
          captured_image = cv2.imread(image_path, 0)
          plate_img_cropped = captured_image[y1:y2, x1:x2]

          w, h = x2 - x1, y2 - y1
          resized = cv2.resize(plate_img_cropped, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
          threshed = cv2.threshold(resized, 100, 255, cv2.THRESH_BINARY)[1]

          reader = easyocr.Reader(['en'], gpu=False)
          ocr_output = reader.readtext(threshed, detail=0)
          license_plate_number = check_ocr_output(ocr_output)

          print(f"OCR Result: {license_plate_number}")

          if license_plate_number:
              try:
                  plate_ref = db_ref.child(f'licensePlates/{license_plate_number}')
                  plate_data = plate_ref.get()
                  if plate_data and plate_data.get('allowed', False):
                      print(f"Plate {license_plate_number} is authorized")
                      timestamp = int(time.time() * 1000)

                      command_ref = db_ref.child('gates/main-gate/command')
                      set_firebase_data(command_ref, {
                          'action': 'open',
                          'timestamp': timestamp,
                          'triggeredBy': 'ANPR',
                          'plate': license_plate_number
                      })

                      log_ref = db_ref.child('logs').push()
                      set_firebase_data(log_ref, {
                          'plate': license_plate_number,
                          'action': 'Gate opened by ANPR',
                          'timestamp': timestamp,
                          'userId': 'ANPR',
                          'success': True
                      })

                      with serial_lock:
                          ser.write(b"OPEN\n")

                  else:
                      print(f"Unauthorized or unknown plate: {license_plate_number}")
                      log_ref = db_ref.child('logs').push()
                      set_firebase_data(log_ref, {
                          'plate': license_plate_number,
                          'action': 'Unauthorized plate attempt',
                          'timestamp': int(time.time() * 1000),
                          'userId': 'ANPR',
                          'success': False
                      })
              except Exception as e:
                  print(f"Error processing plate authorization: {e}")
          else:
              print("No valid plate detected")
        # ser.reset_input_buffer()      

except KeyboardInterrupt:
    print("\nProgram interrupted. Cleaning up...")
    ser.close()
    print("Serial port closed.")
    sys.exit(0)
except Exception as e:
    print(f"Unexpected error: {e}")
    ser.close()
    sys.exit(1)