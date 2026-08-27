# Container C: Segment-then-Splat (STS) - Object-Specific 3DGS Training
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-devel

# Vermeide interaktive Prompts während apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV FORCE_CUDA=1
ENV TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"

WORKDIR /app

# Installiere Systempaket-Abhängigkeiten (Kompilierung von C++/CUDA Extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Klone das offizielle Segment-then-Splat Repository inklusive Submodule
RUN git clone https://github.com/luyr/Segment-then-Splat.git --recursive /app/STS

# Make the stage boundary explicit: with stage1=0 and stage2=5000, iterations
# 1..5000 are the object-mask curriculum and 5001..N render all objects.
COPY docker/container-c-sts/sts_stage_boundary.patch /tmp/sts_stage_boundary.patch
RUN cd /app/STS && patch -p1 < /tmp/sts_stage_boundary.patch && rm /tmp/sts_stage_boundary.patch

WORKDIR /app/STS

# Installiere STS-Abhängigkeiten
RUN pip install --no-cache-dir plyfile==0.8.1 tqdm scipy wandb opencv-python scikit-learn lpips
RUN pip install --no-cache-dir appdirs rich tyro pyyaml jaxtyping viser pytorch-msssim rawpy matplotlib scikit-image
RUN pip install --no-cache-dir nerfstudio --no-deps

# Baue und installiere diff-gaussian-rasterization & simple-knn Submodule direkt ohne Build-Isolation
RUN pip install ./submodules/depth-diff-gaussian-rasterization --no-build-isolation
RUN pip install ./submodules/simple-knn --no-build-isolation

# Exponiere Standard-Ports falls benötigt
EXPOSE 6009

CMD ["python3", "train.py", "--help"]
