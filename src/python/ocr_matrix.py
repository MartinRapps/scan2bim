import sys
import re
import os
import pytesseract
from PIL import Image

def extract_matrix_from_image(img_path):
    print(f"Reading image from: {img_path}")
    if not os.path.exists(img_path):
        print(f"Error: {img_path} not found!")
        return None
        
    try:
        # Load the image
        img = Image.open(img_path)
        
        # --psm 6 treats the image as a uniform block of text, which matches the
        # CloudCompare matrix output (4 lines of numbers). No character whitelist:
        # a whitelist drops the space character and makes tesseract concatenate all
        # numbers on a line into one string, and the literal "\n\r" some configs
        # pass further corrupts recognition. The default model already recognises
        # digits, signs, dots, commas and spaces reliably here.
        custom_config = r'--psm 6'
        raw_text = pytesseract.image_to_string(img, config=custom_config)
        
        print("\n--- OCR Raw Text Detected ---")
        print(raw_text)
        print("-----------------------------\n")
        
        # Parse floats from each line
        lines = raw_text.split('\n')
        matrix_rows = []
        
        for line in lines:
            # Strip CloudCompare console prefixes like "[17:11:04]" and stray colons
            line = re.sub(r'\[[^\]]*\]', ' ', line)
            line = line.replace(':', ' ')
            # Clean string and find all numbers resembling floats
            line = line.replace(' ', ',').replace(';', ',').replace('\t', ',')
            # Handle common OCR misread of dot as comma, or double commas.
            line = line.replace(',.', '.').replace('.,', '.').replace(',', '.')
            tokens = re.findall(r'[\-+]?\d+(?:\.\d+)?', line)
            
            # Keep tokens of floats
            valid_floats = []
            for t in tokens:
                try:
                    # Clean up random multiple signs
                    t_clean = t.replace('+-', '-').replace('-+', '-')
                    if t_clean.count('-') > 1:
                        # Fix the common issue of "-0-02" -> "-0.02"
                        parts = t_clean.split('-')
                        # filter out empty string parts
                        parts = [p for p in parts if p != '']
                        if len(parts) >= 2:
                            t_clean = '-' + parts[0] + '.' + ''.join(parts[1:])
                    
                    val = float(t_clean)
                    valid_floats.append(t_clean)
                except ValueError:
                    continue
            
            if len(valid_floats) >= 3: # A row of 3D or 4D coordinates/transformation matrix
                matrix_rows.append(valid_floats)
        
        if len(matrix_rows) < 3:
            print("Error: Could not extract a valid 3x4 or 4x4 matrix structure from the image!")
            return None
            
        return matrix_rows
        
    except Exception as e:
        print(f"An error occurred during OCR extraction: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python ocr_matrix.py <input_image_path> <output_matrix_path>")
        sys.exit(1)
        
    input_img = sys.argv[1]
    output_txt = sys.argv[2]
    
    extracted = extract_matrix_from_image(input_img)
    if extracted:
        # Check rows length and padr if it's 3x4 to 4x4
        if len(extracted) == 3:
            # Add identity row for affine projection
            extracted.append(['0.00000000000', '0.00000000000', '0.00000000000', '1.00000000000'])
            
        print("\nFormatted 4x4 Matrix Output:")
        formatted_lines = []
        for i, row in enumerate(extracted[:4]):
            # Ensure row has exactly 4 columns
            while len(row) < 4:
                row.append("0.00000000000")
            row_str = ",".join(row[:4])
            formatted_lines.append(row_str)
            print(f"  Row {i+1}: {row_str}")
            
        # Write to txt file
        os.makedirs(os.path.dirname(output_txt), exist_ok=True)
        with open(output_txt, 'w') as f:
            f.write("\n".join(formatted_lines))
            
        print(f"\nMatrix successfully written as CSV to: {output_txt}")
        sys.exit(0)
    else:
        print("OCR processing finished with failures.")
        sys.exit(1)
