import csv
import glob
import os


def find_gcp_csv(raw_dir):
    preferred = os.path.join(raw_dir, 'gcp_coordinates.csv')
    if os.path.exists(preferred):
        return preferred

    candidates = sorted(
        path for path in glob.glob(os.path.join(raw_dir, '*.csv'))
        if os.path.basename(path).lower() not in {'gcp_relative.csv'}
    )
    if candidates:
        return candidates[0]

    return None

def main():
    raw_dir = '/data/01_raw'
    csv_path = find_gcp_csv(raw_dir)
    out_rel_path = '/data/01_raw/gcp_relative.csv'
    out_anchor_path = '/data/01_raw/anchor.txt'
    
    if not csv_path:
        raise FileNotFoundError(
            f"No CSV file found in {raw_dir}. Please upload any GCP coordinate CSV there."
        )
        
    print(f"Reading global GCP coordinates from {csv_path}...")
    
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader)]
            rows = [row for row in reader if row]
    except Exception as e:
        raise RuntimeError(f"Error reading CSV: {e}") from e
    
    # Detect column names for coordinates (robust matching for German/English headers)
    try:
        x_idx = [i for i, c in enumerate(header) if c.lower() in ['x', 'east', 'ost', 'easting']][0]
        y_idx = [i for i, c in enumerate(header) if c.lower() in ['y', 'north', 'nord', 'northing']][0]
        z_idx = [i for i, c in enumerate(header) if c.lower() in ['z', 'height', 'hoehe', 'elevation']][0]
        id_idx = [i for i, c in enumerate(header) if c.lower() in ['id', 'name', 'gcp', 'passpunkt', 'gcp_id']][0]
    except IndexError:
        raise ValueError(
            "Could not detect GCP coordinate headers. "
            "Please ensure the CSV has columns: id, x, y, z"
        )
    
    if not rows:
        raise ValueError("The GCP coordinate CSV file is empty.")
    
    # Select the first GCP in the file as the anchor point
    anchor_id = rows[0][id_idx]
    try:
        anchor_x = float(rows[0][x_idx])
        anchor_y = float(rows[0][y_idx])
        anchor_z = float(rows[0][z_idx])
    except ValueError as e:
        raise ValueError(f"Error parsing coordinates as floats: {e}") from e
    
    print(f"Selected anchor point '{anchor_id}': X={anchor_x}, Y={anchor_y}, Z={anchor_z}")
    
    # Ensure raw directory or container maps exist
    os.makedirs(os.path.dirname(out_anchor_path), exist_ok=True)
    
    # Save the anchor point coordinates to a txt file
    with open(out_anchor_path, 'w', encoding='utf-8') as f:
        f.write(f"{anchor_x},{anchor_y},{anchor_z}")
    print(f"Anchor coordinates saved to {out_anchor_path}")
        
    # Compute relative coordinates by subtracting the anchor and write to new CSV
    try:
        with open(out_rel_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                new_row = list(row)
                new_row[x_idx] = float(row[x_idx]) - anchor_x
                new_row[y_idx] = float(row[y_idx]) - anchor_y
                new_row[z_idx] = float(row[z_idx]) - anchor_z
                writer.writerow(new_row)
        print(f"Relative GCP coordinates saved to {out_rel_path} for CloudCompare.")
        print("Success! You can now load these relative coordinates in CloudCompare.")
    except Exception as e:
        raise RuntimeError(f"Error writing relative coordinates: {e}") from e
 
if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Error: {error}")
