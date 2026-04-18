import cv2
import pytesseract
import numpy as np
import re
from ultralytics import YOLO

# -----------------------------
# TESSERACT PATH (WINDOWS)
# -----------------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# -----------------------------
# SMART PLATE CORRECTION
# -----------------------------
def fix_indian_plate(text):
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    if len(text) < 7:
        return text

    # Standard mappings for common OCR errors
    num_map = {'O':'0','Q':'0','Z':'2','I':'1','L':'1','S':'5','B':'8','G':'6','T':'7'}
    char_map = {'0':'O','1':'I','2':'Z','8':'B','5':'S','6':'G'}

    def fix_part(part, mapping):
        return ''.join(mapping.get(c, c) for c in part)

    try:
        state = fix_part(text[:2], char_map)
        # Check if it's a 10-character plate (Standard)
        if len(text) >= 9:
            district = fix_part(text[2:4], num_map)
            # Find where the numbers start at the end
            # Usually: AA 00 AA 0000
            number = fix_part(text[-4:], num_map)
            series = fix_part(text[4:-4], char_map)
            return f"{state} {district} {series} {number}"
        return text
    except:
        return text

# -----------------------------
# LOAD YOLO MODEL
# -----------------------------
model = YOLO("best.pt")

# -----------------------------
# LOAD IMAGE
# -----------------------------
img_path = "3.jpeg" # Using your uploaded file name
img = cv2.imread(img_path)

if img is None:
    print("Error: Image not found!")
    exit()

h, w = img.shape[:2]
results = model(img)

print("\n--- Detection Results ---")

for r in results:
    for box in r.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # 1. TIGHTER CROP (To avoid grill interference)
        # We add just 5% padding
        px = int((x2 - x1) * 0.05)
        py = int((y2 - y1) * 0.05)
        plate = img[max(0, y1-py):min(h, y2+py), max(0, x1-px):min(w, x2+px)]

        # 2. PREPROCESSING FOR HSRP (The "Tracing" Logic)
        # Upscale
        plate = cv2.resize(plate, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # Grayscale
        gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)

        # Median Blur: This is the "Secret Sauce" for HSRP plates. 
        # It removes the blue dots/pattern inside the letters.
        blurred = cv2.medianBlur(gray, 3)

        # Contrast Enhancement
        alpha = 1.5 # Contrast control (1.0-3.0)
        beta = 0    # Brightness control (0-100)
        contrast = cv2.convertScaleAbs(blurred, alpha=alpha, beta=beta)

        # Thresholding
        _, thresh = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Morphological Dilate (Makes letters slightly thicker/bolder)
        kernel = np.ones((2,2), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=1)

        # 3. OCR (PSM 7 is vital for single lines)
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        raw_text = pytesseract.image_to_string(thresh, config=config).strip()

        # 4. POST-PROCESS
        clean_text = re.sub(r'[^A-Z0-9]', '', raw_text)
        final_plate = fix_indian_plate(clean_text)

        print(f"Detected Text: {final_plate}")

        # --- VISUAL DEBUG ---
        # Show what Tesseract is actually seeing
        cv2.imshow("What Tesseract Sees", thresh)
        
        # Annotate main image
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.putText(img, final_plate, (x1, y1 - 15), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

# Save result
cv2.imwrite("output_processed.jpg", img)
cv2.imshow("Final Result", img)
cv2.waitKey(0)
cv2.destroyAllWindows()