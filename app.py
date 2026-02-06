import streamlit as st
import google.generativeai as genai
import yt_dlp
import os
import json
import tempfile
import time
from pathlib import Path
from datetime import datetime

# 기본 출력 폴더 설정
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)

# 사용 가능한 Gemini 모델 목록 (공식 문서 기준)
AVAILABLE_MODELS = {
    "gemini-3-flash-preview": "Gemini 3 Flash (Preview) - 최신, 빠름",
    "gemini-3-pro-preview": "Gemini 3 Pro (Preview) - 최신, 고성능",
    "gemini-2.5-flash": "Gemini 2.5 Flash - 안정, 무료티어",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite - 가장 저렴",
    "gemini-2.5-pro": "Gemini 2.5 Pro - 고성능",
    "gemini-2.0-flash": "Gemini 2.0 Flash - 레거시 (2026.3 종료)",
}

# 페이지 설정
st.set_page_config(
    page_title="영상 편집 분석기",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 영상 편집 분석기")
st.markdown("YouTube 영상의 편집 스타일을 AI로 분석합니다.")

# 사이드바 - API 키 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        help="Google AI Studio에서 API 키를 발급받으세요"
    )

    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키가 설정되었습니다")

    st.divider()

    # 모델 선택
    selected_model = st.selectbox(
        "Gemini 모델",
        options=list(AVAILABLE_MODELS.keys()),
        format_func=lambda x: AVAILABLE_MODELS[x],
        index=0,  # 기본값: gemini-3-flash-preview
        help="공식 문서 기준 사용 가능한 모델"
    )

    st.divider()

    output_format = st.radio(
        "출력 형식",
        ["JSON", "Markdown"],
        index=0
    )

    st.divider()

    # 자동 저장 설정
    auto_save = st.checkbox("분석 결과 자동 저장", value=True)
    save_dir = DEFAULT_OUTPUT_DIR  # 기본값 설정

    if auto_save:
        save_path = st.text_input(
            "저장 경로",
            value=str(DEFAULT_OUTPUT_DIR),
            help="분석 결과가 저장될 폴더 경로"
        )
        save_dir = Path(save_path)
        if not save_dir.exists():
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
                st.success(f"폴더 생성됨: {save_dir}")
            except Exception as e:
                st.error(f"폴더 생성 실패: {e}")
                save_dir = DEFAULT_OUTPUT_DIR

# 분석 프롬프트
ANALYSIS_PROMPT = """당신은 전문 영상 편집자입니다. 이 영상의 '편집점(Cut)'과 '화면 구성'을 초 단위로 정밀하게 분석하세요.

## 필수 요구사항 (엄격히 준수)

1. **Timecode:** 0.5초 단위의 타임스탬프를 기록할 것 (예: 00:01.5)
2. **Short Cuts:** 1초 미만의 짧은 컷도 놓치지 말 것
3. **모든 컷을 Hard Cut으로 판단하지 말 것** - 트랜지션 유형을 정확히 구분할 것

## 샷 타입 분류
- Extreme Wide Shot | Wide Shot | Full Shot | Medium Shot
- Medium Close-up | Close-up | Extreme Close-up
- Over-the-Shoulder | POV Shot | Two Shot

## 카메라 움직임 분류
- Static (고정) | Pan (좌우) | Tilt (상하)
- Zoom In/Out | Dolly In/Out | Tracking/Follow
- Crane/Jib | Handheld | Steadicam

## 트랜지션 분류

**[컷]**
- Hard Cut: 즉시 전환 (프레임 간 시각적 연결 없음)
- Jump Cut: 같은 프레임에서 시간 건너뜀
- Match Cut: 유사한 구도/동작으로 연결
- Cross Cut: 두 장면 번갈아 보여줌
- Cutaway: 다른 장면으로 잠시 전환
- L-Cut: 이전 오디오가 다음 장면까지 이어짐
- J-Cut: 다음 오디오가 먼저 들림

**[페이드]**
- Fade In: 검은 화면에서 밝아짐
- Fade Out: 검은 화면으로 어두워짐
- Fade to White: 흰색으로 전환

**[디졸브]**
- Cross Dissolve: 두 장면이 겹치며 전환
- Ripple Dissolve: 물결 효과 디졸브

**[와이프]**
- Linear Wipe: 수평/수직 밀어내기
- Iris Wipe: 원형 확대/축소
- Clock Wipe: 시계 방향 회전

**[카메라 기반]**
- Whip Pan: 빠른 팬으로 전환
- Zoom Transition: 줌으로 전환
- Shake Transition: 흔들림 전환

**[특수 효과]**
- Bloom/Lens Flare | Glitch | Chromatic Aberration

## 출력 형식 (JSON)
{
  "total_duration": "MM:SS.s",
  "scenes": [
    {
      "start": "MM:SS.s",
      "end": "MM:SS.s",
      "shot": "샷 타입",
      "camera": "카메라 움직임",
      "transition": "다음 씬으로의 트랜지션 유형",
      "description": "화면 내용 및 피사체 동작 설명",
      "effects": "특수효과 (없으면 null)"
    }
  ],
  "summary": "전체 편집 스타일 요약"
}
"""


def download_video(url: str, output_dir: str) -> str:
    """YouTube 영상 다운로드"""
    ydl_opts = {
        'format': 'best[height<=720]',  # 720p 이하로 제한 (업로드 용량 고려)
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename


def upload_to_gemini(file_path: str):
    """Gemini에 파일 업로드"""
    file = genai.upload_file(file_path)

    # 파일 처리 대기
    while file.state.name == "PROCESSING":
        time.sleep(2)
        file = genai.get_file(file.name)

    if file.state.name == "FAILED":
        raise ValueError(f"파일 처리 실패: {file.state.name}")

    return file


def analyze_video(file, model_name: str) -> str:
    """Gemini로 영상 정밀 분석"""
    model = genai.GenerativeModel(model_name)

    response = model.generate_content(
        [file, ANALYSIS_PROMPT],
        generation_config={
            "temperature": 0.2,  # 분석 정확도를 위해 창의성 낮춤
            "response_mime_type": "application/json",  # JSON 출력 강제
            "max_output_tokens": 65536,  # 출력 토큰 최대치 (긴 영상 분석용)
        }
    )
    return response.text


def parse_json_response(text: str) -> dict:
    """응답에서 JSON 추출"""
    # JSON 블록 찾기
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": text}


def save_analysis_result(video_name: str, result_json: dict, save_dir: Path) -> tuple[Path, Path]:
    """분석 결과를 파일로 저장"""
    # 파일명에서 확장자 제거 및 안전한 문자로 변환
    safe_name = Path(video_name).stem
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in safe_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 마크다운 파일 저장
    md_filename = f"{safe_name}_{timestamp}.md"
    md_path = save_dir / md_filename
    md_content = json_to_markdown(result_json)
    md_path.write_text(md_content, encoding="utf-8")

    # JSON 파일 저장
    json_filename = f"{safe_name}_{timestamp}.json"
    json_path = save_dir / json_filename
    json_path.write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, json_path


def json_to_markdown(data: dict) -> str:
    """JSON을 마크다운으로 변환"""
    md = []

    if "total_duration" in data:
        md.append(f"## 영상 길이: {data['total_duration']}\n")

    if "scenes" in data:
        md.append("## 씬 분석\n")
        md.append("| 타임코드 | 샷 타입 | 카메라 | 트랜지션 | 설명 | 효과 |")
        md.append("|----------|---------|--------|----------|------|------|")

        for scene in data["scenes"]:
            # 새 형식 (start/end) 또는 구 형식 (time) 지원
            if "start" in scene and "end" in scene:
                timecode = f"{scene['start']} - {scene['end']}"
            else:
                timecode = scene.get("time", "-")

            effects = scene.get("effects") or "-"
            description = scene.get("description", "-")
            md.append(f"| {timecode} | {scene.get('shot', '-')} | {scene.get('camera', '-')} | {scene.get('transition', '-')} | {description} | {effects} |")

    if "summary" in data:
        md.append(f"\n## 편집 스타일 요약\n{data['summary']}")

    if "raw_response" in data:
        md.append(f"\n## 분석 결과\n{data['raw_response']}")

    return "\n".join(md)


# 메인 UI
url_input = st.text_area(
    "YouTube URL 입력",
    placeholder="https://youtube.com/watch?v=xxxxx\n여러 개 입력 시 줄바꿈으로 구분",
    height=100
)

col1, col2 = st.columns([1, 4])
with col1:
    analyze_btn = st.button("🔍 분석 시작", type="primary", use_container_width=True)

# 분석 실행
if analyze_btn:
    if not api_key:
        st.error("사이드바에서 Gemini API 키를 입력해주세요.")
    elif not url_input.strip():
        st.error("YouTube URL을 입력해주세요.")
    else:
        urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

        for i, url in enumerate(urls):
            st.divider()
            st.subheader(f"영상 {i+1}: {url}")

            with st.status(f"분석 중...", expanded=True) as status:
                try:
                    # 임시 디렉토리 사용
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # 1. 영상 다운로드
                        st.write("📥 영상 다운로드 중...")
                        video_path = download_video(url, temp_dir)
                        video_name = Path(video_path).name
                        st.write(f"✅ 다운로드 완료: {video_name}")

                        # 2. Gemini에 업로드
                        st.write("☁️ Gemini에 업로드 중...")
                        uploaded_file = upload_to_gemini(video_path)
                        st.write("✅ 업로드 완료")

                        # 3. 분석
                        st.write("🤖 AI 분석 중...")
                        result_text = analyze_video(uploaded_file, selected_model)
                        st.write("✅ 분석 완료")

                        # 4. 결과 파싱
                        result_json = parse_json_response(result_text)

                        status.update(label="분석 완료!", state="complete")

                    # 5. 자동 저장
                    if auto_save:
                        md_path, json_path = save_analysis_result(video_name, result_json, save_dir)
                        st.success(f"💾 자동 저장 완료:\n- {md_path}\n- {json_path}")

                    # 결과 표시
                    if output_format == "JSON":
                        st.json(result_json)
                    else:
                        st.markdown(json_to_markdown(result_json))

                    # 다운로드 버튼
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            "📄 JSON 다운로드",
                            json.dumps(result_json, ensure_ascii=False, indent=2),
                            file_name=f"{Path(video_name).stem}.json",
                            mime="application/json"
                        )
                    with col2:
                        st.download_button(
                            "📝 Markdown 다운로드",
                            json_to_markdown(result_json),
                            file_name=f"{Path(video_name).stem}.md",
                            mime="text/markdown"
                        )

                except Exception as e:
                    status.update(label="오류 발생", state="error")
                    st.error(f"오류: {str(e)}")

# 푸터
st.divider()
st.caption("Powered by Google Gemini API & yt-dlp")
