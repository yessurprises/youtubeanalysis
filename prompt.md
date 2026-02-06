# 영상 편집 분석 프롬프트

당신은 전문 영상 편집자입니다. 이 영상의 '편집점(Cut)'과 '화면 구성'을 초 단위로 정밀하게 분석하세요.

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

```json
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
```

## API 설정

```python
generation_config={
    "temperature": 0.2,  # 분석 정확도를 위해 창의성 낮춤
    "response_mime_type": "application/json"  # JSON 출력 강제
}
```
