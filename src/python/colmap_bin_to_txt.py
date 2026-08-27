"""COLMAP binary reconstruction model -> COLMAP text reconstruction model.

Liest ``cameras.bin`` und ``images.bin`` aus einem COLMAP-Sparse-Modell
(sparse/<n>/) und schreibt ``cameras.txt`` + ``images.txt`` im COLMAP-TXT-Format,
das ``gcp_register.py`` und der GCP-Registrierungs-Endpunkt lesen.

Rein stdlib, keine externen Abhängigkeiten. Nützlich, wenn kein COLMAP-
Binary (und kein Docker) verfügbar ist -- z.B. auf einem CPU-only Laptop
ohne CUDA, um die Posen/Intrinsik aus einem Backup-SfM zu extrahieren.

Auswahl des Teilmodells: Wenn der Sparse-Ordner mehrere numerische
Unterordner enthaelt, wird der mit der groessten ``points3D.bin`` gewaehlt
(gleiche Logik wie ``run_sfm.sh``). Sonst wird der angegebene Pfad direkt
verwendet.
"""

import argparse
import os
import struct
import sys

COLMAP_MODEL_NAMES = {
    0: "SIMPLE_PINHOLE",
    1: "PINHOLE",
    2: "SIMPLE_RADIAL",
    3: "RADIAL",
    4: "OPENCV",
    5: "OPENCV_FISHEYE",
    6: "FULL_OPENCV",
    7: "FOV",
    8: "SIMPLE_RADIAL_FISHEYE",
    9: "RADIAL_FISHEYE",
    10: "THIN_PRISM_FISHEYE",
}

# Reasonable widths for parameter counts so we can sanity-check the model
# mapping even if the on-disk num_params field is missing/wrong.
_MODEL_DEFAULT_NUM_PARAMS = {
    "SIMPLE_PINHOLE": 3, "PINHOLE": 4, "SIMPLE_RADIAL": 4, "RADIAL": 5,
    "OPENCV": 8, "OPENCV_FISHEYE": 8, "FULL_OPENCV": 12, "FOV": 5,
    "SIMPLE_RADIAL_FISHEYE": 4, "RADIAL_FISHEYE": 5, "THIN_PRISM_FISHEYE": 12,
}


def _read_struct(fh, fmt):
    """Read and unpack a struct format from a binary file handle."""
    size = struct.calcsize(fmt)
    data = fh.read(size)
    if len(data) != size:
        raise EOFError(f"Unerwartetes Dateiende beim Lesen von '{fmt}' ({size} Bytes erwartet).")
    return struct.unpack(fmt, data)


def pick_largest_model(sparse_root):
    """Return the numeric subdirectory under sparse_root with the largest
    points3D.bin (same policy as run_sfm.sh), or sparse_root itself if it
    already contains the binary files."""
    if os.path.isfile(os.path.join(sparse_root, "cameras.bin")):
        return sparse_root
    candidates = []
    for entry in sorted(os.listdir(sparse_root)):
        sub = os.path.join(sparse_root, entry)
        if not os.path.isdir(sub) or not entry.isdigit():
            continue
        p3d = os.path.join(sub, "points3D.bin")
        if os.path.isfile(p3d):
            candidates.append((os.path.getsize(p3d), sub))
    if not candidates:
        raise FileNotFoundError(
            f"Kein Sparse-Teilmodell gefunden unter {sparse_root} (keine cameras.bin im Root und keine numerischen Unterordner mit points3D.bin)."
        )
    candidates.sort(reverse=True)
    return candidates[0][1]


def read_cameras_bin(path):
    """Return {camera_id: {model, width, height, params}} from cameras.bin.

    Unterstuetzt zwei COLMAP-Varianten:
    (A) klassisch: nach width/height folgt ein uint64 num_params und dann die Params.
    (B) neueres Format (COLMAP 3.10+, Rigs): num_params wird aus der MODEL_ID abgeleitet
        (kein separates Feld); die Anzahl ergibt sich aus _MODEL_DEFAULT_NUM_PARAMS.

    Wir erkennen (A) vs (B) durch Ausprobieren: Wenn nach width/height direkt 24 Bytes
    fuer 3 doubles (SIMPLE_PINHOLE) lesbar sind und in eine plausible Bildgroesse +
    3 numerische Werte passen, waehlen wir (A); sonst (B).
    """
    cameras = {}
    with open(path, "rb") as fh:
        num_cameras, = _read_struct(fh, "<Q")
        for _ in range(num_cameras):
            cam_id, model_id = _read_struct(fh, "<ii")
            width, height = _read_struct(fh, "<QQ")
            # Variante A: explizites num_params.
            saved_pos = fh.tell()
            num_params_a, = _read_struct(fh, "<Q")
            if 0 < num_params_a <= 64 and _MODEL_DEFAULT_NUM_PARAMS.get(
                COLMAP_MODEL_NAMES.get(model_id, ""), -1) in (num_params_a, 0):
                num_params = num_params_a
            else:
                # Variante B: num_params weggelassen -> aus MODEL_ID ableiten.
                fh.seek(saved_pos)
                num_params = _MODEL_DEFAULT_NUM_PARAMS.get(COLMAP_MODEL_NAMES.get(model_id, ""), None)
                if num_params is None:
                    raise ValueError(
                        f"Unbekannte COLMAP-MODEL_ID {model_id} fuer Kamera {cam_id}."
                    )
            params = list(_read_struct(fh, f"<{num_params}d"))
            model_name = COLMAP_MODEL_NAMES.get(model_id)
            if model_name is None:
                raise ValueError(
                    f"Unbekannte COLMAP-MODEL_ID {model_id} (Kamera {cam_id}). Bekannt: {sorted(COLMAP_MODEL_NAMES)}"
                )
            cameras[cam_id] = {"model": model_name, "width": width, "height": height, "params": params}
    return cameras


def read_images_bin(path):
    """Yield (image_id, qvec[4], tvec[3], camera_id, name) for every image in images.bin."""
    with open(path, "rb") as fh:
        num_images, = _read_struct(fh, "<Q")
        for _ in range(num_images):
            image_id, = _read_struct(fh, "<i")
            qw, qx, qy, qz = _read_struct(fh, "<dddd")
            tx, ty, tz = _read_struct(fh, "<ddd")
            camera_id, = _read_struct(fh, "<i")
            # null-terminated name string
            name_bytes = bytearray()
            while True:
                ch = fh.read(1)
                if not ch or ch == b"\x00":
                    break
                name_bytes += ch
            name = name_bytes.decode("utf-8", errors="replace")
            num_points2D, = _read_struct(fh, "<Q")
            # Skip the 2D point records (x, y, point3D_id) per image.
            fh.seek(num_points2D * struct.calcsize("<ddq"), os.SEEK_CUR)
            yield image_id, [qw, qx, qy, qz], [tx, ty, tz], camera_id, name


def write_cameras_txt(path, cameras):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Camera list with one line of data per camera:\n")
        fh.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, NUM_PARAMS[]\n")
        for cam_id in sorted(cameras):
            cam = cameras[cam_id]
            params = " ".join(repr(v) for v in cam["params"])
            fh.write(f"{cam_id} {cam['model']} {cam['width']} {cam['height']} {len(cam['params'])} {params}\n")


def write_images_txt(path, images):
    """Write images.txt in the COLMAP two-line-per-image format. images is an
    iterable of (image_id, qvec, tvec, camera_id, name)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Image list with two lines of data per image:\n")
        fh.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        fh.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        for image_id, qvec, tvec, camera_id, name in images:
            qw, qx, qy, qz = qvec
            tx, ty, tz = tvec
            fh.write(
                f"{image_id} {qw} {qx} {qy} {qz} {tx} {ty} {tz} {camera_id} {name}\n"
            )
            fh.write("\n")  # empty 2D-points line (matches the format gcp_register expects)


def main():
    parser = argparse.ArgumentParser(
        description="COLMAP sparse/<n>/{cameras,images}.bin -> sparse_txt/{cameras,images}.txt"
    )
    parser.add_argument("--input", required=True,
                        help="Sparse-Ordner (enthaelt cameras.bin/images.bin oder numerische Teilmodelle)")
    parser.add_argument("--output", required=True,
                        help="Zielordner fuer cameras.txt und images.txt (wird angelegt)")
    parser.add_argument("--model", default=None,
                        help="Expliziter Pfad zum Teilmodell (ueberschreibt Autoauswahl)")
    args = parser.parse_args()

    input_root = os.path.abspath(args.input)
    output_root = os.path.abspath(args.output)
    os.makedirs(output_root, exist_ok=True)

    model_dir = args.model or pick_largest_model(input_root)
    model_dir = os.path.abspath(model_dir)
    print(f"Sparse-Teilmodell: {model_dir}")

    cameras_bin = os.path.join(model_dir, "cameras.bin")
    images_bin = os.path.join(model_dir, "images.bin")
    if not os.path.isfile(cameras_bin):
        raise FileNotFoundError(f"cameras.bin nicht gefunden: {cameras_bin}")
    if not os.path.isfile(images_bin):
        raise FileNotFoundError(f"images.bin nicht gefunden: {images_bin}")

    print(f"Lese {cameras_bin} ...")
    cameras = read_cameras_bin(cameras_bin)
    print(f"  -> {len(cameras)} Kameras")
    print(f"Lese {images_bin} ...")
    images = list(read_images_bin(images_bin))
    print(f"  -> {len(images)} Bilder")

    cameras_out = os.path.join(output_root, "cameras.txt")
    images_out = os.path.join(output_root, "images.txt")
    write_cameras_txt(cameras_out, cameras)
    write_images_txt(images_out, images)
    print(f"Schrieb: {cameras_out}")
    print(f"Schrieb: {images_out}")


if __name__ == "__main__":
    main()
