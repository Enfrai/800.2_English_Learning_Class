# Build the FastAPI service image.
# Author: Shuohui Liu
# Date: 19 Oct 2026
# Updated: Sandhya Tiwari, 26 Oct 2026 (folder for US-006 lesson materials)
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
RUN mkdir -p /var/lib/ako/materials && chown 10001:10001 /var/lib/ako/materials
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
