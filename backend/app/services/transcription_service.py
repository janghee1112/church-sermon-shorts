from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Callable, Dict, Iterable, List, Optional

from openai import OpenAI

from app.schemas.analysis import TranscriptSegmentData, TranscriptionResult, TranscriptWordData
from app.services.video_service import AudioChunk


SERMON_VOCABULARY = [
    "하나님", "예수님", "성령", "성경", "창세기", "출애굽기", "시편", "마태복음",
    "요한복음", "로마서", "고린도전서", "데살로니가전서", "믿음", "은혜", "구원",
    "회개", "기도", "복음", "언약", "성화", "칭의",
]


class TranscriptionError(Exception):
    pass


class TranscriptionService(ABC):
    @abstractmethod
    def transcribe(
        self,
        chunks: List[AudioChunk],
        duration_seconds: float,
        extra_vocabulary: Optional[List[str]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> TranscriptionResult:
        raise NotImplementedError


class OpenAITranscriptionService(TranscriptionService):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise TranscriptionError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def transcribe(
        self,
        chunks: List[AudioChunk],
        duration_seconds: float,
        extra_vocabulary: Optional[List[str]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> TranscriptionResult:
        vocabulary = SERMON_VOCABULARY + (extra_vocabulary or [])
        merged: List[TranscriptSegmentData] = []
        try:
            for index, chunk in enumerate(chunks):
                with chunk.path.open("rb") as audio_file:
                    request_options: Dict[str, object] = dict(
                        model=self.model,
                        file=audio_file,
                        language="ko",
                        prompt="다음은 한국어 교회 설교입니다. 고유명사: " + ", ".join(vocabulary),
                    )
                    if self.model == "whisper-1":
                        request_options.update(response_format="verbose_json", timestamp_granularities=["segment", "word"])
                    else:
                        request_options.update(response_format="json")
                    response = self.client.audio.transcriptions.create(**request_options)  # type: ignore[arg-type]
                fallback_end = chunks[index + 1].offset_seconds if index + 1 < len(chunks) else duration_seconds
                merged.extend(self._convert_response(response, chunk.offset_seconds, fallback_end))
                if on_progress:
                    on_progress(30 + round(35 * (index + 1) / len(chunks)))
        except Exception as exc:
            raise TranscriptionError("음성 전사 API 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.") from exc
        deduped = self._deduplicate(merged)
        return TranscriptionResult(text=" ".join(item.text for item in deduped), segments=deduped)

    @staticmethod
    def _as_dict(item: object) -> Dict[str, object]:
        if hasattr(item, "model_dump"):
            return getattr(item, "model_dump")()
        return dict(item) if isinstance(item, dict) else vars(item)

    def _convert_response(self, response: object, offset: float, fallback_end: float) -> List[TranscriptSegmentData]:
        response_dict = self._as_dict(response)
        raw_segments = response_dict.get("segments") or []
        raw_words = [self._as_dict(item) for item in (response_dict.get("words") or [])]
        segments: List[TranscriptSegmentData] = []
        for raw in raw_segments:
            item = self._as_dict(raw)
            start = float(item.get("start") or 0) + offset
            end = float(item.get("end") or start) + offset
            words = [
                TranscriptWordData(
                    word=str(word.get("word") or "").strip(),
                    start_sec=float(word.get("start") or 0) + offset,
                    end_sec=float(word.get("end") or 0) + offset,
                )
                for word in raw_words
                if start - offset <= float(word.get("start") or 0) < end - offset
            ]
            text = str(item.get("text") or "").strip()
            if text:
                segments.append(TranscriptSegmentData(start_sec=start, end_sec=end, text=text, words=words))
        if not segments:
            text = str(response_dict.get("text") or "").strip()
            if text:
                sentences = [item.strip() for item in re.findall(r"[^.!?。！？]+[.!?。！？]?", text) if item.strip()]
                if len(sentences) <= 1:
                    tokens = text.split()
                    target_count = min(len(tokens), max(1, round((fallback_end - offset) / 10)))
                    chunk_size = max(1, (len(tokens) + target_count - 1) // target_count)
                    sentences = [" ".join(tokens[index:index + chunk_size]) for index in range(0, len(tokens), chunk_size)]
                step = max(1.0, (fallback_end - offset) / len(sentences))
                for index, sentence in enumerate(sentences):
                    start = offset + index * step
                    end = fallback_end if index == len(sentences) - 1 else min(fallback_end, start + step)
                    segments.append(TranscriptSegmentData(start_sec=start, end_sec=end, text=sentence))
        return segments

    @staticmethod
    def _deduplicate(segments: Iterable[TranscriptSegmentData]) -> List[TranscriptSegmentData]:
        result: List[TranscriptSegmentData] = []
        for segment in sorted(segments, key=lambda item: item.start_sec):
            duplicate = False
            for previous in result[-3:]:
                time_overlap = min(previous.end_sec, segment.end_sec) - max(previous.start_sec, segment.start_sec)
                similarity = SequenceMatcher(None, previous.text, segment.text).ratio()
                if time_overlap > 0 and similarity >= 0.82:
                    duplicate = True
                    break
            if not duplicate:
                result.append(segment)
        return result


class MockTranscriptionService(TranscriptionService):
    SAMPLE_TEXTS = [
        "우리는 기도하고도 응답이 없다고 느낄 때가 있습니다.",
        "그러나 하나님의 침묵은 우리를 외면하셨다는 뜻이 아닙니다.",
        "기다리는 시간에도 하나님은 우리의 믿음을 단단하게 빚고 계십니다.",
        "믿음은 모든 답을 아는 것이 아니라 답이 없어도 하나님을 신뢰하는 것입니다.",
        "오늘 내가 할 수 있는 작은 순종이 내일의 길을 엽니다.",
        "상처받은 마음을 숨기지 말고 기도로 하나님께 솔직히 가져가십시오.",
        "은혜는 강한 사람에게 주는 상이 아니라 지친 사람을 다시 세우는 선물입니다.",
        "우리가 서로의 짐을 질 때 교회는 세상에 복음을 보여 줍니다.",
        "실패가 마지막 문장이 되도록 두지 마십시오. 하나님은 새 문장을 쓰십니다.",
        "이번 한 주도 말씀을 붙들고 사랑을 선택하며 살아가길 바랍니다.",
    ]

    def transcribe(
        self,
        chunks: List[AudioChunk],
        duration_seconds: float,
        extra_vocabulary: Optional[List[str]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> TranscriptionResult:
        segment_length = max(4.0, min(12.0, duration_seconds / max(10, int(duration_seconds / 8))))
        count = max(10, int(duration_seconds / segment_length))
        segments: List[TranscriptSegmentData] = []
        for index in range(count):
            start = index * duration_seconds / count
            end = (index + 1) * duration_seconds / count
            text = self.SAMPLE_TEXTS[index % len(self.SAMPLE_TEXTS)]
            tokens = text.split()
            words = [
                TranscriptWordData(
                    word=token,
                    start_sec=start + (end - start) * word_index / len(tokens),
                    end_sec=start + (end - start) * (word_index + 1) / len(tokens),
                )
                for word_index, token in enumerate(tokens)
            ]
            segments.append(TranscriptSegmentData(start_sec=start, end_sec=end, text=text, words=words))
        if on_progress:
            on_progress(65)
        return TranscriptionResult(text=" ".join(item.text for item in segments), segments=segments)
