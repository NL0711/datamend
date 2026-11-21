FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# weights/model.onnx and weights/SOURCE.json must exist at build (run fetch_weights.py + convert.py first),
# or mount a directory at /app/weights.
COPY weights ./weights
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:create_app --factory --host 0.0.0.0 --port ${PORT}"]
