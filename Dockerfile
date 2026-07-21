FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY frontend/package.json ./frontend/
RUN cd frontend && npm install
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

FROM python:3.14-slim
LABEL org.opencontainers.image.vendor="JDB-NET"
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py db.py openapi.json ./
COPY static/swagger.html ./static/
COPY --from=frontend /app/static/dist ./static/dist
ARG VERSION=unknown
ENV VERSION=${VERSION}
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--log-level", "warning"]
