import cv2
import pytesseract
import numpy as np
import re
from ultralytics import YOLO

# -----------------------------
# 1. SETUP TESSERACT PATH
# -----------------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# -----------------------------
# 2. SMART PLATE CORRECTION
# -----------------------------
def fix_indian_plate(text):
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    
    if len(text) < 7:
        return text

    num_map = {'O':'0','Q':'0','Z':'2','I':'1','L':'1','S':'5','B':'8','G':'6','T':'7'}
    char_map = {'0':'O','1':'I','2':'Z','8':'B','5':'S','6':'G'}

    def fix_part(part, mapping):
        return ''.join(mapping.get(c, c) for c in part)

    try:
        state = fix_part(text[:2], char_map)
        
        # State Code Enforcement (Failsafe)
        if state == "TH": state = "TN"
        elif state == "MH" and text[0] == 'N': state = "MH" 
        
        if len(text) >= 9:
            district = fix_part(text[2:4], num_map)
            number = fix_part(text[-4:], num_map)
            series = fix_part(text[4:-4], char_map)
            return f"{state} {district} {series} {number}"
        return text
    except:
        return text

# -----------------------------
# 3. INITIALIZE YOLO
# -----------------------------
model = YOLO("best.pt")

# -----------------------------
# 4. LOAD IMAGE
# -----------------------------
img_path = "2.jpeg" # Make sure this matches your image name
img = cv2.imread(img_path)

if img is None:
    print(f"Error: Could not load image {img_path}")
    exit()

h, w = img.shape[:2]
results = model(img)

print("\n--- Starting Detection & OCR ---")

for r in results:
    for box in r.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # A. TIGHT CROP
        px = int((x2 - x1) * 0.05)
        py = int((y2 - y1) * 0.05)
        plate = img[max(0, y1-py):min(h, y2+py), max(0, x1-px):min(w, x2+px)]

        # B. PREPROCESSING
        plate = cv2.resize(plate, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)

        alpha = 1.5  
        beta = -30   
        intense_gray = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
        blurred = cv2.medianBlur(intense_gray, 3)

        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 6. RECTANGULAR MORPHOLOGICAL CLOSING
        inv_thresh = cv2.bitwise_not(thresh)
        
        # 🔥 THE FIX: A 5x2 tall rectangular kernel. 🔥
        # Connects vertical dots but prevents horizontal bridging inside the 'N'
        kernel = np.ones((8, 5), np.uint8)
        closed = cv2.morphologyEx(inv_thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        thresh = cv2.bitwise_not(closed)

        # 7. ADD WHITE PADDING
        thresh = cv2.copyMakeBorder(thresh, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        # C. OCR EXECUTION
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        raw_text = pytesseract.image_to_string(thresh, config=config).strip()

        # D. CLEANUP
        print(f"DEBUG - Raw Tesseract Output: '{raw_text}'")
        clean_text = re.sub(r'[^A-Z0-9]', '', raw_text)
        final_plate = fix_indian_plate(clean_text)

        print(f"Final Detected Text: '{final_plate}'")
        print("-" * 30)

        # E. VISUAL DEBUGGING
        cv2.imshow("Final Padded Tesseract Input", thresh)
        
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

        text_x = x1
        text_y = max(y1 - 15, 30)

        cv2.putText(img, final_plate, (text_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 6, cv2.LINE_AA)
        cv2.putText(img, final_plate, (text_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)

# -----------------------------
# 5. SAVE AND DISPLAY
# -----------------------------
cv2.imwrite("final_output.jpg", img)
cv2.imshow("License Plate Recognition", img)
cv2.waitKey(0)
cv2.destroyAllWindows()