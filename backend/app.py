import sys
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import uuid
import yt_dlp

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from core_logic import run_subtitle_pipeline

app = FastAPI(title="ViralSub API - Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

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
    style: str = Form("normal"),
    lang: str = Form("vi"), 
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

@app.post("/burn-video")
async def burn_video(
    video_path: str = Form(...),
    srt_content: str = Form(...)
):
    import subprocess
    filename = os.path.basename(video_path)
    actual_video_path = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(actual_video_path):
        raise HTTPException(status_code=400, detail="Video gốc đã bị xóa khỏi server.")

    srt_filename = f"{filename}.srt"
    srt_path = os.path.join(TEMP_DIR, srt_filename)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    output_filename = filename.replace(".mp4", "_hardsub.mp4")
    output_path = os.path.join(TEMP_DIR, output_filename)

    try:
        # FFMPEG Burn-in Subtitles
        sub_filter = f"subtitles=temp_uploads/{srt_filename}"
        subprocess.run([
            "ffmpeg", "-y", "-i", actual_video_path,
            "-vf", sub_filter,
            "-c:a", "copy",
            output_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return {"status": "success", "video_url": f"/temp_uploads/{output_filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi ép sub video: {str(e)}")

app.mount("/temp_uploads", StaticFiles(directory=TEMP_DIR), name="temp_uploads")
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)