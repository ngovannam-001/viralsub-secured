# Sử dụng Python 3.10 mỏng nhẹ, tối ưu cho AI
FROM python:3.10-slim

# Cài đặt ffmpeg (Bắt buộc cho Whisper)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Copy file requirements và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY backend /app/backend
COPY frontend /app/frontend

# Mở port 8000
EXPOSE 8000

# Lệnh khởi chạy tự động khi deploy
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]