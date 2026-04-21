import sys
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import uuid
import yt_dlp

# --- ĐOẠN CODE "THẦN THÁNH" FIX LỖI PATH ---
# Lấy đường dẫn của thư mục hiện tại (thư mục backend)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Thêm nó vào hệ thống tìm kiếm của Python
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Bây giờ import sẽ luôn chạy được
from core_logic import run_subtitle_pipeline
# ------------------------------------------

#app = FastAPI(title="ViralSub API - Secured")
# ... (giữ nguyên các phần code bên dưới)

app = FastAPI(title="ViralSub API - Secured")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# 🔐 CẤU HÌNH MẬT KHẨU BẢO VỆ TOOL
# Mặc định là "viralsub2024" nếu bạn chạy ở máy. Lên Render có thể đổi pass này.
SYSTEM_PASSWORD = os.getenv("SYSTEM_PASSWORD", "viralsub2024")

def download_video_from_url(url: str, output_path: str):
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
    api_key: str = Form(""),
    style: str = Form("genz"),
    sys_password: str = Form("") # Nhận mật khẩu từ web gửi lên
):
    # 🚨 CHỐT CHẶN BẢO MẬT: Kiểm tra mật khẩu trước khi làm bất cứ việc gì
    if sys_password != SYSTEM_PASSWORD:
        raise HTTPException(status_code=401, detail="⛔ Sai mật khẩu hệ thống! Bạn không có quyền sử dụng tool này.")

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

        video_url_path = f"/temp_uploads/{temp_filename}"
        
        raw_zh, final_vi = run_subtitle_pipeline(temp_video_path, api_key, style)
        
        return {
            "status": "success",
            "data": {
                "zh_srt": raw_zh,
                "vi_srt": final_vi,
                "video_url": video_url_path
            }
        }
    except Exception as e:
        if os.path.exists(temp_video_path): os.remove(temp_video_path)
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/temp_uploads", StaticFiles(directory=TEMP_DIR), name="temp_uploads")
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)