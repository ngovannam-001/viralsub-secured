import sys
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import uuid
import yt_dlp

# --- ĐOẠN CODE "THẦN THÁNH" FIX LỖI PATH ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import logic xử lý lõi (Groq + Gemini + FFMPEG)
from core_logic import run_subtitle_pipeline
# ------------------------------------------

app = FastAPI(title="ViralSub API - Professional Workspace")

# Cấu hình CORS để Frontend và Backend nói chuyện được với nhau
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thư mục lưu trữ video tạm thời
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# 🔐 CẤU HÌNH MẬT KHẨU HỆ THỐNG (Cài trên Render qua biến SYSTEM_PASSWORD)
SYSTEM_PASSWORD = os.getenv("SYSTEM_PASSWORD", "viralsub2024")

def download_video_from_url(url: str, output_path: str):
    """Hàm tải video từ YouTube/Douyin"""
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

@app.post("/run-tool")
async def process_video(
    video: UploadFile = File(None),
    video_url: str = Form(None),
    api_key: str = Form(""), # Để trống sẽ dùng Key trong Render
    style: str = Form("genz"),
    sys_password: str = Form("")
):
    # 1. Kiểm tra mật khẩu hệ thống
    if sys_password != SYSTEM_PASSWORD:
        raise HTTPException(status_code=401, detail="⛔ Sai mật khẩu hệ thống! Vui lòng kiểm tra lại.")

    # 2. Kiểm tra đầu vào
    if not video and not video_url:
        raise HTTPException(status_code=400, detail="Vui lòng upload video hoặc nhập URL!")

    temp_filename = f"{uuid.uuid4()}.mp4"
    temp_video_path = os.path.join(TEMP_DIR, temp_filename)
    
    try:
        # 3. Thu thập file video (Upload hoặc Download)
        if video:
            with open(temp_video_path, "wb") as buffer:
                shutil.copyfileobj(video.file, buffer)
        elif video_url:
            download_video_from_url(video_url, temp_video_path)

        # 4. Chạy Pipeline xử lý (Groq bóc băng -> Gemini dịch)
        # Hàm này trả về: Sub tiếng Trung và Sub tiếng Việt
        raw_zh, final_vi = run_subtitle_pipeline(temp_video_path, api_key, style)
        
        # 5. Trả kết quả về cho giao diện 3 cột
        return {
            "status": "success",
            "data": {
                "zh_srt": raw_zh,
                "vi_srt": final_vi,
                "video_url": f"/temp_uploads/{temp_filename}" # Đường dẫn để Player trên Web load video
            }
        }

    except Exception as e:
        # Nếu lỗi thì dọn dẹp file tạm để tránh đầy rác server
        if os.path.exists(temp_video_path): 
            os.remove(temp_video_path)
        raise HTTPException(status_code=500, detail=str(e))

# --- CẤU HÌNH PHỤC VỤ FILE TĨNH ---

# Cho phép truy cập vào thư mục video tạm (để phát video trên web)
app.mount("/temp_uploads", StaticFiles(directory=TEMP_DIR), name="temp_uploads")

# Phục vụ giao diện Frontend (index.html, css, js)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Chạy server tại cổng 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)