# Build the FastAPI service image.
# Author: Shuohui Liu
# Date: 19 Oct 2026
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
# Lesson files live on a volume mounted here; the service user must own it.
RUN mkdir -p /data/lesson-files && chown 10001 /data/lesson-files
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
