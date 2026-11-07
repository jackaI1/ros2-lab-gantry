# Linux only. Build in GitHub Actions, not on the development Mac.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends blender libgomp1 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /lab
COPY . .
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir '.[test,vision,learning,cloud]'
CMD ["python", "-m", "pytest", "-q"]
