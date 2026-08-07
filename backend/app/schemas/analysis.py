from typing import List

from pydantic import BaseModel, Field, model_validator


class TranscriptWordData(BaseModel):
    word: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)


class TranscriptSegmentData(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    text: str = Field(min_length=1)
    words: List[TranscriptWordData] = Field(default_factory=list)


class StoredTranscriptSegmentData(BaseModel):
    segment_id: int
    segment_order: int = Field(ge=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_boundary(self) -> "StoredTranscriptSegmentData":
        if self.end_sec <= self.start_sec:
            raise ValueError("segment end must be later than start")
        return self


class TranscriptionResult(BaseModel):
    text: str
    segments: List[TranscriptSegmentData]


class AnalysisScores(BaseModel):
    centrality: int = Field(ge=0, le=100)
    standalone: int = Field(ge=0, le=100)
    hook: int = Field(ge=0, le=100)
    emotional_impact: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def calculate_overall(self) -> "AnalysisScores":
        self.overall = round(
            self.centrality * 0.30
            + self.standalone * 0.30
            + self.hook * 0.20
            + self.emotional_impact * 0.20
        )
        return self


class AnalysisTitle(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=30)


class AnalysisCandidate(BaseModel):
    start_segment_id: int = Field(gt=0)
    end_segment_id: int = Field(gt=0)
    main_topic: str
    recommendation_type: str = "핵심 메시지"
    selection_reason: str
    scores: AnalysisScores
    titles: List[AnalysisTitle] = Field(min_length=3, max_length=3)

class SermonAnalysisResult(BaseModel):
    sermon_summary: str
    sermon_topics: List[str]
    candidates: List[AnalysisCandidate] = Field(min_length=4)
