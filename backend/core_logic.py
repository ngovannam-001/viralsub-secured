import os
import time
import sys
import re
import subprocess
from google import genai
from google.genai import types
from groq import Groq

try:
    sys.stdout.reconfigure(encoding='utf-8') 
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def get_style_instruction(style_type, lang="vi"):
    target_lang = "Tiếng Việt" if lang == "vi" else "Tiếng Anh (English)"
    
    if style_type == "genz":
        return f"""- NHIỆM VỤ: Dịch câu sang {target_lang}.
- VĂN PHONG: Trẻ trung, năng động, bắt trend mạng xã hội (GenZ).
- ĐỘ DÀI: TỐI ĐA 8–12 từ/subtitle để đọc kịp."""
    elif style_type == "pro":
        return f"""- NHIỆM VỤ: Dịch câu sang {target_lang}.
- VĂN PHONG: Chuyên nghiệp, lịch sự, chuẩn mực ngôn ngữ báo chí.
- ĐỘ DÀI: TỐI ĐA 10–14 từ/subtitle."""
    else: 
        return f"""- NHIỆM VỤ: Dịch câu sang {target_lang}.
- VĂN PHONG: Dịch sát nghĩa gốc, tự nhiên như người bản xứ.
- ĐỘ DÀI: TỐI ĐA 10–12 từ/subtitle."""

def translate_chunk_by_ai(client, srt_chunk, chunk_index, total_chunks, style="normal", lang="vi", max_retries=5):
    print(f"   ⏳ Đang gửi AI dịch Khúc {chunk_index}/{total_chunks} (Ngôn ngữ: {lang})...")
    style_rule = get_style_instruction(style, lang)
    
    sys_instruct = f"""Nhiệm vụ: DỊCH file SRT tiếng Trung sang ngôn ngữ đích + TỰ ĐỘNG LỌC RÁC.
1. BỘ LỌC TỰ ĐỘNG: XÓA Lời bài hát, nhạc nền.
2. SMART REWRITE & STYLE:
{style_rule}
3. QUAN TRỌNG NHẤT - BẢO TOÀN TIMESTAMP:
- GIỮ NGUYÊN cấu trúc Timestamp. KHÔNG giải thích. KHÔNG dùng markdown."""

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite', 
                contents=srt_chunk,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    temperature=0.2,
                )
            )
            if not response or not hasattr(response, 'text') or not response.text:
                raise ValueError("Kết quả trả về rỗng")

            result_text = response.text.replace("```srt", "").replace("```", "").strip()
            if re.search(r'[\u4e00-\u9fff]', result_text):
                time.sleep(3)
                continue 
            return result_text 
        except Exception as e:
            error_msg = str(e)
            print(f"❌ LỖI GEMINI: {error_msg}")
            if "503" in error_msg or "429" in error_msg or "quota" in error_msg.lower():
                time.sleep(15 * (attempt + 1))
            else:
                break
    return None

def process_srt_in_chunks(client, raw_chinese_content, style, lang="vi"):
    blocks = [b.strip() for b in raw_chinese_content.split('\n\n') if b.strip()]
    chunk_size = 20 
    translated_blocks = []
    total_chunks = (len(blocks) + chunk_size - 1) // chunk_size
    for i in range(0, len(blocks), chunk_size):
        chunk_blocks = blocks[i:i+chunk_size]
        chunk_str = '\n\n'.join(chunk_blocks)
        result = translate_chunk_by_ai(client, chunk_str, (i // chunk_size) + 1, total_chunks, style, lang)
        if result: translated_blocks.extend([b.strip() for b in result.split('\n\n') if b.strip()])
        time.sleep(3) 
        
    final_srt = ""
    new_id = 1
    for block in translated_blocks:
        lines = block.split('\n')
        time_line_idx = next((idx for idx, line in enumerate(lines) if '-->' in line), -1)
        if time_line_idx != -1 and len(lines) > time_line_idx + 1:
            timestamp = lines[time_line_idx]
            text = " ".join(lines[time_line_idx+1:])
            final_srt += f"{new_id}\n{timestamp}\n{text}\n\n"
            new_id += 1
    return final_srt.strip()

def run_subtitle_pipeline(video_path: str, api_key: str, style: str = "normal", lang: str = "vi"):
    if not os.path.exists(video_path): raise FileNotFoundError(f"❌ Không tìm thấy file: {video_path}")
        
    final_gemini_key = api_key if api_key else os.environ.get("GEMINI_API_KEY")
    if not final_gemini_key: raise ValueError("❌ Chưa cung cấp API Key của Gemini!")
    client = genai.Client(api_key=final_gemini_key)
    
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key: raise ValueError("❌ Chưa cài GROQ_API_KEY.")
    groq_client = Groq(api_key=groq_api_key)
    
    print("⏳ Đang nén âm thanh cực đại cho Groq (Fix 25MB)...")
    audio_path = video_path + ".mp3"
    
    try:
        # Lệnh nén siêu mạnh (16kHz, Mono, 32kbps) để trị lỗi 413 Too Large của Groq
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, 
            "-vn", "-ar", "16000", "-ac", "1", "-acodec", "libmp3lame", "-b:a", "32k", 
            audio_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception as e:
        raise RuntimeError("❌ Lỗi FFMPEG: " + str(e))

    print("⏳ Đang gửi lên Groq...")
    try:
        with open(audio_path, "rb") as file:
            result = groq_client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), file.read()),
                model="whisper-large-v3-turbo", response_format="verbose_json",
                language="zh", temperature=0.0
            )
    except Exception as e:
        if os.path.exists(audio_path): os.remove(audio_path)
        raise RuntimeError(f"❌ Lỗi Groq: {str(e)}")
        
    if os.path.exists(audio_path): os.remove(audio_path)
    
    raw_chinese_content = ""
    valid_index = 1
    segments = result.segments if hasattr(result, 'segments') else result.get("segments", [])
    
    for segment in segments:
        original = getattr(segment, 'text', '') if hasattr(segment, 'text') else segment.get('text', '')
        original = original.strip()
        start_time = getattr(segment, 'start', 0.0) if hasattr(segment, 'start') else segment.get('start', 0.0)
        end_time = getattr(segment, 'end', 0.0) if hasattr(segment, 'end') else segment.get('end', 0.0)
        
        if (end_time - start_time) > 15.0 or (len(original) > 20 and len(set(original)) < (len(original) / 3)) or len(original) < 2: continue
            
        raw_chinese_content += f"{valid_index}\n{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n{original}\n\n"
        valid_index += 1
        
    if not raw_chinese_content: raise ValueError("Lỗi: Video không có giọng nói!")
        
    final_polished_content = process_srt_in_chunks(client, raw_chinese_content, style, lang)
    if not final_polished_content: raise RuntimeError("⚠️ Xử lý AI thất bại.")
        
    return raw_chinese_content, final_polished_content