# ---- Stage 1: builder ----
FROM nvidia/cuda:12.0.0-devel-ubuntu22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential curl ca-certificates libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp .

RUN cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=50 && \
    cmake --build build --config Release -j$(nproc) --target llama-server

RUN curl -L -o /build/model.gguf \
    https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf

# ---- Stage 2: runtime ----
FROM nvidia/cuda:12.0.0-runtime-ubuntu22.04 AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 appuser

WORKDIR /app
COPY --from=builder /build/build/bin /app
COPY --from=builder /build/model.gguf /app/model.gguf
RUN chown -R appuser:appuser /app

ENV LD_LIBRARY_PATH=/app
USER appuser
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

CMD ["./llama-server", "--model", "/app/model.gguf", "--host", "0.0.0.0", "--port", "8090"]