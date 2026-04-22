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

# Sửa lại hàm process_video hiện tại một chút để nhận tham số lang
@app.post("/run-tool")
async def process_video(
    video: UploadFile = File(None),
    video_url: str = Form(None),
    api_key: str = Form(""),
    style: str = Form("normal"),
    lang: str = Form("vi"), # <--- THÊM DÒNG NÀY (Đa ngôn ngữ)
    sys_password: str = Form("")
):
    if sys_password != SYSTEM_PASSWORD:
        raise HTTPException(status_code=401, detail="⛔ Sai mật khẩu hệ thống!")
    if not video and not video_url:
        raise HTTPException(status_code=400, detail="Vui lòng upload video hoặc nhập URL!")

    temp_filename = f"{uuid.uuid4()}.mp4"
    temp_video_path = os.path.join(TEMP_DIR, temp_filename)
    
    try:
        if video:
            with open(temp_video_path, "wb") as buffer:
                shutil.copyfileobj(video.file, buffer)
        elif video_url:
            download_video_from_url(video_url, temp_video_path)

        # Chú ý truyền thêm lang vào hàm core logic
        raw_zh, final_vi = run_subtitle_pipeline(temp_video_path, api_key, style, lang)
        
        return {
            "status": "success",
            "data": {
                "zh_srt": raw_zh,
                "vi_srt": final_vi,
                "video_url": f"/temp_uploads/{temp_filename}" 
            }
        }
    except Exception as e:
        if os.path.exists(temp_video_path): os.remove(temp_video_path)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# GIAI ĐOẠN 2: API ÉP CHỮ VÀO VIDEO (HARDSUB)
# ==========================================
@app.post("/burn-video")
async def burn_video(
    video_path: str = Form(...), # VD: /temp_uploads/abc.mp4
    srt_content: str = Form(...)
):
    import subprocess
    # Lấy đường dẫn file thật trên hệ thống
    filename = os.path.basename(video_path)
    actual_video_path = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(actual_video_path):
        raise HTTPException(status_code=400, detail="Video gốc đã bị xóa khỏi server. Vui lòng dịch lại!")

    # Lưu SRT tạm để FFmpeg đọc
    srt_filename = f"{filename}.srt"
    srt_path = os.path.join(TEMP_DIR, srt_filename)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    # File output xuất ra
    output_filename = filename.replace(".mp4", "_hardsub.mp4")
    output_path = os.path.join(TEMP_DIR, output_filename)

    try:
        # Lệnh FFMPEG ghi thẳng phụ đề vào hình ảnh video
        # -vf "subtitles=..." là bộ lọc ép chữ. Chú ý: FFMPEG trên Linux yêu cầu đường dẫn sub phải cẩn thận
        sub_filter = f"subtitles=temp_uploads/{srt_filename}"
        
        subprocess.run([
            "ffmpeg", "-y", "-i", actual_video_path,
            "-vf", sub_filter,
            "-c:a", "copy", # Giữ nguyên chất lượng âm thanh gốc
            output_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return {"status": "success", "video_url": f"/temp_uploads/{output_filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi burn video: {str(e)}")

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