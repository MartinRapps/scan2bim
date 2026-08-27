import csv

# Create a 10x10 grid from -5 to 5 manually using standard python loops
# This removes the numpy dependency so it runs out-of-the-box on the host!
grid_values = [-5.0, -3.89, -2.78, -1.67, -0.56, 0.56, 1.67, 2.78, 3.89, 5.0]

# Adjust center point to be exactly 0.0
grid_values[4] = -1.1 / 2.0
grid_values[5] = 1.1 / 2.0

output_file = 'data/synthetic_gcp_grid.csv'

with open(output_file, mode='w', newline='') as f:
    writer = csv.writer(f)
    # Write header
    writer.writerow(['gcp_id', 'X', 'Y', 'Z'])
    
    # Write 100 points (10x10 combinations)
    idx = 1
    for px in grid_values:
        for py in grid_values:
            p_x = round(px, 3)
            p_y = round(py, 3)
            p_z = 0.0
            
            # Label center perfectly as 0,0,0 at index near center if desired
            writer.writerow([f"GCP_{idx:03d}", p_x, p_y, p_z])
            idx += 1

print(f"Synthetischer Passpunkt-Raster erfolgreich erstellt: {output_file}")
print("Groesse: 10x10 Raster, Ausdehnung: -5m bis +5m, flach, Zentrum (0,0,0) in der Mitte.")
