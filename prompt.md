# 영상 편집 분석 프롬프트

당신은 전문 영상 편집자입니다. 이 영상의 '편집점(Cut)'과 '화면 구성'을 초 단위로 정밀하게 분석하세요.

## 필수 요구사항 (엄격히 준수)

1. **Timecode:** 0.5초 단위의 타임스탬프를 기록할 것 (예: 00:01.5)
2. **Short Cuts:** 1초 미만의 짧은 컷도 놓치지 말 것

## 샷 타입 분류
- Extreme Wide Shot | Wide Shot | Full Shot | Medium Shot
- Medium Close-up | Close-up | Extreme Close-up
- Over-the-Shoulder | POV Shot | Two Shot

## 카메라 움직임 분류
- Static (고정) | Pan (좌우) | Tilt (상하)
- Zoom In/Out | Dolly In/Out | Tracking/Follow
- Crane/Jib | Handheld | Steadicam

## 출력 형식 (JSON)

```json
{
  "total_duration": "MM:SS.s",
  "scenes": [
    {
      "start": "MM:SS.s",
      "end": "MM:SS.s",
      "shot": "샷 타입",
      "camera": "카메라 움직임",
      "description": "화면 내용 및 피사체 동작 설명",
      "effects": "특수효과 (없으면 null)"
    }
  ],
  "summary": "전체 편집 스타일 요약"
}
```

## API 설정

```python
generation_config={
    "temperature": 0.2,  # 분석 정확도를 위해 창의성 낮춤
    "response_mime_type": "application/json"  # JSON 출력 강제
}
```
