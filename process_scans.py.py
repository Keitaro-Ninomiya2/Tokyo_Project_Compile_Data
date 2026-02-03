import cv2
import numpy as np
import os
import glob
import math

# ==========================================
# CONFIGURATION
# ==========================================
BASE_DIR = r"C:\Users\Keitaro Ninomiya\Box\Research Notes (keitaro2@illinois.edu)\Tokyo_Gender"
TARGET_LOC = "TokyoShi"
TARGET_YEAR = "1942"

# Input: .../Raw_Data/TokyoShi/1942
RAW_DIR = os.path.join(BASE_DIR, "Raw_Data", TARGET_LOC, TARGET_YEAR)

# Output: .../Processed_Data/TokyoShi/1942
PROCESSED_DIR = os.path.join(BASE_DIR, "Processed_Data", TARGET_LOC, TARGET_YEAR)

# ==========================================
# ALGORITHMS (The Robust Hybrid Pipeline)
# ==========================================

def get_spine_x(img_gray):
    """Finds the vertical shadow of the book spine using Peak Detection."""
    h, w = img_gray.shape
    # 1. Standard Binary (Otsu works best for shadows)
    _, binary = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 2. Vertical Projection
    v_proj = np.sum(binary, axis=0)
    
    # 3. Search center 30% only
    start, end = int(w * 0.35), int(w * 0.65)
    
    # 4. Smooth heavily to find the massive shadow peak
    v_smooth = cv2.GaussianBlur(v_proj[start:end].astype(np.float32), (45, 45), 0)
    
    return start + np.argmax(v_smooth)

def get_deskew_angle(img_color):
    """Detects rotation angle using Hough Line Transform on horizontal dividers."""
    h, w = img_color.shape[:2]
    gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
    
    # Focus on middle 30% height (where dividers are)
    roi_top, roi_bottom = int(h * 0.35), int(h * 0.65)
    roi = gray[roi_top:roi_bottom, :]
    
    edges = cv2.Canny(roi, 50, 150, apertureSize=3)
    
    # Look for long horizontal lines (>= 25% of page width)
    min_len = w * 0.25
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                            minLineLength=min_len, maxLineGap=20)
    
    if lines is None: return 0.0

    valid_angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        # Calculate angle
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        
        # Safety Lock: Only accept subtle tilts (+/- 2 degrees)
        # This prevents it from locking onto vertical text or noise
        if -2.0 < angle < 2.0:
            valid_angles.append(angle)
            
    if not valid_angles: return 0.0
    
    # Return Median angle (Robust to outliers)
    return np.median(valid_angles)

def rotate_image(image, angle):
    """Rotates image around center to fix skew."""
    if abs(angle) < 0.1: return image # Skip if negligible
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    # Use white border to match paper
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR, 
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255,255,255))

def get_horizontal_cut(img_color):
    """Finds horizontal divider using Morphological Filtering."""
    h, w = img_color.shape[:2]
    gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
    
    # 1. Adaptive Thresh (Handles lighting variation)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 25, 10)
    
    # 2. Morphological Open 
    # Kernel (40, 1) keeps only horizontal lines > 40px wide. Text is erased.
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    
    # 3. Projection Search on "Clean" lines
    start, end = int(h * 0.35), int(h * 0.65)
    proj = np.sum(lines, axis=1)[start:end]
    
    # Fallback to center if no lines found
    if np.max(proj) == 0: return h // 2
    
    return start + np.argmax(proj)

# ==========================================
# MAIN BATCH LOOP
# ==========================================

def run_processing():
    if not os.path.exists(RAW_DIR):
        print(f"❌ Error: Input directory not found: {RAW_DIR}")
        return

    # Find images
    search_path = os.path.join(RAW_DIR, "*.jpg")
    files = sorted(glob.glob(search_path))
    
    print(f"🚀 Processing TokyoShi 1942")
    print(f"📂 Input:  {RAW_DIR}")
    print(f"📂 Output: {PROCESSED_DIR}")
    print(f"📄 Found {len(files)} pages.")
    print("=" * 60)

    for i, file_path in enumerate(files):
        filename = os.path.basename(file_path)
        page_name = os.path.splitext(filename)[0] # e.g. "Page031"
        
        print(f"[{i+1}/{len(files)}] {filename}...", end=" ")
        
        try:
            # 1. Load Image
            img = cv2.imread(file_path)
            if img is None: 
                print("FAILED (Load error)")
                continue
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # 2. Vertical Split (The Spine)
            split_x = get_spine_x(gray)
            left_raw = img[:, 0:split_x]
            right_raw = img[:, split_x:w]

            # 3. Process LEFT Page (Deskew -> Cut)
            angle_l = get_deskew_angle(left_raw)
            left_fixed = rotate_image(left_raw, angle_l)
            cut_y_l = get_horizontal_cut(left_fixed)
            
            # 4. Process RIGHT Page (Deskew -> Cut)
            angle_r = get_deskew_angle(right_raw)
            right_fixed = rotate_image(right_raw, angle_r)
            cut_y_r = get_horizontal_cut(right_fixed)

            # 5. Save Results
            # Path: .../Processed_Data/TokyoShi/1942/PageXXX/img/
            save_dir = os.path.join(PROCESSED_DIR, page_name, "img")
            os.makedirs(save_dir, exist_ok=True)
            
            cv2.imwrite(os.path.join(save_dir, "left_top.jpg"), left_fixed[0:cut_y_l, :])
            cv2.imwrite(os.path.join(save_dir, "left_bottom.jpg"), left_fixed[cut_y_l:, :])
            cv2.imwrite(os.path.join(save_dir, "right_top.jpg"), right_fixed[0:cut_y_r, :])
            cv2.imwrite(os.path.join(save_dir, "right_bottom.jpg"), right_fixed[cut_y_r:, :])
            
            print(f"Done. (Skew L:{angle_l:.2f}°, R:{angle_r:.2f}°)")

        except Exception as e:
            print(f"ERROR: {str(e)}")

    print("=" * 60)
    print("Batch Processing Complete.")

if __name__ == "__main__":
    run_processing()