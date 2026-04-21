import os
import time
import sys
import re
from google import genai
from google.genai import types
from groq import Groq # <--- Đã thêm thư viện Groq

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

def get_style_instruction(style_type):
    if style_type == "genz":
        return """- XƯNG HÔ: Đại từ ngôi 1 → "Chồng", ngôi 2 → "các Vợ". TUYỆT ĐỐI KHÔNG dùng: tui, tôi, mình, bạn.
- Chèn từ khóa mồi: layout, chân ái, đỉnh chóp, cứu luôn, auto đẹp.
- Dịch kiểu hơi láo láo, nghịch nghịch GenZ. TỐI ĐA 8–12 từ/subtitle."""
    elif style_type == "pro":
        return """- XƯNG HÔ: Đại từ ngôi 1 → "Tôi", ngôi 2 → "Các bạn".
- Văn phong chuyên nghiệp, lịch sự, rõ ràng, phù hợp làm video hướng dẫn, bản tin.
- Dịch chuẩn nghĩa, không dùng tiếng lóng. TỐI ĐA 10–14 từ/subtitle."""
    else: # Normal
        return """- XƯNG HÔ: Đại từ ngôi 1 → "Mình", ngôi 2 → "Mọi người".
- Văn phong tự nhiên, gần gũi, như một Vlogger tâm sự. TỐI ĐA 10–12 từ/subtitle."""

def translate_chunk_by_ai(client, srt_chunk, chunk_index, total_chunks, style="genz", max_retries=5):
    print(f"   ⏳ Đang gửi AI dịch Khúc {chunk_index}/{total_chunks} (Style: {style})...")
    style_rule = get_style_instruction(style)
    
    sys_instruct = f"""Nhiệm vụ: DỊCH file SRT tiếng Trung sang tiếng Việt + TỰ ĐỘNG LỌC RÁC.

1. BỘ LỌC TỰ ĐỘNG: XÓA BỎ HOÀN TOÀN Lời bài hát, nhạc nền.

2. SMART REWRITE & STYLE:
{style_rule}

3. QUAN TRỌNG NHẤT - BẢO TOÀN THỜI GIAN (TIMESTAMP):
- GIỮ NGUYÊN cấu trúc Timestamp. TUYỆT ĐỐI KHÔNG ĐƯỢC SỬA HOẶC XÓA TIMESTAMP CỦA CÁC CÂU HỢP LỆ.
- Chỉ trả về nội dung SRT thuần túy. KHÔNG giải thích. KHÔNG dùng markdown.
"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash', # Chuyển sang 1.5 Flash cho ổn định 100%
                contents=srt_chunk,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    temperature=0.2,
                )
            )
            
            # Đề phòng Google từ chối dịch vì tưởng nhầm là nội dung vi phạm
            if not response or not hasattr(response, 'text') or not response.text:
                print(f"⚠️ Gemini trả về kết quả rỗng (Có thể do bộ lọc Safety).")
                raise ValueError("Kết quả trả về rỗng")

            result_text = response.text.replace("```srt", "").replace("```", "").strip()
            if re.search(r'[\u4e00-\u9fff]', result_text):
                time.sleep(3)
                continue 
            return result_text 
        except Exception as e:
            # IN LỖI CHI TIẾT RA RENDER ĐỂ BẮT BỆNH NẾU VẪN TẠCH
            error_msg = str(e)
            print(f"❌ LỖI GEMINI (Lần thử {attempt + 1}): {error_msg}")
            
            if "503" in error_msg or "429" in error_msg or "quota" in error_msg.lower():
                wait_time = 15 * (attempt + 1)
                time.sleep(wait_time)
            else:
                break
    return None

def process_srt_in_chunks(client, raw_chinese_content, style):
    blocks = [b.strip() for b in raw_chinese_content.split('\n\n') if b.strip()]
    chunk_size = 20 
    translated_blocks = []
    total_chunks = (len(blocks) + chunk_size - 1) // chunk_size
    for i in range(0, len(blocks), chunk_size):
        chunk_blocks = blocks[i:i+chunk_size]
        chunk_str = '\n\n'.join(chunk_blocks)
        chunk_index = (i // chunk_size) + 1
        result = translate_chunk_by_ai(client, chunk_str, chunk_index, total_chunks, style)
        if result:
            translated_blocks.extend([b.strip() for b in result.split('\n\n') if b.strip()])
        time.sleep(3) 
        
    final_srt = ""
    new_id = 1
    for block in translated_blocks:
        lines = block.split('\n')
        time_line_idx = -1
        for idx, line in enumerate(lines):
            if '-->' in line:
                time_line_idx = idx
                break
        if time_line_idx != -1 and len(lines) > time_line_idx + 1:
            timestamp = lines[time_line_idx]
            text = " ".join(lines[time_line_idx+1:])
            final_srt += f"{new_id}\n{timestamp}\n{text}\n\n"
            new_id += 1
    return final_srt.strip()

def run_subtitle_pipeline(video_path: str, api_key: str, style: str = "genz"):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"❌ Không tìm thấy file: {video_path}")
        
    # Lấy Key khách nhập trên web, nếu khách không nhập thì tự động lấy Key cài sẵn trong Render
    final_gemini_key = api_key if api_key else os.environ.get("GEMINI_API_KEY")
    if not final_gemini_key:
        raise ValueError("❌ Lỗi: Chưa cung cấp API Key của Gemini!")
        
    client = genai.Client(api_key=final_gemini_key)
    
    # ---------------------------------------------------------
    # GỌI GROQ API SIÊU TỐC THAY VÌ CHẠY WHISPER TRÊN SERVER
    # ---------------------------------------------------------
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("❌ Lỗi: Chưa cài đặt GROQ_API_KEY trong Environment variables của Render.")
        
    print("⏳ Đang gửi file lên Groq để bóc băng (Super Fast)...")
    groq_client = Groq(api_key=groq_api_key)
    
    try:
        with open(video_path, "rb") as file:
            # Tham số response_format="verbose_json" giúp trả về timestamp y hệt Whisper cũ
            result = groq_client.audio.transcriptions.create(
                file=(os.path.basename(video_path), file.read()),
                model="whisper-large-v3-turbo", 
                response_format="verbose_json",
                language="zh", 
                temperature=0.0
            )
    except Exception as e:
        raise RuntimeError(f"❌ Lỗi khi bóc băng bằng Groq: {str(e)}")
    
    raw_chinese_content = ""
    valid_index = 1
    
    # Xử lý kết quả trả về từ Groq
    segments = result.segments if hasattr(result, 'segments') else result.get("segments", [])
    
    for segment in segments:
        original = getattr(segment, 'text', '') if hasattr(segment, 'text') else segment.get('text', '')
        original = original.strip()
        
        start_time = getattr(segment, 'start', 0.0) if hasattr(segment, 'start') else segment.get('start', 0.0)
        end_time = getattr(segment, 'end', 0.0) if hasattr(segment, 'end') else segment.get('end', 0.0)
        
        duration = end_time - start_time
        
        # Logic lọc rác cũ của bạn
        if duration > 15.0 or (len(original) > 20 and len(set(original)) < (len(original) / 3)) or len(original) < 2:
            continue
            
        start_str = format_timestamp(start_time)
        end_str = format_timestamp(end_time)
        block = f"{valid_index}\n{start_str} --> {end_str}\n{original}\n\n"
        raw_chinese_content += block
        valid_index += 1
        
    if not raw_chinese_content:
        raise ValueError("Lỗi: Video không có giọng nói nào hoặc quá ngắn!")
        
    # Chuyển qua Gemini dịch
    final_polished_content = process_srt_in_chunks(client, raw_chinese_content, style)
    if not final_polished_content:
        raise RuntimeError("⚠️ Quá trình xử lý AI (Gemini) thất bại.")
        
    return raw_chinese_content, final_polished_content