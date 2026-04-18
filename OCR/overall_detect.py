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
    """ Cleans up common OCR mistakes based on the standard Indian format. """
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
# 3. PLATE SCORING SYSTEM (THE DECIDER)
# -----------------------------
def score_plate(text):
    """ Evaluates how closely the text resembles a valid Indian plate. """
    if not text: return 0
    clean = text.replace(" ", "")
    score = len(clean) # 1 point per character
    
    # Bonus points for matching the Indian Format: AA 11 AA 1111
    if re.match(r'^[A-Z]{2}', clean): score += 5  # Starts with 2 letters
    if re.match(r'.*\d{4}$', clean): score += 5   # Ends with 4 numbers
    if 9 <= len(clean) <= 10: score += 5          # Correct total length
    
    return score

# -----------------------------
# 4. INITIALIZE YOLO
# -----------------------------
model = YOLO("best.pt")

# -----------------------------
# 5. LOAD IMAGE
# -----------------------------
img_path = "input5.jpg" # Change this to your test image
img = cv2.imread(img_path)

if img is None:
    print(f"Error: Could not load image {img_path}")
    exit()

h, w = img.shape[:2]
results = model(img)

print("\n--- Starting Dual-Pass Detection & OCR ---")

for r in results:
    for box in r.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # A. TIGHT CROP
        px = int((x2 - x1) * 0.05)
        py = int((y2 - y1) * 0.05)
        plate = img[max(0, y1-py):min(h, y2+py), max(0, x1-px):min(w, x2+px)]

        # B. BASE PREPROCESSING
        plate = cv2.resize(plate, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)

        alpha = 1.5  
        beta = -30   
        intense_gray = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
        blurred = cv2.medianBlur(intense_gray, 3)

        # Base Threshold 
        _, thresh_base = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        inv_thresh_base = cv2.bitwise_not(thresh_base)

        # C. BRANCH 1: NORMAL PIPELINE
        # Uses a mild 3x3 square kernel to gently clean edges without distortion
        kernel_normal = np.ones((10, 2), np.uint8)
        closed_normal = cv2.morphologyEx(inv_thresh_base, cv2.MORPH_CLOSE, kernel_normal, iterations=1)
        thresh_normal = cv2.bitwise_not(closed_normal)

        # D. BRANCH 2: HSRP PIPELINE
        # Uses the aggressive 5x2 tall rectangular kernel to fix honeycomb gaps
        kernel_hsrp = np.ones((8, 5), np.uint8) 
        closed_hsrp = cv2.morphologyEx(inv_thresh_base, cv2.MORPH_CLOSE, kernel_hsrp, iterations=2)
        thresh_hsrp = cv2.bitwise_not(closed_hsrp)

        # E. ADD WHITE PADDING TO BOTH (Crucial for Tesseract edges)
        thresh_normal = cv2.copyMakeBorder(thresh_normal, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        thresh_hsrp = cv2.copyMakeBorder(thresh_hsrp, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        # F. EXECUTE OCR ON BOTH
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        
        raw_normal = pytesseract.image_to_string(thresh_normal, config=config).strip()
        raw_hsrp = pytesseract.image_to_string(thresh_hsrp, config=config).strip()

        # G. CLEAN AND EVALUATE
        clean_normal = fix_indian_plate(re.sub(r'[^A-Z0-9]', '', raw_normal))
        clean_hsrp = fix_indian_plate(re.sub(r'[^A-Z0-9]', '', raw_hsrp))

        score_normal = score_plate(clean_normal)
        score_hsrp = score_plate(clean_hsrp)

        print(f"Normal Pipeline Output: '{clean_normal}' (Score: {score_normal})")
        print(f"HSRP Pipeline Output:   '{clean_hsrp}' (Score: {score_hsrp})")

        # Select the winner based on our scoring logic!
        if score_hsrp > score_normal:
            final_plate = clean_hsrp
            print("--> WINNER: HSRP Pipeline")
        else:
            final_plate = clean_normal
            print("--> WINNER: Normal Pipeline")
            
        print("-" * 30)

        # H. VISUAL DEBUGGING
        # Stack both images horizontally to compare what Tesseract saw
        debug_view = np.hstack((thresh_normal, thresh_hsrp))
        debug_view = cv2.cvtColor(debug_view, cv2.COLOR_GRAY2BGR)
        
        # Add labels to the debug view
        cv2.putText(debug_view, "NORMAL (3x3 Kernel)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(debug_view, "HSRP (5x2 Kernel)", (thresh_normal.shape[1] + 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        cv2.imshow("Tesseract Inputs: Normal vs HSRP", debug_view)
        
        # Draw bounding box and winning text on original image
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

        text_x = x1
        text_y = max(y1 - 15, 30)

        # Thick Green Outline
        cv2.putText(img, final_plate, (text_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 6, cv2.LINE_AA)
        # Thin Black Fill
        cv2.putText(img, final_plate, (text_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)

# -----------------------------
# 6. SAVE AND DISPLAY
# -----------------------------
cv2.imwrite("final_output.jpg", img)
cv2.imshow("License Plate Recognition", img)
cv2.waitKey(0)
cv2.destroyAllWindows()