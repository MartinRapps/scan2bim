# Container A: SAM 3 Pre-processing
# Base image: CUDA runtime with Python 3.12 for SAM 3.1
FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ARG SAM3_REF=9f22cb976fb6e38dad5bb34940fad852dd897d0e

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev python3-venv \
    git ffmpeg libsm6 libxext6 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies and SAM 3
RUN python3 -m pip install --break-system-packages --no-cache-dir torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu126
RUN python3 -m pip install --break-system-packages --no-cache-dir opencv-python pillow huggingface_hub einops cython numpy pycocotools psutil timm pytesseract
RUN git clone https://github.com/facebookresearch/sam3.git /opt/sam3 \
    && cd /opt/sam3 \
    && git checkout ${SAM3_REF} \
    && python3 -m pip install --break-system-packages --no-cache-dir -e .
