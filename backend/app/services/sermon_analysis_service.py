import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence

from openai import OpenAI

from app.schemas.analysis import (
    AnalysisCandidate,
    AnalysisScores,
    AnalysisTitle,
    CandidateTitleResult,
    CandidateDiscoveryResult,
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
        timestamped_transcript = _timestamped_transcript(segments)
        discovery_prompt = f"""당신은 YouTube Shorts 콘텐츠 편집자이자 설교 맥락 검증자입니다.
아래 한국어 설교 transcript에서 잠재 쇼츠 후보를 넓게 10~15개 탐색하세요.
최종 4개를 바로 고르지 말고, 서로 다른 주제와 감정 진입점을 최대한 넓게 포함하세요.

시청자는 기독교 영상을 검색한 사람이 아니라 연예인·게임·음식·뉴스 Shorts를 보다가 우연히 만난 20~40대 일반인입니다.
후보는 20~75초 범위, 권장 25~55초이며 문장(세그먼트) 경계에서 시작하고 끝나야 합니다.
첫 1~3초에 질문, 갈등, 반전, 불편한 진실, 자기진단, 강한 단언, 실제 사례가 드러나는 구간을 우선 탐색하세요.
비교·질투·돈·성공·실패·불안·미래·외로움·관계·부모·부부·용서·배신·자존감·후회·직장·번아웃 같은 보편적 문제를 신앙 메시지와 연결한 구간을 우선하세요.
“사랑하는 성도 여러분”, 본문 장절 낭독, 인사, 광고, 긴 배경 설명, 교회 내부 용어만으로 시작하는 구간은 피하세요.

반드시 제공된 segment_id만 사용하세요. AI가 문장·시간·대사를 만들거나 고쳐 쓰지 마세요.
raw_opening_sentence는 해당 시작 세그먼트의 실제 문장을 그대로 복사할 때만 채우고, 서버는 최종 대본을 DB에서 다시 구성합니다.
context_integrity는 앞뒤 맥락을 잘라도 목사님의 뜻이 왜곡되지 않으면 true, 질문·조건문·비꼼을 잘못 보이게 하면 false입니다.
반환 필드는 JSON 스키마에 맞추고 transcript/exact_transcript/요약 대사를 반환하지 마세요.
영상 길이: {duration_seconds:.2f}초

{timestamped_transcript}"""
        discovery = self._request_structured(
            discovery_prompt,
            CandidateDiscoveryResult,
            "설교 의미를 보존하면서 실제 세그먼트로 쇼츠 잠재 후보를 넓게 탐색하는 편집자",
        )
        pool = json.dumps(discovery.model_dump(mode="json"), ensure_ascii=False)
        scoring_prompt = f"""당신은 Shorts 콘텐츠 편집자이자 설교 맥락 검증자입니다.
아래 transcript와 잠재 후보 목록을 바탕으로 각 후보를 0~100점으로 재평가하세요.
잠재 후보를 충분히 비교한 뒤 4개 이상 15개 이하를 반환하고, 서버가 최종 4개를 점수·중복·다양성 기준으로 선택합니다.

핵심 시청자는 교회에 다니지 않아도 이해할 수 있는 20~40대 일반 Shorts 시청자입니다.
평가 가중치는 다음과 같습니다.
- hook_strength 25
- universal_relevance 20
- curiosity_gap 15
- payoff_strength 15
- standalone_clarity 10
- emotional_intensity 10
- brevity_efficiency 5

추가로 opening_3s_score(첫 3초), scroll_stop_score(다른 Shorts를 보던 중 멈출 가능성),
non_christian_clarity_score, title_potential_score, information_density_score를 평가하세요.
첫 문장이 상투적이면 opening과 scroll_stop을 낮추세요. 마지막에 명확한 답·반전·행동 기준·위로·경고·자기인식이 없으면 payoff를 낮추세요.
context_integrity가 false인 후보는 절대 추천하지 마세요. AI가 새 문장, 대본, 직접 발언, 제목용 가짜 인용을 만들지 마세요.
각 후보에 main_topic, recommendation_type, selection_reason, shorts_scores를 채우세요.
제목 3개는 실제 transcript의 뜻을 왜곡하지 않는 질문형·감정형·통념깨기형 등으로 작성하세요.
후보의 시작·종료는 반드시 제공된 segment_id로만 반환하고, transcript/exact_transcript 필드는 반환하지 마세요.

잠재 후보 목록:
{pool}

전체 timestamped transcript:
{timestamped_transcript}"""
        scored = self._request_structured(
            scoring_prompt,
            SermonAnalysisResult,
            "잠재 후보의 초반 훅·일반인 공감·완결성과 맥락을 검증하는 Shorts 평가자",
        )
        selected = normalize_and_select_candidates(scored, segments, duration_seconds, limit=4)
        ordered_segments = sorted(segments, key=lambda segment: segment.segment_order)
        segment_index_by_id = {segment.segment_id: index for index, segment in enumerate(ordered_segments)}
        title_payload = json.dumps(
            [
                {
                    "start_segment_id": item.start_segment_id,
                    "end_segment_id": item.end_segment_id,
                    "segments": [
                        {
                            "segment_id": segment.segment_id,
                            "start_sec": segment.start_sec,
                            "end_sec": segment.end_sec,
                            "text": segment.text,
                        }
                        for segment in ordered_segments[
                            segment_index_by_id[item.start_segment_id]:segment_index_by_id[item.end_segment_id] + 1
                        ]
                    ],
                }
                for item in selected
            ],
            ensure_ascii=False,
        )
        title_prompt = f"""최종 쇼츠 후보 4개에 대해 제목을 각 3개씩 생성하세요.
제목은 실제 대본의 의미와 일치하는 짧은 한국어 문장이어야 하며 질문형·감정형·통념깨기형처럼 유형을 서로 다르게 하세요.
본문에 없는 발언을 직접 인용처럼 만들거나 과장된 clickbait(99%, 당신은 속고 있습니다 등)를 쓰지 마세요.
반드시 입력된 start_segment_id/end_segment_id를 그대로 반환하세요.
입력된 segments의 실제 대사를 수정하거나 요약해 transcript로 반환하지 마세요.

최종 후보 원문 세그먼트:
{title_payload}"""
        title_result = self._request_structured(
            title_prompt,
            CandidateTitleResult,
            "최종 4개 후보의 실제 내용에 근거한 정직한 Shorts 제목 편집자",
        )
        titles_by_range = {
            (item.start_segment_id, item.end_segment_id): item.titles
            for item in title_result.candidates
        }
        final_candidates: List[AnalysisCandidate] = []
        for item in selected:
            titles = titles_by_range.get((item.start_segment_id, item.end_segment_id))
            if not titles:
                raise SermonAnalysisError("최종 후보 제목 응답을 검증하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            item.analysis.titles = titles
            final_candidates.append(item.analysis)
        return SermonAnalysisResult(
            sermon_summary=scored.sermon_summary,
            sermon_topics=scored.sermon_topics,
            candidates=final_candidates,
        )

    def _request_structured(self, prompt: str, response_model: type, system_message: str):
        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=response_model,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("empty structured response")
                return parsed
            except Exception as exc:
                last_error = exc
        raise SermonAnalysisError("AI 후보 분석 응답을 검증하지 못했습니다. 잠시 후 다시 시도해 주세요.") from last_error


class MockSermonAnalysisService(SermonAnalysisService):
    TOPICS = [
        ("기다림 속의 믿음", "핵심 메시지", "답이 보이지 않는 시간에도 믿음을 지키는 설교의 중심 주장입니다.", ["hope", "anxiety"]),
        ("오늘의 작은 순종", "삶의 적용", "청자가 바로 실천할 수 있는 구체적인 적용을 담고 있습니다.", ["motivation", "identity"]),
        ("지친 마음을 세우는 은혜", "위로와 격려", "지친 청자에게 정서적·영적 위로를 주는 독립적인 메시지입니다.", ["relief", "hope"]),
        ("실패는 마지막이 아닙니다", "강한 한 문장", "강한 선언으로 시작해 새로운 소망으로 자연스럽게 마무리됩니다.", ["regret", "hope"]),
        ("기도에 솔직해지는 법", "삶의 적용", "상처를 숨기지 않고 기도로 가져가는 실천을 설명합니다.", ["guilt", "relief"]),
        ("함께 짐을 지는 교회", "핵심 메시지", "공동체가 복음을 보여 주는 방식을 한 주제로 완결합니다.", ["loneliness", "relationship"]),
        ("하나님의 침묵", "강한 질문", "응답이 없을 때 품는 질문에서 믿음의 결론으로 이어집니다.", ["anxiety", "curiosity"]),
        ("은혜는 선물입니다", "위로와 격려", "은혜의 의미를 짧고 기억하기 쉬운 문장으로 전달합니다.", ["relief", "hope"]),
        ("비교에서 벗어나는 법", "자기진단", "남과 비교하며 작아지는 마음을 돌아보고 시선을 바꾸는 구간입니다.", ["comparison", "jealousy"]),
        ("용서가 어려운 이유", "갈등", "용서하면 손해 보는 것처럼 느끼는 현실적인 갈등을 다룹니다.", ["anger", "relationship"]),
        ("만족과 돈의 관계", "통념 깨기", "더 가지면 만족할 것이라는 통념을 뒤집고 진짜 만족을 설명합니다.", ["money", "identity"]),
        ("불안한 미래를 맡기는 법", "강한 질문", "미래를 통제하려는 마음에서 믿음의 선택으로 넘어갑니다.", ["anxiety", "fear"]),
    ]

    def analyze(self, segments: Sequence[StoredTranscriptSegmentData], duration_seconds: float) -> SermonAnalysisResult:
        if duration_seconds < 120:
            raise SermonAnalysisError("4개의 쇼츠 후보를 만들려면 영상 길이가 최소 2분이어야 합니다.")
        target = min(60.0, max(30.0, duration_seconds / 5.0))
        gap = max(0.0, (duration_seconds - target * 4) / 5)
        candidates: List[AnalysisCandidate] = []
        for index, (topic, recommendation_type, reason, triggers) in enumerate(self.TOPICS):
            lane = index % 4
            start = gap + lane * (target + gap)
            if index >= 4:
                start = min(duration_seconds - target, start + target * 0.08)
            start_index = min(range(len(segments)), key=lambda value: abs(segments[value].start_sec - start))
            end_index = start_index
            while end_index + 1 < len(segments) and segments[end_index].end_sec - segments[start_index].start_sec < target:
                end_index += 1
            score = max(62, 94 - index * 2)
            shorts_scores = {
                "hook_strength": max(55, score - 1),
                "universal_relevance": max(55, score - 3),
                "curiosity_gap": max(55, score - 5),
                "payoff_strength": max(55, score - 2),
                "standalone_clarity": max(55, score - 1),
                "emotional_intensity": max(55, score - 4),
                "brevity_efficiency": max(55, score - 6),
            }
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
                shorts_scores=shorts_scores,
                opening_3s_score=max(60, score - 3),
                scroll_stop_score=max(60, score - 4),
                non_christian_clarity_score=max(60, score - 2),
                title_potential_score=max(60, score - 2),
                information_density_score=max(60, score - 5),
                emotional_triggers=triggers,
                core_theme=topic,
                raw_opening_sentence=segments[start_index].text,
                expected_payoff=reason,
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


def _timestamped_transcript(segments: Sequence[StoredTranscriptSegmentData]) -> str:
    return json.dumps(
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


@dataclass(frozen=True)
class SelectedCandidate:
    analysis: AnalysisCandidate
    start_segment_id: int
    end_segment_id: int
    start_sec: float
    end_sec: float
    segment_count: int

    @property
    def ranking_score(self) -> int:
        return self.analysis.effective_shorts_score()


WEAK_OPENING_PATTERNS = (
    "사랑하는 성도",
    "사랑하는 여러분",
    "오늘 본문",
    "오늘 말씀",
    "이 시간에는",
    "우리가 이 말씀",
    "하나님께서는 우리에게",
)
OPENING_HOOK_MARKERS = ("왜", "오해", "아닙니다", "그런데", "사실", "불편", "손해", "만족", "정말")
THEME_CLUSTERS = (
    {"비교", "질투", "열등감", "자존감", "인정", "인정욕구"},
    {"돈", "성공", "만족", "자족", "부족", "소유"},
    {"관계", "용서", "배신", "부부", "부모", "자녀", "친구"},
    {"불안", "미래", "두려움", "걱정", "염려"},
    {"실패", "후회", "죄책감", "분노", "상처"},
)


def _is_weak_opening(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    for pattern in WEAK_OPENING_PATTERNS:
        compact_pattern = re.sub(r"\s+", "", pattern)
        if not normalized.startswith(compact_pattern):
            continue
        remainder = normalized[len(compact_pattern):len(compact_pattern) + 24]
        if any(marker in remainder for marker in OPENING_HOOK_MARKERS):
            return False
        if len(remainder) <= 6 or remainder.startswith(("오늘", "본문", "말씀을", "이야기를")):
            return True
    return False


def _candidate_theme_tokens(item: AnalysisCandidate) -> set[str]:
    source = " ".join(
        [
            item.core_theme or item.main_topic,
            item.main_topic,
            *item.emotional_triggers,
        ]
    ).lower()
    return {token for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", source) if token}


def _theme_similarity(left: AnalysisCandidate, right: AnalysisCandidate) -> float:
    left_tokens = _candidate_theme_tokens(left)
    right_tokens = _candidate_theme_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    exact = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    cluster_overlap = 0.0
    for cluster in THEME_CLUSTERS:
        if left_tokens & cluster and right_tokens & cluster:
            cluster_overlap = max(cluster_overlap, 0.65)
    return max(exact, cluster_overlap)


def _prepare_candidate(
    candidate: AnalysisCandidate,
    ordered: Sequence[StoredTranscriptSegmentData],
    start_index: int,
    end_index: int,
) -> tuple[int, int]:
    """Trim a generic spoken introduction when doing so preserves a valid clip."""
    if candidate.context_integrity and _is_weak_opening(ordered[start_index].text):
        while start_index < end_index and end_index < len(ordered) and ordered[end_index].end_sec - ordered[start_index + 1].start_sec >= 20:
            if not _is_weak_opening(ordered[start_index].text):
                break
            start_index += 1
    return start_index, end_index


def _effective_length_bounds(
    ordered: Sequence[StoredTranscriptSegmentData],
    start_index: int,
    end_index: int,
) -> tuple[int, int] | None:
    """Use sentence boundaries without padding a candidate beyond 75 seconds."""
    while end_index - start_index >= 0 and ordered[end_index].end_sec - ordered[start_index].start_sec > 75 and end_index > start_index:
        end_index -= 1
    if ordered[end_index].end_sec - ordered[start_index].start_sec < 20:
        while end_index + 1 < len(ordered) and ordered[end_index].end_sec - ordered[start_index].start_sec < 20:
            end_index += 1
        if ordered[end_index].end_sec - ordered[start_index].start_sec < 20:
            return None
    duration = ordered[end_index].end_sec - ordered[start_index].start_sec
    if duration < 20 or duration > 75:
        return None
    return start_index, end_index


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
        if not candidate.context_integrity:
            continue
        if candidate.start_segment_id not in index_by_id or candidate.end_segment_id not in index_by_id:
            continue
        start_index = index_by_id[candidate.start_segment_id]
        end_index = index_by_id[candidate.end_segment_id]
        if end_index < start_index:
            continue
        start_index, end_index = _prepare_candidate(candidate, ordered, start_index, end_index)
        bounds = _effective_length_bounds(ordered, start_index, end_index)
        if bounds is None:
            continue
        start_index, end_index = bounds
        start = max(0.0, ordered[start_index].start_sec)
        end = min(duration_seconds, ordered[end_index].end_sec)
        if 20 <= end - start <= 75:
            normalized.append(SelectedCandidate(
                analysis=candidate,
                start_segment_id=ordered[start_index].segment_id,
                end_segment_id=ordered[end_index].segment_id,
                start_sec=start,
                end_sec=end,
                segment_count=end_index - start_index + 1,
            ))

    normalized.sort(key=lambda item: item.ranking_score, reverse=True)
    selected: List[SelectedCandidate] = []
    for item in normalized:
        if any(max(item.start_sec, chosen.start_sec) < min(item.end_sec, chosen.end_sec) for chosen in selected):
            continue
        if any(_theme_similarity(item.analysis, chosen.analysis) >= 0.60 for chosen in selected):
            continue
        selected.append(item)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        # If strict semantic diversity leaves too few clips, fill from the best
        # non-overlapping candidates while preserving the no-overlap policy.
        for item in normalized:
            if item in selected:
                continue
            if any(max(item.start_sec, chosen.start_sec) < min(item.end_sec, chosen.end_sec) for chosen in selected):
                continue
            selected.append(item)
            if len(selected) == limit:
                break
    if len(selected) < limit:
        raise SermonAnalysisError("서로 겹치지 않는 유효한 쇼츠 후보 4개를 만들지 못했습니다.")
    return sorted(selected, key=lambda item: item.start_sec)
