import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence

from openai import OpenAI

from app.schemas.analysis import (
    AnalysisCandidate,
    AnalysisScores,
    AnalysisTitle,
    SermonAnalysisResult,
    StoredTranscriptSegmentData,
)


class SermonAnalysisError(Exception):
    pass


class SermonAnalysisService(ABC):
    @abstractmethod
    def analyze(self, segments: Sequence[StoredTranscriptSegmentData], duration_seconds: float) -> SermonAnalysisResult:
        raise NotImplementedError


class OpenAISermonAnalysisService(SermonAnalysisService):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise SermonAnalysisError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def analyze(self, segments: Sequence[StoredTranscriptSegmentData], duration_seconds: float) -> SermonAnalysisResult:
        timestamped_transcript = json.dumps(
            [
                {
                    "segment_id": item.segment_id,
                    "start_sec": item.start_sec,
                    "end_sec": item.end_sec,
                    "text": item.text,
                }
                for item in segments
            ],
            ensure_ascii=False,
        )
        base_prompt = f"""다음 한국어 설교 대본에서 쇼츠 후보를 JSON으로 선정하세요.
후보 범위는 반드시 제공된 segment_id 중 start_segment_id와 end_segment_id로만 선택하세요.
시간이나 대본을 생성·수정·요약하지 말고 transcript 또는 exact_transcript 필드를 반환하지 마세요.

반드시 총 12개 후보를 반환하세요. 그중 앞의 4개는 최종 후보로 사용할 수 있도록 서로 시간대가 겹치지 않아야 합니다.
앞의 4개 각각은 30~75초(권장 45~65초)이며 문장 경계에서 시작·종료해야 합니다.
인사·광고·행사 안내는 피하고 핵심 메시지, 삶의 적용, 위로, 강한 질문을 다양하게 포함하세요.
각 후보에 centrality, standalone, hook, emotional_impact, overall(0~100)과 서로 다른 유형의 한국어 제목 3개를 주세요.
overall은 centrality 30%, standalone 30%, hook 20%, emotional_impact 20%를 기준으로 계산하세요.
영상 길이: {duration_seconds:.2f}초

{timestamped_transcript}"""
        repair_prompt = base_prompt + """

중요: 이전 후보안은 최종 4개가 서로 겹치거나 길이 조건을 지켜 통과하지 못했습니다.
이번에는 먼저 전체 시간대를 나누고, 앞의 4개를 서로 절대 겹치지 않는 실제 segment_id 범위로 확정한 뒤 나머지 8개를 추가하세요.
첫 4개 중 하나라도 30초 미만·75초 초과·존재하지 않는 segment_id·다른 첫 4개와 시간 겹침이면 응답 전체가 사용되지 않습니다."""
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "당신은 설교의 의미를 왜곡하지 않는 한국어 영상 편집자입니다."},
                        {"role": "user", "content": base_prompt if attempt == 0 else repair_prompt},
                    ],
                    response_format=SermonAnalysisResult,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("empty structured response")
                if _has_four_valid_non_overlapping_candidates(parsed, segments, duration_seconds):
                    return parsed
                last_error = ValueError("insufficient non-overlapping candidate ranges")
            except Exception as exc:
                last_error = exc
        raise SermonAnalysisError("AI 후보 분석 응답을 검증하지 못했습니다. 잠시 후 다시 시도해 주세요.") from last_error


class MockSermonAnalysisService(SermonAnalysisService):
    TOPICS = [
        ("기다림 속의 믿음", "핵심 메시지", "답이 보이지 않는 시간에도 믿음을 지키는 설교의 중심 주장입니다."),
        ("오늘의 작은 순종", "삶의 적용", "청자가 바로 실천할 수 있는 구체적인 적용을 담고 있습니다."),
        ("지친 마음을 세우는 은혜", "위로와 격려", "지친 청자에게 정서적·영적 위로를 주는 독립적인 메시지입니다."),
        ("실패는 마지막이 아닙니다", "강한 한 문장", "강한 선언으로 시작해 새로운 소망으로 자연스럽게 마무리됩니다."),
        ("기도에 솔직해지는 법", "삶의 적용", "상처를 숨기지 않고 기도로 가져가는 실천을 설명합니다."),
        ("함께 짐을 지는 교회", "핵심 메시지", "공동체가 복음을 보여 주는 방식을 한 주제로 완결합니다."),
        ("하나님의 침묵", "강한 질문", "응답이 없을 때 품는 질문에서 믿음의 결론으로 이어집니다."),
        ("은혜는 선물입니다", "위로와 격려", "은혜의 의미를 짧고 기억하기 쉬운 문장으로 전달합니다."),
    ]

    def analyze(self, segments: Sequence[StoredTranscriptSegmentData], duration_seconds: float) -> SermonAnalysisResult:
        if duration_seconds < 120:
            raise SermonAnalysisError("4개의 30초 후보를 만들려면 영상 길이가 최소 2분이어야 합니다.")
        target = min(60.0, max(30.0, duration_seconds / 5.0))
        gap = max(0.0, (duration_seconds - target * 4) / 5)
        candidates: List[AnalysisCandidate] = []
        for index, (topic, recommendation_type, reason) in enumerate(self.TOPICS):
            lane = index % 4
            start = gap + lane * (target + gap)
            if index >= 4:
                start = min(duration_seconds - target, start + target * 0.08)
            start_index = min(range(len(segments)), key=lambda value: abs(segments[value].start_sec - start))
            end_index = start_index
            while end_index + 1 < len(segments) and segments[end_index].end_sec - segments[start_index].start_sec < target:
                end_index += 1
            score = 94 - index * 2
            candidates.append(AnalysisCandidate(
                start_segment_id=segments[start_index].segment_id,
                end_segment_id=segments[end_index].segment_id,
                main_topic=topic,
                recommendation_type=recommendation_type,
                selection_reason=reason,
                scores=AnalysisScores(
                    centrality=score,
                    standalone=max(70, score - 1),
                    hook=max(70, score - 4),
                    emotional_impact=max(70, score - 2),
                    overall=max(70, score - 2),
                ),
                titles=[
                    AnalysisTitle(title=f"{topic}, 왜 지금 중요할까요?", type="질문형"),
                    AnalysisTitle(title=f"{topic}은 우리를 다시 세웁니다", type="단정형"),
                    AnalysisTitle(title=f"우리가 놓치고 있던 {topic}", type="호기심형"),
                ],
            ))
        return SermonAnalysisResult(
            sermon_summary="응답을 기다리는 시간에도 하나님을 신뢰하고, 작은 순종과 공동체의 사랑으로 믿음을 살아 내자는 설교입니다.",
            sermon_topics=["믿음", "기다림", "순종", "은혜"],
            candidates=candidates,
        )


@dataclass(frozen=True)
class SelectedCandidate:
    analysis: AnalysisCandidate
    start_segment_id: int
    end_segment_id: int
    start_sec: float
    end_sec: float
    segment_count: int


def normalize_and_select_candidates(
    result: SermonAnalysisResult,
    segments: Sequence[StoredTranscriptSegmentData],
    duration_seconds: float,
    limit: int = 4,
) -> List[SelectedCandidate]:
    if not segments:
        raise SermonAnalysisError("분석할 대본이 없습니다.")
    ordered = sorted(segments, key=lambda item: item.segment_order)
    index_by_id = {item.segment_id: index for index, item in enumerate(ordered)}
    normalized: List[SelectedCandidate] = []
    for candidate in result.candidates:
        if candidate.start_segment_id not in index_by_id or candidate.end_segment_id not in index_by_id:
            continue
        start_index = index_by_id[candidate.start_segment_id]
        end_index = index_by_id[candidate.end_segment_id]
        if end_index < start_index:
            continue
        while ordered[end_index].end_sec - ordered[start_index].start_sec < 30 and end_index + 1 < len(ordered):
            end_index += 1
        while ordered[end_index].end_sec - ordered[start_index].start_sec > 75 and end_index > start_index:
            end_index -= 1
        start = max(0.0, ordered[start_index].start_sec)
        end = min(duration_seconds, ordered[end_index].end_sec)
        if 30 <= end - start <= 75:
            normalized.append(SelectedCandidate(
                analysis=candidate,
                start_segment_id=ordered[start_index].segment_id,
                end_segment_id=ordered[end_index].segment_id,
                start_sec=start,
                end_sec=end,
                segment_count=end_index - start_index + 1,
            ))

    normalized.sort(key=lambda item: item.analysis.scores.overall, reverse=True)
    selected: List[SelectedCandidate] = []
    used_topics: set[str] = set()
    for item in normalized:
        if any(max(item.start_sec, chosen.start_sec) < min(item.end_sec, chosen.end_sec) for chosen in selected):
            continue
        if item.analysis.main_topic in used_topics and len(normalized) - len(selected) > limit:
            continue
        selected.append(item)
        used_topics.add(item.analysis.main_topic)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        raise SermonAnalysisError("서로 겹치지 않는 유효한 쇼츠 후보 4개를 만들지 못했습니다.")
    return sorted(selected, key=lambda item: item.start_sec)


def _has_four_valid_non_overlapping_candidates(
    result: SermonAnalysisResult,
    segments: Sequence[StoredTranscriptSegmentData],
    duration_seconds: float,
) -> bool:
    try:
        normalize_and_select_candidates(result, segments, duration_seconds, limit=4)
    except SermonAnalysisError:
        return False
    return True
