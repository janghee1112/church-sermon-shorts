from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    original_file_name: str
    stored_file_name: str
    duration_seconds: float
    width: int
    height: int
    file_size: int
    status: str
    progress: int
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    analysis_mode: str
    created_at: datetime
    updated_at: datetime


class WordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    word: str
    start_sec: float
    end_sec: float


class SegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    start_sec: float
    end_sec: float
    text: str
    segment_order: int
    words: List[WordResponse] = Field(default_factory=list)


class TranscriptResponse(BaseModel):
    project_id: str
    full_text: str
    segments: List[SegmentResponse]


class TitleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    title_type: str
    title_order: int


class ScoresResponse(BaseModel):
    centrality: int
    standalone: int
    hook: int
    emotional_impact: int
    overall: int


class CandidateResponse(BaseModel):
    id: int
    candidate_order: int
    recommendation_type: str
    start_sec: float
    end_sec: float
    duration_sec: float
    transcript: str
    main_topic: str
    selection_reason: str
    scores: ScoresResponse
    titles: List[TitleResponse]
    shorts_score: int = 0
    opening_3s_score: int = 0
    scroll_stop_score: int = 0
    non_christian_clarity_score: int = 0
    emotional_triggers: List[str] = Field(default_factory=list)
    context_integrity: bool = True
    core_theme: Optional[str] = None


class CandidateDebugResponse(BaseModel):
    candidate_order: int
    start_segment_id: Optional[int] = None
    end_segment_id: Optional[int] = None
    segment_count: int
    shorts_score: int = 0
    hook_strength: int = 0
    universal_relevance: int = 0
    curiosity_gap: int = 0
    payoff_strength: int = 0
    standalone_clarity: int = 0
    emotional_intensity: int = 0
    brevity_efficiency: int = 0
    opening_3s_score: int = 0
    scroll_stop_score: int = 0
    non_christian_clarity_score: int = 0
    title_potential_score: int = 0
    information_density_score: int = 0
    context_integrity: bool = True
    emotional_triggers: List[str] = Field(default_factory=list)
    core_theme: Optional[str] = None


class TranscriptBoundaryDebugResponse(BaseModel):
    segment_id: int
    start_sec: float
    end_sec: float
    text: str


class AnalysisDebugResponse(BaseModel):
    analysis_mode: str
    transcription_model: Optional[str] = None
    transcript_segment_count: int
    transcript_char_count: int
    first_segment: Optional[TranscriptBoundaryDebugResponse] = None
    last_segment: Optional[TranscriptBoundaryDebugResponse] = None
    candidates: List[CandidateDebugResponse] = Field(default_factory=list)


class CandidatesResponse(BaseModel):
    project_id: str
    analysis_mode: str
    sermon_summary: str
    sermon_topics: List[str]
    candidates: List[CandidateResponse]
    debug: Optional[AnalysisDebugResponse] = None
