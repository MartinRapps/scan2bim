# Container D: SuGaR (Meshing & Regularization)
# Base Image with CUDA 11.8 & GCC
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

# Avoid interactive prompts and set build variables for C++ / CUDA extensions
ENV DEBIAN_FRONTEND=noninteractive
ENV FORCE_CUDA=1
ENV TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    wget \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Install Miniconda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh
ENV PATH=/opt/conda/bin:$PATH

# Accept Anaconda Terms of Service
RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# Create Conda Environment and configure shell
RUN conda create --name sugar -y python=3.9

# Install PyTorch, CUDA, and PyTorch3D inside 'sugar' environment in a single transaction to prevent MKL channel dilution
# NOTE: mkl is pinned to 2024.0.0 because mkl>=2025 removed the 'iJIT_NotifyEvent' symbol
# that PyTorch 2.0.1 requires. Without this pin, 'import torch' crashes with
# 'libtorch_cpu.so: undefined symbol: iJIT_NotifyEvent'.
RUN conda install -n sugar -y \
    "numpy<2" \
    "mkl==2024.0.0" \
    pytorch==2.0.1 \
    torchvision==0.15.2 \
    torchaudio==2.0.2 \
    pytorch-cuda=11.8 \
    fvcore \
    iopath \
    pytorch3d==0.7.4 \
    plotly \
    rich \
    plyfile==0.8.1 \
    -c pytorch3d -c pytorch -c nvidia -c fvcore -c iopath -c conda-forge

# Enable 'sugar' environment globally as default command path
ENV PATH=/opt/conda/envs/sugar/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/conda/envs/sugar/lib:$LD_LIBRARY_PATH

# Clone the project SuGaR fork at the pinned revision (recursive so the
# gaussian_splatting submodules are populated). This matches the
# third_party/SuGaR submodule (MartinRapps/SuGaR @ a0fc37b) so that image
# builds include the exact mask-aware project revision used by the archived
# matrix runs; docker-compose.sugar-dev.yml remains available as a development
# overlay for local fork changes.
ARG SUGAR_REF=a0fc37bd75c41aa1f2fae6044108edf450e6c82c
WORKDIR /opt/sugar
RUN git clone --recursive https://github.com/MartinRapps/SuGaR.git . && \
    git checkout "${SUGAR_REF}" && \
    git submodule update --init --recursive

RUN conda run -n sugar pip install "numpy<2" open3d PyMCubes && \
    cd /opt/sugar/gaussian_splatting/submodules/diff-gaussian-rasterization/ && \
    conda run -n sugar pip install . --no-build-isolation && \
    cd /opt/sugar/gaussian_splatting/submodules/simple-knn/ && \
    conda run -n sugar pip install . --no-build-isolation

# The container runs at runtime as the host UID/GID (see docker-compose.yml 'user:' directive),
# not as root. Since /opt/sugar was created entirely as root during the build (git clone, pip
# install), the non-root runtime user cannot create new output directories (e.g. './output/coarse/...')
# inside it, causing 'PermissionError: [Errno 13] Permission denied'. Make the whole workdir
# world-writable so runtime-created checkpoints/meshes can always be written.
WORKDIR /opt/sugar
RUN chmod -R 777 /opt/sugar
