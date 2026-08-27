#!/usr/bin/env python3
"""Create a PLY copy with every Gaussian set to a uniform high opacity.

3D Gaussian Splatting stores the raw opacity logit in the ``opacity`` PLY
field, not the final alpha. A finite alpha of exactly 1 is impossible after a
sigmoid, so the default target is 0.999999. The tool preserves every other
byte in each vertex record. The project uses the copy as a geometry-oriented
SuGaR input while preserving the unmodified filtered PLY separately.
"""

import argparse
import hashlib
import math
import shutil
import struct
from pathlib import Path


PLY_SCALAR_TYPES = {
    "char": ("b", 1),
    "int8": ("b", 1),
    "uchar": ("B", 1),
    "uint8": ("B", 1),
    "short": ("h", 2),
    "int16": ("h", 2),
    "ushort": ("H", 2),
    "uint16": ("H", 2),
    "int": ("i", 4),
    "int32": ("i", 4),
    "uint": ("I", 4),
    "uint32": ("I", 4),
    "float": ("f", 4),
    "float32": ("f", 4),
    "double": ("d", 8),
    "float64": ("d", 8),
}


def parse_vertex_layout(source_path):
    """Return the binary header and layout of scalar vertex properties."""
    header_lines = []
    with source_path.open("rb") as source_file:
        while True:
            raw_line = source_file.readline()
            if not raw_line:
                raise ValueError("PLY header ended before end_header.")
            header_lines.append(raw_line)
            if raw_line.strip() == b"end_header":
                break

    try:
        header_text = b"".join(header_lines).decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("PLY header is not ASCII encoded.") from error

    byte_order = None
    vertex_count = None
    in_vertex_element = False
    properties = []
    for line in header_text.splitlines():
        parts = line.split()
        if not parts or parts[0] == "comment":
            continue
        if parts[:1] == ["format"]:
            byte_order = parts[1]
        elif parts[:1] == ["element"]:
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                vertex_count = int(parts[2])
        elif in_vertex_element and parts[:1] == ["property"]:
            if len(parts) != 3 or parts[1] == "list":
                raise ValueError("Only scalar vertex properties are supported.")
            property_type, property_name = parts[1:]
            if property_type not in PLY_SCALAR_TYPES:
                raise ValueError(f"Unsupported PLY scalar type: {property_type}")
            properties.append((property_name, property_type))

    if byte_order != "binary_little_endian":
        raise ValueError("Only binary_little_endian PLY files are supported.")
    if vertex_count is None or vertex_count < 1:
        raise ValueError("PLY contains no vertex element.")
    if not properties:
        raise ValueError("PLY vertex element contains no scalar properties.")

    offset = 0
    layout = {}
    for property_name, property_type in properties:
        format_character, byte_count = PLY_SCALAR_TYPES[property_type]
        layout[property_name] = (offset, format_character, byte_count)
        offset += byte_count

    if "opacity" not in layout:
        raise ValueError("PLY vertex element has no opacity property.")

    return b"".join(header_lines), vertex_count, offset, layout["opacity"]


def sha256sum(path):
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for block in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Create a high-opacity Gaussian PLY copy for geometry-oriented SuGaR input."
    )
    parser.add_argument("--input-ply", type=Path, required=True)
    parser.add_argument("--output-ply", type=Path, required=True)
    opacity_group = parser.add_mutually_exclusive_group()
    opacity_group.add_argument(
        "--target-alpha",
        type=float,
        default=0.999999,
        help="Final sigmoid opacity in the open interval (0, 1); default: 0.999999.",
    )
    opacity_group.add_argument(
        "--opacity-logit",
        type=float,
        help="Raw stored opacity logit; overrides the target-alpha conversion.",
    )
    args = parser.parse_args()

    source_path = args.input_ply.resolve()
    output_path = args.output_ply.resolve()
    if source_path == output_path:
        parser.error("--output-ply must differ from --input-ply to preserve the source.")
    if not source_path.is_file():
        parser.error(f"Input PLY does not exist: {source_path}")

    if args.opacity_logit is None:
        if not 0.0 < args.target_alpha < 1.0:
            parser.error("--target-alpha must be strictly between 0 and 1.")
        opacity_logit = math.log(args.target_alpha / (1.0 - args.target_alpha))
        final_alpha = args.target_alpha
    else:
        if not math.isfinite(args.opacity_logit):
            parser.error("--opacity-logit must be finite.")
        opacity_logit = args.opacity_logit
        final_alpha = 1.0 / (1.0 + math.exp(-opacity_logit))

    header, vertex_count, record_size, opacity_layout = parse_vertex_layout(source_path)
    opacity_offset, opacity_format, opacity_size = opacity_layout
    if opacity_format not in {"f", "d"}:
        parser.error("The opacity property must be a float or double.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pack_opacity = struct.Struct("<" + opacity_format).pack_into
    with source_path.open("rb") as source_file, output_path.open("wb") as output_file:
        source_header = source_file.read(len(header))
        if source_header != header:
            raise ValueError("PLY header changed while the file was being read.")
        output_file.write(header)

        for vertex_index in range(vertex_count):
            record = bytearray(source_file.read(record_size))
            if len(record) != record_size:
                raise ValueError(f"PLY ended in vertex record {vertex_index}.")
            pack_opacity(record, opacity_offset, opacity_logit)
            output_file.write(record)

        shutil.copyfileobj(source_file, output_file)

    print("Created high-opacity SuGaR input PLY")
    print(f"  input: {source_path}")
    print(f"  output: {output_path}")
    print(f"  vertices: {vertex_count}")
    print(f"  stored opacity logit: {opacity_logit:.9g}")
    print(f"  resulting sigmoid opacity: {final_alpha:.9g}")
    print(f"  input SHA-256: {sha256sum(source_path)}")
    print(f"  output SHA-256: {sha256sum(output_path)}")
    print("The source PLY remains unchanged and retains the original opacity semantics.")


if __name__ == "__main__":
    main()