FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plane_erp_sync ./plane_erp_sync
RUN useradd -r -u 10001 sync && chown -R sync /app
USER sync
CMD ["python", "-m", "plane_erp_sync.main"]
