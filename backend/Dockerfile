FROM python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
ARG INSTALL_SEMANTIC=false
COPY backend/requirements-semantic.txt backend/requirements-semantic.txt
RUN if [ "$INSTALL_SEMANTIC" = "true" ]; then pip install --no-cache-dir -r backend/requirements-semantic.txt; fi
COPY backend backend
COPY scripts scripts
COPY sample_data sample_data
COPY evaluation evaluation
COPY pyproject.toml pyproject.toml
RUN python scripts/generate_samples.py && python scripts/train_classifier.py
RUN useradd --create-home --uid 10001 docverify && mkdir -p /data/uploads /data/models && chown -R docverify:docverify /data /app
USER docverify
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
