# Linux only. Build in GitHub Actions, not on the development Mac.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils libxi6 libxrender1 libxkbcommon0 libsm6 libgl1 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.blender.org/release/Blender3.6/blender-3.6.18-linux-x64.tar.xz -o /tmp/blender.tar.xz && \
    echo "a5f58d22c2af4f980be11dc403ef98614d8a4c66c2b49eafa1802fd8ad14b208  /tmp/blender.tar.xz" | sha256sum -c - && \
    mkdir /opt/blender && tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 && rm /tmp/blender.tar.xz
ENV PATH="/opt/blender:${PATH}"
WORKDIR /lab
COPY . .
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir '.[test,vision,learning,cloud]'
CMD ["python", "-m", "pytest", "-q"]
