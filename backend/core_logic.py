import whisper
import os
import time
import sys
import re
from google import genai
from google.genai import types

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
                model='gemini-2.5-flash-lite',
                contents=srt_chunk,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    temperature=0.2,
                )
            )
            result_text = response.text.replace("```srt", "").replace("```", "").strip()
            if re.search(r'[\u4e00-\u9fff]', result_text):
                time.sleep(3)
                continue 
            return result_text 
        except Exception as e:
            error_msg = str(e)
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
        
    client = genai.Client(api_key=api_key)
    model = whisper.load_model("tiny") # Hoặc "tiny" nếu server yếu
    
    result = model.transcribe(
        video_path, 
        language="zh", 
        fp16=False,
        condition_on_previous_text=True, 
        word_timestamps=True,            
        initial_prompt="哈喽大家",       
        temperature=(0.0, 0.2, 0.4),
        compression_ratio_threshold=2.4, 
        logprob_threshold=-1.0,          
        no_speech_threshold=0.6          
    )
    
    raw_chinese_content = ""
    valid_index = 1
    for segment in result["segments"]:
        original = segment["text"].strip()
        duration = segment['end'] - segment['start']
        if duration > 15.0 or (len(original) > 20 and len(set(original)) < (len(original) / 3)) or len(original) < 2:
            continue
            
        start = format_timestamp(segment['start'])
        end = format_timestamp(segment['end'])
        block = f"{valid_index}\n{start} --> {end}\n{original}\n\n"
        raw_chinese_content += block
        valid_index += 1
        
    if not raw_chinese_content:
        raise ValueError("Lỗi: Video không có giọng nói nào!")
        
    final_polished_content = process_srt_in_chunks(client, raw_chinese_content, style)
    if not final_polished_content:
        raise RuntimeError("⚠️ Quá trình xử lý AI thất bại.")
        
    return raw_chinese_content, final_polished_content