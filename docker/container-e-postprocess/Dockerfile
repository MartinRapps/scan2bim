# Container E: Post-processing (DGtal C++ & GDAL / CPU-only)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install basic development and GIS tools
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libboost-all-dev \
    libeigen3-dev \
    gdal-bin \
    libgdal-dev \
    python3-pip \
    python3-numpy \
    libgmp-dev \
    zlib1g-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir pytesseract pillow

# Build and install DGtal from source
# JOBS: build-arg fuer low-RAM-Builds (z.B. --build-arg JOBS=2 auf 7,6 GB WSL2).
ARG JOBS
RUN git clone https://github.com/DGtal-team/DGtal.git /tmp/DGtal && \
    cd /tmp/DGtal && \
    mkdir build && cd build && \
    cmake .. -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF && \
    make -j"${JOBS}" && \
    make install && \
    rm -rf /tmp/DGtal

WORKDIR /app
COPY src/cpp /app/src/cpp

# JOBS build-arg: ueberschreibt die Parallelitaet fuer low-RAM-Builds (z.B. 7,6 GB WSL2
# auf einem Laptop). Default = nproc. Auf dem Laptop: --build-arg JOBS=2.
ARG JOBS
RUN cmake -S /app/src/cpp -B /tmp/centerline-build -DCMAKE_BUILD_TYPE=Release && \
    cmake --build /tmp/centerline-build --parallel "${JOBS}" && \
    install -m 0755 /tmp/centerline-build/extractor /usr/local/bin/extractor && \
    rm -rf /tmp/centerline-build /app/src/cpp
