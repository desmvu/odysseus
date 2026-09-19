# ---- builder: patch + build wheels for Real-ESRGAN's broken-on-3.14 deps ----
# basicsr/gfpgan/facexlib read their version via exec()+locals()['__version__'],
# which raises KeyError on Python 3.13+ (PEP 667). Build patched wheels here so
# the final image / Cookbook never has to compile the broken sdists. See
# docker/build-realesrgan-wheels.sh for the full rationale.
FROM python:3.14-slim AS realesrgan-wheels
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY docker/build-realesrgan-wheels.sh /usr/local/bin/build-realesrgan-wheels.sh
RUN bash /usr/local/bin/build-realesrgan-wheels.sh /wheels

FROM python:3.14-slim

# System deps. tmux is required by Cookbook for background downloads/serves.
# openssh-client is required for Cookbook remote server tests, setup, probes,
# downloads, and serves from Docker installs.
# git/cmake are required when Cookbook builds llama.cpp on first llama.cpp
# launch inside Docker.
# nodejs/npm provide npx for the built-in Browser MCP server.
# chromium provides the actual browser binary used by that MCP server.
# gosu lets the entrypoint drop privileges cleanly so signals still reach
# uvicorn directly (no extra shell layer like `su`/`sudo` would add).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    nodejs \
    npm \
    chromium \
    tmux \
    openssh-client \
    gosu \
    libgl1 \
    libglib2.0-0t64 \
    libxcb1 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# CUDA toolkit for llama.cpp — a minimal package set (nvcc + cudart + cuBLAS +
# driver stubs), not the full `cuda-toolkit` metapackage. The metapackage also
# pulls nsight-compute, cuda-gdb, sanitizer, cuFFT, cuSPARSE, NPP, nvrtc-dev,
# and docs — none of which GGML_CUDA needs to build llama-server — inflating
# the image by several GB for nothing. The component packages are always
# version-suffixed (e.g. cuda-nvcc-13-4, no unversioned alias exists), so the
# suffix is resolved dynamically from cuda-toolkit's own candidate version
# instead of hardcoding one that would silently break `apt-get install` the
# next time NVIDIA bumps their repo. Verified end-to-end: configure, build,
# and `ldd` on the resulting llama-server binary all resolve libcudart/
# libcublas/libcublasLt correctly against this set alone.
RUN apt-get update \
    && apt-get install -y wget gnupg \
    && wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && mkdir -p /etc/crypto-policies/back-ends \
    && echo '[hash_algorithms]' > /etc/crypto-policies/back-ends/apt-sequoia.config \
    && echo 'sha1 = "always"' >> /etc/crypto-policies/back-ends/apt-sequoia.config \
    && apt-get update \
    && CUDA_VER="$(apt-cache policy cuda-toolkit | grep Candidate | sed -E 's/.*: ([0-9]+)\.([0-9]+).*/\1-\2/')" \
    && apt-get install -y --no-install-recommends \
         cuda-nvcc-$CUDA_VER cuda-cudart-dev-$CUDA_VER \
         libcublas-$CUDA_VER libcublas-dev-$CUDA_VER cuda-driver-dev-$CUDA_VER \
    && rm -f /etc/crypto-policies/back-ends/apt-sequoia.config \
    && rm -rf /var/lib/apt/lists/*

# libgl1/libglib2.0-0t64/libxcb1 are runtime shared libs (libGL.so.1,
# libglib-2.0/libgthread, libxcb.so.1) that opencv-python (cv2) loads. The
# slim base omits them, so the Cookbook "install realesrgan" path imports cv2
# and dies with `libxcb.so.1: cannot open shared object file` despite a clean
# pip install. Using full opencv-python (not -headless) because basicsr/gfpgan/
# facexlib/realesrgan all depend on the `opencv-python` distribution by name.
#
# libmagic1 is the shared lib (libmagic.so.1) that python-magic dlopens for
# content-based MIME sniffing in src/upload_handler.py. We install both here
# (libmagic1 + the python-magic wrapper, below) rather than in requirements.txt
# because python-magic resolves libmagic at import time: where the lib is
# absent the import can block or raise, so keeping it image-only avoids
# regressing pip/venv installs on hosts without libmagic. Debian always has the
# lib here, so the import is instant and detection actually works.

# Docker CLI (client only — daemon stays on the host via the
# /var/run/docker.sock mount). The Debian `docker.io` package ships
# dockerd but not the client binary on slim, so grab the static client
# tarball from download.docker.com instead.
ARG DOCKER_CLI_VERSION=29.6.2
RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
         amd64) DARCH=x86_64 ;; \
         arm64) DARCH=aarch64 ;; \
         *) echo "unsupported arch $ARCH"; exit 1 ;; \
       esac \
    && curl -fsSL "https://download.docker.com/linux/static/stable/${DARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
       -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && install -m 0755 /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz

WORKDIR /app

# Install Python deps first (layer cache). Optional extras (PyMuPDF AGPL, etc.)
# are opt-in so the default image stays MIT-core; see requirements-optional.txt.
ARG INSTALL_OPTIONAL=false
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_OPTIONAL" = "true" ]; then pip install --no-cache-dir -r requirements-optional.txt; fi

# CUDA llama-cpp-python + runtime libs
RUN pip install --no-cache-dir llama-cpp-python==0.3.34 \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 \
    --force-reinstall
RUN pip install --no-cache-dir nvidia-cuda-runtime-cu12 nvidia-cublas-cu12
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.14/site-packages/nvidia/cuda_runtime/lib:/usr/local/lib/python3.14/site-packages/nvidia/cublas/lib:$LD_LIBRARY_PATH

# Pre-built llama.cpp server
ENV PATH="/usr/local/cuda/bin:${PATH}"
ENV CUDACXX="/usr/local/cuda/bin/nvcc"

RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp /app/llama.cpp \
    && cmake -B /app/llama.cpp/build -S /app/llama.cpp -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /app/llama.cpp/build --config Release -j$(nproc)

# Put the prebuilt binary on PATH. Without this, `shutil.which("llama-server")`
# (routes/shell_routes.py, routes/cookbook_routes.py) can't find it: Cookbook's
# dependency check then falls back to an in-process `import llama_cpp` GPU probe
# that permanently pins a CUDA context in the main app process (shows up as a
# "python3" GPU-preflight warning that never goes away), and a serve launch
# falls back to the ~15-20min from-source build bootstrap instead of using the
# binary that's already sitting right here.
ENV PATH="/app/llama.cpp/build/bin:${PATH}"

# python-magic powers content-based MIME sniffing in src/upload_handler.py.
# Image-only (not in requirements.txt) because it needs the libmagic1 system
# lib installed above; see the apt note near the top of this stage.
RUN pip install --no-cache-dir python-magic==0.4.27

# Pre-install the patched basicsr/gfpgan/facexlib wheels built in the
# realesrgan-wheels stage (--no-deps keeps the image lean — torch & friends are
# pulled only when realesrgan is actually installed). With these dists already
# satisfied, the Cookbook's plain `pip install realesrgan` resolves them from
# wheels instead of rebuilding the sdists that fail on Python 3.14.
COPY --from=realesrgan-wheels /wheels/ /tmp/odysseus-wheels/
RUN pip install --no-cache-dir --no-deps /tmp/odysseus-wheels/*.whl \
    && rm -rf /tmp/odysseus-wheels

# Copy app code
COPY . .

# Create data directory (mount a volume here for persistence)
RUN mkdir -p data logs services/cache/search

# Entrypoint that drops to PUID/PGID (default 1000:1000) and repairs
# ownership on the bind-mounted /app/data and /app/logs. Without this,
# the container runs as root and writes root-owned files into host
# bind mounts — any later non-root run (or a host user trying to
# update them) silently fails on EPERM, breaking skill extraction,
# prefs persistence, mail attachments, etc.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 7000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7000"]
