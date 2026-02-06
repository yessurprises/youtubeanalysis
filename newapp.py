import streamlit as st
import google.generativeai as genai
import yt_dlp
import os
import json
import tempfile
import time
import subprocess
import re
import shutil
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────
_FFMPEG_FALLBACK = r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
FFMPEG_PATH = shutil.which("ffmpeg") or os.path.join(_FFMPEG_FALLBACK, "ffmpeg.exe")
FFPROBE_PATH = shutil.which("ffprobe") or os.path.join(_FFMPEG_FALLBACK, "ffprobe.exe")

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)

AVAILABLE_MODELS = {
    "gemini-2.5-flash": "Gemini 2.5 Flash — 안정적, 무료 티어",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite — 가장 저렴",
    "gemini-2.5-pro": "Gemini 2.5 Pro — 고성능",
    "gemini-2.0-flash": "Gemini 2.0 Flash — 레거시 (2026.3 종료)",
}

# ──────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────
st.set_page_config(page_title="영상 편집 분석기", page_icon="🎬", layout="wide")
st.title("🎬 영상 편집 분석기")
st.markdown("YouTube 영상의 편집 패턴을 AI로 분석하고, 스토리보드 생성용 학습 데이터를 만듭니다.")

# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        help="Google AI Studio에서 발급받은 키를 입력하세요.",
    )
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키 설정 완료")

    st.divider()

    selected_model = st.selectbox(
        "Gemini 모델",
        options=list(AVAILABLE_MODELS.keys()),
        format_func=lambda x: AVAILABLE_MODELS[x],
        index=0,
        help="영상 분석에 사용할 모델을 선택하세요.",
    )

    st.divider()

    use_scene_detection = st.checkbox(
        "FFmpeg 씬 체인지 감지 사용",
        value=True,
        help="FFmpeg로 편집점을 먼저 추출한 뒤 Gemini에 넘깁니다. 정확도가 크게 향상됩니다.",
    )
    scene_threshold = st.slider(
        "씬 체인지 감도",
        min_value=0.1,
        max_value=0.6,
        value=0.3,
        step=0.05,
        help="낮을수록 민감 (컷 많이 검출), 높을수록 큰 변화만 검출",
    )

    st.divider()

    output_format = st.radio("출력 형식", ["JSON", "Markdown"], index=0)

    st.divider()

    auto_save = st.checkbox("분석 결과 자동 저장", value=True)
    save_dir = DEFAULT_OUTPUT_DIR
    if auto_save:
        save_path = st.text_input("저장 경로", value=str(DEFAULT_OUTPUT_DIR))
        save_dir = Path(save_path)
        if not save_dir.exists():
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
                st.success(f"폴더 생성됨: {save_dir}")
            except Exception as e:
                st.error(f"폴더 생성 실패: {e}")
                save_dir = DEFAULT_OUTPUT_DIR

# ──────────────────────────────────────────────
# 프롬프트
# ──────────────────────────────────────────────

# 씬 체인지 데이터 없이 Gemini만 사용할 때
PROMPT_WITHOUT_SCENE_DATA = """\
# Role
You are a professional video editor analyzing a startup event sketch video.
Your analysis will be used as **training data** to let an LLM generate storyboards and timelines for future videos.

# Task
Watch the entire video and produce a structured JSON analysis.
Focus on **editorial intent** (why each cut was made) as much as technical attributes.

# Guidelines
- Timestamp to the nearest **1 second** (do NOT fabricate sub-second precision).
- Identify every distinct shot/cut you can observe.
- For each shot, classify both its technical attributes AND its editorial purpose.
- At the end, summarize the overall editing patterns so an LLM can replicate the style.

# Shot Types
Extreme Wide Shot | Wide Shot | Full Shot | Medium Shot | Medium Close-up | Close-up | Extreme Close-up | Over-the-Shoulder | POV Shot | Two Shot | Insert Shot | Cutaway

# Camera Movement
Static | Pan (Left/Right) | Tilt (Up/Down) | Zoom In | Zoom Out | Dolly In | Dolly Out | Tracking/Follow | Crane/Jib | Handheld | Steadicam

# Subject Types
speaker | audience | product_demo | venue_exterior | venue_interior | signage_branding | networking | B-roll | title_card | transition_graphic

# Editorial Purpose
establish_context | introduce_speaker | build_energy | deliver_information | show_reaction | emotional_beat | transition | pacing_break | closing

# Output JSON Schema
{
  "total_duration": "MM:SS",
  "scenes": [
    {
      "index": 1,
      "start": "MM:SS",
      "end": "MM:SS",
      "duration_sec": 3.0,
      "shot_type": "Medium Shot",
      "camera_movement": "Static",
      "subject_type": "speaker",
      "editorial_purpose": "introduce_speaker",
      "description": "발표자가 무대 중앙에서 인사하며 발표를 시작"
    }
  ],
  "editing_patterns": {
    "avg_cut_duration_sec": 2.5,
    "pacing_curve": "slow_start → fast_middle → slow_end",
    "shot_type_distribution": {
      "Wide Shot": 15,
      "Medium Shot": 40,
      "Close-up": 30,
      "Other": 15
    },
    "recurring_sequences": [
      "Wide → Medium → Close-up 패턴이 발표 섹션에서 반복"
    ],
    "dominant_camera_style": "Static with occasional slow pan"
  },
  "narrative_structure": "도입(행사장 전경) → 전개(발표 하이라이트) → 클라이맥스(관객 반응) → 마무리(네트워킹)",
  "summary": "전체 편집 스타일 요약 (톤, 속도감, 특징적 기법 등)"
}

Return ONLY valid JSON. No markdown fences, no extra text.
"""

# 씬 체인지 데이터가 있을 때 (2단계 파이프라인)
PROMPT_WITH_SCENE_DATA = """\
# Role
You are a professional video editor analyzing a startup event sketch video.
Your analysis will be used as **training data** to let an LLM generate storyboards and timelines for future videos.

# Pre-extracted Scene Change Data
FFmpeg has already detected the following cut points (timestamps in seconds):
{scene_timestamps}

Total detected cuts: {cut_count}

Use these timestamps as a **reliable guide** for where edits occur.
Your job is to watch the video and describe WHAT and WHY at each cut point.

# Task
For each segment between cut points, analyze:
1. Technical shot attributes (type, camera movement)
2. Editorial intent (why this cut exists)
3. Content description

Then summarize overall editing patterns.

# Shot Types
Extreme Wide Shot | Wide Shot | Full Shot | Medium Shot | Medium Close-up | Close-up | Extreme Close-up | Over-the-Shoulder | POV Shot | Two Shot | Insert Shot | Cutaway

# Camera Movement
Static | Pan (Left/Right) | Tilt (Up/Down) | Zoom In | Zoom Out | Dolly In | Dolly Out | Tracking/Follow | Crane/Jib | Handheld | Steadicam

# Subject Types
speaker | audience | product_demo | venue_exterior | venue_interior | signage_branding | networking | B-roll | title_card | transition_graphic

# Editorial Purpose
establish_context | introduce_speaker | build_energy | deliver_information | show_reaction | emotional_beat | transition | pacing_break | closing

# Output JSON Schema
{{
  "total_duration": "MM:SS",
  "scenes": [
    {{
      "index": 1,
      "start": "MM:SS",
      "end": "MM:SS",
      "duration_sec": 3.0,
      "shot_type": "Medium Shot",
      "camera_movement": "Static",
      "subject_type": "speaker",
      "editorial_purpose": "introduce_speaker",
      "description": "발표자가 무대 중앙에서 인사하며 발표를 시작"
    }}
  ],
  "editing_patterns": {{
    "avg_cut_duration_sec": 2.5,
    "pacing_curve": "slow_start → fast_middle → slow_end",
    "shot_type_distribution": {{
      "Wide Shot": 15,
      "Medium Shot": 40,
      "Close-up": 30,
      "Other": 15
    }},
    "recurring_sequences": [
      "Wide → Medium → Close-up 패턴이 발표 섹션에서 반복"
    ],
    "dominant_camera_style": "Static with occasional slow pan"
  }},
  "narrative_structure": "도입(행사장 전경) → 전개(발표 하이라이트) → 클라이맥스(관객 반응) → 마무리(네트워킹)",
  "summary": "전체 편집 스타일 요약 (톤, 속도감, 특징적 기법 등)"
}}

Return ONLY valid JSON. No markdown fences, no extra text.
"""


# ──────────────────────────────────────────────
# 핵심 함수들
# ──────────────────────────────────────────────


def download_video(url: str, output_dir: str) -> tuple[str, dict]:
    """YouTube 영상 다운로드. (파일 경로, 메타데이터) 반환."""
    ydl_opts = {
        "format": "best[height<=720]",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        metadata = {
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "upload_date": info.get("upload_date", ""),
            "url": url,
        }
        return filename, metadata


def detect_scene_changes(video_path: str, threshold: float = 0.3) -> list[float]:
    """FFmpeg로 씬 체인지(편집점) 타임스탬프 추출."""
    cmd = [
        FFMPEG_PATH,
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=300, encoding="utf-8", errors="replace"
        )
        stderr = result.stderr or ""
    except FileNotFoundError:
        st.warning("FFmpeg가 설치되어 있지 않습니다. 씬 체인지 감지를 건너뜁니다.")
        return []
    except subprocess.TimeoutExpired:
        st.warning("FFmpeg 처리 시간이 초과되었습니다.")
        return []
    except Exception as e:
        st.warning(f"FFmpeg 실행 중 오류: {e}")
        return []

    # showinfo 출력에서 pts_time 파싱
    timestamps = []
    pattern = re.compile(r"pts_time:(\d+\.?\d*)")
    for line in stderr.split("\n"):
        if "showinfo" in line:
            match = pattern.search(line)
            if match:
                timestamps.append(round(float(match.group(1)), 1))

    return sorted(set(timestamps))


def format_timestamps_for_prompt(timestamps: list[float], total_duration: float) -> str:
    """타임스탬프 목록을 프롬프트에 넣을 텍스트로 변환."""
    if not timestamps:
        return "No cuts detected."

    lines = []
    # 첫 세그먼트
    prev = 0.0
    for i, ts in enumerate(timestamps):
        dur = round(ts - prev, 1)
        lines.append(f"  Segment {i+1}: {prev:.1f}s → {ts:.1f}s  (duration: {dur:.1f}s)")
        prev = ts
    # 마지막 세그먼트
    dur = round(total_duration - prev, 1)
    lines.append(f"  Segment {len(timestamps)+1}: {prev:.1f}s → {total_duration:.1f}s  (duration: {dur:.1f}s)")

    return "\n".join(lines)


def get_video_duration(video_path: str) -> float:
    """FFprobe로 영상 길이(초) 구하기."""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def upload_to_gemini(file_path: str):
    """Gemini에 파일 업로드 후 처리 완료까지 대기."""
    file = genai.upload_file(file_path)

    max_wait = 300  # 최대 5분 대기
    elapsed = 0
    while file.state.name == "PROCESSING":
        time.sleep(3)
        elapsed += 3
        if elapsed > max_wait:
            raise TimeoutError("Gemini 파일 처리 시간 초과 (5분)")
        file = genai.get_file(file.name)

    if file.state.name == "FAILED":
        raise ValueError(f"Gemini 파일 처리 실패: {file.state.name}")

    return file


def analyze_video(
    gemini_file,
    model_name: str,
    scene_timestamps: list[float] | None = None,
    total_duration: float = 0.0,
) -> str:
    """Gemini로 영상 분석 수행."""
    model = genai.GenerativeModel(model_name)

    if scene_timestamps:
        prompt = PROMPT_WITH_SCENE_DATA.format(
            scene_timestamps=format_timestamps_for_prompt(scene_timestamps, total_duration),
            cut_count=len(scene_timestamps),
        )
    else:
        prompt = PROMPT_WITHOUT_SCENE_DATA

    response = model.generate_content(
        [gemini_file, prompt],
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
            "max_output_tokens": 65536,
        },
    )
    return response.text


def parse_json_response(text: str) -> dict:
    """응답에서 JSON 추출 (방어적 파싱)."""
    cleaned = text.strip()

    # 마크다운 코드 펜스 제거
    if cleaned.startswith("```"):
        # ```json 또는 ``` 제거
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 부분 JSON이라도 찾아보기
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(cleaned[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass
        return {"raw_response": text}


def enrich_with_metadata(result: dict, metadata: dict, scene_timestamps: list[float] | None) -> dict:
    """분석 결과에 메타데이터와 씬 체인지 정보를 추가."""
    result["_metadata"] = {
        "video_title": metadata.get("title", ""),
        "video_url": metadata.get("url", ""),
        "video_duration_sec": metadata.get("duration", 0),
        "uploader": metadata.get("uploader", ""),
        "upload_date": metadata.get("upload_date", ""),
        "analyzed_at": datetime.now().isoformat(),
        "model_used": selected_model,
    }
    if scene_timestamps is not None:
        result["_metadata"]["ffmpeg_scene_changes"] = scene_timestamps
        result["_metadata"]["ffmpeg_cut_count"] = len(scene_timestamps)
    return result


def save_analysis_result(video_name: str, result_json: dict, save_dir: Path) -> tuple[Path, Path]:
    """분석 결과를 JSON + Markdown 파일로 저장."""
    safe_name = Path(video_name).stem
    safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in safe_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_filename = f"{safe_name}_{timestamp}.json"
    json_path = save_dir / json_filename
    json_path.write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")

    md_filename = f"{safe_name}_{timestamp}.md"
    md_path = save_dir / md_filename
    md_path.write_text(json_to_markdown(result_json), encoding="utf-8")

    return md_path, json_path


def get_analyzed_urls(output_dir: Path) -> set[str]:
    """output 폴더의 JSON 파일에서 이미 분석된 video_url 셋 반환."""
    urls = set()
    for json_file in output_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            url = data.get("_metadata", {}).get("video_url", "")
            if url:
                urls.add(url)
        except Exception:
            continue
    return urls


def search_youtube(keyword: str, max_results: int, min_duration: int, max_duration: int) -> list[dict]:
    """yt-dlp로 YouTube 검색, 필터링된 URL+메타데이터 리스트 반환."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "ignoreerrors": True,
    }
    search_query = f"ytsearch{max_results * 3}:{keyword}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(search_query, download=False)

    entries = result.get("entries", []) if result else []
    filtered = []
    for entry in entries:
        if not entry:
            continue
        duration = entry.get("duration") or 0
        if min_duration <= duration <= max_duration:
            filtered.append({
                "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                "title": entry.get("title", "제목 없음"),
                "duration": duration,
                "uploader": entry.get("uploader", ""),
                "upload_date": entry.get("upload_date", ""),
            })

    return filtered


def run_batch_analysis(
    videos: list[dict],
    model_name: str,
    use_scene: bool,
    threshold: float,
    auto_save: bool,
    save_dir: Path,
    progress_bar,
    status_text,
) -> list[dict]:
    """기존 파이프라인 함수들을 루프로 호출, 결과 리스트 반환."""
    results = []
    total = len(videos)

    for i, video_info in enumerate(videos):
        url = video_info["url"]
        title = video_info["title"]
        status_text.write(f"**[{i + 1}/{total}]** {title}")
        progress_bar.progress((i) / total, text=f"분석 중: {i + 1}/{total}")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 다운로드
                video_path, metadata = download_video(url, temp_dir)
                video_name = Path(video_path).name

                # FFmpeg 씬 체인지
                scene_timestamps = None
                total_duration = get_video_duration(video_path) or metadata.get("duration", 0)

                if use_scene:
                    scene_timestamps = detect_scene_changes(video_path, threshold)
                    if not scene_timestamps:
                        scene_timestamps = None

                # Gemini 업로드 + 분석
                uploaded_file = upload_to_gemini(video_path)
                result_text = analyze_video(
                    uploaded_file, model_name,
                    scene_timestamps=scene_timestamps,
                    total_duration=total_duration,
                )

                # 파싱 & 메타데이터
                result_json = parse_json_response(result_text)
                result_json = enrich_with_metadata(result_json, metadata, scene_timestamps)

            # 저장
            if auto_save:
                save_analysis_result(video_name, result_json, save_dir)

            results.append({"status": "success", "title": title, "url": url, "data": result_json})

        except Exception as e:
            results.append({"status": "fail", "title": title, "url": url, "error": str(e)})

    progress_bar.progress(1.0, text="완료!")
    return results


def merge_results_for_training(results: list[dict]) -> str:
    """개별 JSON을 LLM 학습용 통합 JSONL로 병합."""
    lines = []
    for r in results:
        if r["status"] != "success":
            continue
        data = r["data"]
        training_record = {
            "video_url": data.get("_metadata", {}).get("video_url", ""),
            "video_title": data.get("_metadata", {}).get("video_title", ""),
            "total_duration": data.get("total_duration", ""),
            "scenes": data.get("scenes", []),
            "editing_patterns": data.get("editing_patterns", {}),
            "narrative_structure": data.get("narrative_structure", ""),
            "summary": data.get("summary", ""),
        }
        lines.append(json.dumps(training_record, ensure_ascii=False))
    return "\n".join(lines)


def json_to_markdown(data: dict) -> str:
    """JSON 분석 결과를 사람이 읽기 좋은 마크다운으로 변환."""
    md = ["# 🎬 영상 편집 분석 리포트\n"]
    handled = set()

    # 메타데이터
    meta = data.get("_metadata", {})
    if meta:
        handled.add("_metadata")
        md.append(f"**영상:** {meta.get('video_title', '-')}")
        md.append(f"**URL:** {meta.get('video_url', '-')}")
        md.append(f"**분석 모델:** {meta.get('model_used', '-')}")
        md.append(f"**분석 일시:** {meta.get('analyzed_at', '-')}")
        if meta.get("ffmpeg_cut_count") is not None:
            md.append(f"**FFmpeg 감지 컷 수:** {meta['ffmpeg_cut_count']}")
        md.append("")

    # 영상 길이
    if "total_duration" in data:
        md.append(f"## 📏 영상 길이: {data['total_duration']}\n")
        handled.add("total_duration")

    # 내러티브 구조
    if "narrative_structure" in data:
        md.append(f"## 📖 내러티브 구조\n{data['narrative_structure']}\n")
        handled.add("narrative_structure")

    # 씬 분석
    if "scenes" in data:
        handled.add("scenes")
        md.append("## 🎞️ 씬별 분석\n")

        scene_fields = {
            "shot_type": "샷 타입",
            "camera_movement": "카메라",
            "subject_type": "피사체",
            "editorial_purpose": "편집 의도",
            "description": "설명",
        }
        skip_keys = {"index", "start", "end", "duration_sec"}

        for i, scene in enumerate(data["scenes"]):
            idx = scene.get("index", i + 1)
            start = scene.get("start", "?")
            end = scene.get("end", "?")
            dur = scene.get("duration_sec", "")
            dur_str = f" ({dur}s)" if dur else ""
            md.append(f"### #{idx} | {start} → {end}{dur_str}\n")

            for key, label in scene_fields.items():
                val = scene.get(key)
                if val is not None:
                    md.append(f"- **{label}:** {val}")

            # 스키마에 없는 추가 필드도 출력
            extra = [k for k in scene if k not in scene_fields and k not in skip_keys]
            for key in extra:
                val = scene[key]
                if val is not None:
                    md.append(f"- **{key}:** {val}")

            md.append("")

    # 편집 패턴
    if "editing_patterns" in data:
        handled.add("editing_patterns")
        ep = data["editing_patterns"]
        md.append("## 📊 편집 패턴\n")
        if "avg_cut_duration_sec" in ep:
            md.append(f"- **평균 컷 길이:** {ep['avg_cut_duration_sec']}초")
        if "pacing_curve" in ep:
            md.append(f"- **페이싱 곡선:** {ep['pacing_curve']}")
        if "dominant_camera_style" in ep:
            md.append(f"- **주요 카메라 스타일:** {ep['dominant_camera_style']}")
        if "shot_type_distribution" in ep:
            md.append("- **샷 타입 분포:**")
            for shot, pct in ep["shot_type_distribution"].items():
                md.append(f"  - {shot}: {pct}%")
        if "recurring_sequences" in ep:
            md.append("- **반복 패턴:**")
            for seq in ep["recurring_sequences"]:
                md.append(f"  - {seq}")
        md.append("")

    # 요약
    if "summary" in data:
        md.append(f"## 📝 편집 스타일 요약\n{data['summary']}\n")
        handled.add("summary")

    # raw_response (파싱 실패 시)
    if "raw_response" in data:
        md.append(f"## ⚠️ 원본 응답\n```\n{data['raw_response']}\n```\n")
        handled.add("raw_response")

    # 나머지 키
    for key in data:
        if key not in handled:
            val = data[key]
            if isinstance(val, (dict, list)):
                md.append(f"## {key}\n```json\n{json.dumps(val, ensure_ascii=False, indent=2)}\n```\n")
            else:
                md.append(f"## {key}\n{val}\n")

    return "\n".join(md)


# ──────────────────────────────────────────────
# 메인 UI (탭 구조)
# ──────────────────────────────────────────────

tab_single, tab_batch = st.tabs(["단일 분석", "배치 수집"])

# ──────────────────────────────────────────────
# 단일 분석 탭
# ──────────────────────────────────────────────
with tab_single:
    url_input = st.text_area(
        "YouTube URL 입력",
        placeholder="https://youtube.com/watch?v=xxxxx\n여러 개 입력 시 줄바꿈으로 구분",
        height=100,
    )

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        analyze_btn = st.button("🔍 분석 시작", type="primary", use_container_width=True)

    if analyze_btn:
        if not api_key:
            st.error("사이드바에서 Gemini API 키를 입력해주세요.")
        elif not url_input.strip():
            st.error("YouTube URL을 입력해주세요.")
        else:
            urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

            for i, url in enumerate(urls):
                st.divider()
                st.subheader(f"영상 {i + 1}/{len(urls)}")

                with st.status("분석 중...", expanded=True) as status:
                    try:
                        with tempfile.TemporaryDirectory() as temp_dir:
                            # Step 1: 다운로드
                            st.write("📥 영상 다운로드 중...")
                            video_path, metadata = download_video(url, temp_dir)
                            video_name = Path(video_path).name
                            st.write(f"✅ 다운로드 완료: **{metadata.get('title', video_name)}**")

                            # Step 2: FFmpeg 씬 체인지 감지 (선택)
                            scene_timestamps = None
                            total_duration = get_video_duration(video_path) or metadata.get("duration", 0)

                            if use_scene_detection:
                                st.write(f"🔎 FFmpeg 씬 체인지 감지 중 (감도: {scene_threshold})...")
                                scene_timestamps = detect_scene_changes(video_path, scene_threshold)
                                if scene_timestamps:
                                    st.write(f"✅ **{len(scene_timestamps)}개** 편집점 감지됨")
                                    with st.expander("감지된 편집점 타임스탬프"):
                                        st.code(
                                            format_timestamps_for_prompt(scene_timestamps, total_duration),
                                            language="text",
                                        )
                                else:
                                    st.write("⚠️ 편집점을 감지하지 못했습니다. Gemini 단독 분석으로 진행합니다.")
                                    scene_timestamps = None

                            # Step 3: Gemini 업로드
                            st.write("☁️ Gemini에 업로드 중...")
                            uploaded_file = upload_to_gemini(video_path)
                            st.write("✅ 업로드 완료")

                            # Step 4: AI 분석
                            pipeline_mode = "2단계 (FFmpeg + Gemini)" if scene_timestamps else "Gemini 단독"
                            st.write(f"🤖 AI 분석 중... [{pipeline_mode}]")
                            result_text = analyze_video(
                                uploaded_file,
                                selected_model,
                                scene_timestamps=scene_timestamps,
                                total_duration=total_duration,
                            )
                            st.write("✅ 분석 완료")

                            # Step 5: 파싱 & 메타데이터 추가
                            result_json = parse_json_response(result_text)
                            result_json = enrich_with_metadata(result_json, metadata, scene_timestamps)

                        status.update(label="✅ 분석 완료!", state="complete")

                        # Step 6: 자동 저장
                        if auto_save:
                            md_path, json_path = save_analysis_result(video_name, result_json, save_dir)
                            st.success(f"💾 저장 완료: `{json_path.name}` / `{md_path.name}`")

                        # Step 7: 결과 표시
                        if output_format == "JSON":
                            st.json(result_json)
                        else:
                            st.markdown(json_to_markdown(result_json))

                        # 다운로드 버튼
                        dl_col1, dl_col2 = st.columns(2)
                        with dl_col1:
                            st.download_button(
                                "📄 JSON 다운로드",
                                json.dumps(result_json, ensure_ascii=False, indent=2),
                                file_name=f"{Path(video_name).stem}_analysis.json",
                                mime="application/json",
                            )
                        with dl_col2:
                            st.download_button(
                                "📝 Markdown 다운로드",
                                json_to_markdown(result_json),
                                file_name=f"{Path(video_name).stem}_analysis.md",
                                mime="text/markdown",
                            )

                    except Exception as e:
                        status.update(label="❌ 오류 발생", state="error")
                        st.error(f"오류: {str(e)}")
                        st.exception(e)

# ──────────────────────────────────────────────
# 배치 수집 탭
# ──────────────────────────────────────────────
with tab_batch:
    st.subheader("키워드로 YouTube 영상 검색 & 일괄 분석")
    st.markdown("검색 키워드로 영상을 자동 수집하고, 순차적으로 분석하여 LLM 학습 데이터를 대량 구축합니다.")

    # 검색 설정
    batch_keyword = st.text_input(
        "검색 키워드",
        placeholder='예: "행사 스케치 영상", "startup event highlight"',
    )

    col_count, col_min, col_max = st.columns(3)
    with col_count:
        batch_max_results = st.slider("최대 수집 개수", min_value=1, max_value=50, value=10)
    with col_min:
        batch_min_duration = st.number_input("최소 영상 길이 (분)", min_value=0, max_value=120, value=1, step=1)
    with col_max:
        batch_max_duration = st.number_input("최대 영상 길이 (분)", min_value=1, max_value=120, value=10, step=1)

    col_search, _ = st.columns([1, 4])
    with col_search:
        search_btn = st.button("🔍 검색", type="primary", use_container_width=True)

    # 검색 실행 → 세션에 selected / reserve 분리 저장
    if search_btn:
        if not batch_keyword.strip():
            st.error("검색 키워드를 입력해주세요.")
        else:
            with st.spinner("YouTube 검색 중..."):
                try:
                    all_candidates = search_youtube(
                        batch_keyword.strip(),
                        batch_max_results,
                        int(batch_min_duration * 60),
                        int(batch_max_duration * 60),
                    )
                    analyzed = get_analyzed_urls(save_dir)
                    excluded = st.session_state.get("batch_excluded_urls", set())
                    all_candidates = [v for v in all_candidates if v["url"] not in analyzed and v["url"] not in excluded]
                    st.session_state["batch_selected"] = all_candidates[:batch_max_results]
                    st.session_state["batch_reserve"] = all_candidates[batch_max_results:]
                    st.session_state["batch_keyword"] = batch_keyword.strip()
                except Exception as e:
                    st.error(f"검색 실패: {e}")
                    st.session_state["batch_selected"] = []
                    st.session_state["batch_reserve"] = []

    # 검색 결과 미리보기
    if st.session_state.get("batch_selected"):
        selected = st.session_state["batch_selected"]
        reserve = st.session_state.get("batch_reserve", [])
        st.success(
            f"'{st.session_state.get('batch_keyword', '')}' — "
            f"선택: **{len(selected)}개** · 대기: {len(reserve)}개"
        )

        # 영상 목록 + 빼기 버튼
        for idx, v in enumerate(selected):
            dur_min = v["duration"] // 60
            dur_sec = v["duration"] % 60
            col_info, col_btn_rm = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{idx + 1}.** {v['title']}  \n"
                    f"  길이: {dur_min}:{dur_sec:02d} · {v['uploader']}  \n"
                    f"  `{v['url']}`"
                )
            with col_btn_rm:
                if st.button("빼기", key=f"remove_{idx}"):
                    removed = st.session_state["batch_selected"].pop(idx)
                    if "batch_excluded_urls" not in st.session_state:
                        st.session_state["batch_excluded_urls"] = set()
                    st.session_state["batch_excluded_urls"].add(removed["url"])
                    if st.session_state.get("batch_reserve"):
                        st.session_state["batch_selected"].append(
                            st.session_state["batch_reserve"].pop(0)
                        )
                    st.rerun()

        st.divider()

        col_start, _ = st.columns([1, 4])
        with col_start:
            batch_start_btn = st.button(
                f"🚀 {len(selected)}개 영상 분석 시작",
                type="primary",
                use_container_width=True,
            )

        if batch_start_btn:
            if not api_key:
                st.error("사이드바에서 Gemini API 키를 입력해주세요.")
            else:
                st.divider()
                progress_bar = st.progress(0, text="준비 중...")
                status_text = st.empty()

                batch_results = run_batch_analysis(
                    videos=selected,
                    model_name=selected_model,
                    use_scene=use_scene_detection,
                    threshold=scene_threshold,
                    auto_save=auto_save,
                    save_dir=save_dir,
                    progress_bar=progress_bar,
                    status_text=status_text,
                )

                # 요약 리포트
                success_count = sum(1 for r in batch_results if r["status"] == "success")
                fail_count = sum(1 for r in batch_results if r["status"] == "fail")

                st.divider()
                st.subheader("배치 분석 결과 요약")

                col_s, col_f = st.columns(2)
                with col_s:
                    st.metric("성공", f"{success_count}개")
                with col_f:
                    st.metric("실패", f"{fail_count}개")

                # 개별 결과 표시
                for r in batch_results:
                    if r["status"] == "success":
                        with st.expander(f"✅ {r['title']}"):
                            st.json(r["data"])
                    else:
                        with st.expander(f"❌ {r['title']}"):
                            st.error(r["error"])

                # 통합 JSONL 다운로드
                if success_count > 0:
                    st.divider()
                    jsonl_data = merge_results_for_training(batch_results)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # JSONL 파일 자동 저장
                    if auto_save:
                        safe_kw = "".join(
                            c if c.isalnum() or c in (" ", "-", "_") else "_"
                            for c in st.session_state.get("batch_keyword", "batch")
                        )
                        jsonl_path = save_dir / f"batch_{safe_kw}_{timestamp}.jsonl"
                        jsonl_path.write_text(jsonl_data, encoding="utf-8")
                        st.success(f"💾 통합 JSONL 저장 완료: `{jsonl_path.name}`")

                    st.download_button(
                        "📦 통합 학습 데이터 (JSONL) 다운로드",
                        jsonl_data,
                        file_name=f"training_data_{timestamp}.jsonl",
                        mime="application/jsonl",
                    )

# ──────────────────────────────────────────────
# 푸터
# ──────────────────────────────────────────────
st.divider()
st.caption("Powered by Google Gemini API · FFmpeg · yt-dlp")
