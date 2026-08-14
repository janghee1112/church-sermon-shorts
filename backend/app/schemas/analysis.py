from typing import List, Optional

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
    centrality: int = Field(default=0, ge=0, le=100)
    standalone: int = Field(default=0, ge=0, le=100)
    hook: int = Field(default=0, ge=0, le=100)
    emotional_impact: int = Field(default=0, ge=0, le=100)
    overall: int = Field(default=0, ge=0, le=100)
    # Accept the newer Shorts metrics inside the legacy ``scores`` object too.
    # This keeps structured responses compatible with earlier prompt variants.
    hook_strength: int = Field(default=0, ge=0, le=100)
    universal_relevance: int = Field(default=0, ge=0, le=100)
    curiosity_gap: int = Field(default=0, ge=0, le=100)
    payoff_strength: int = Field(default=0, ge=0, le=100)
    standalone_clarity: int = Field(default=0, ge=0, le=100)
    emotional_intensity: int = Field(default=0, ge=0, le=100)
    brevity_efficiency: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def calculate_overall(self) -> "AnalysisScores":
        self.overall = round(
            self.centrality * 0.30
            + self.standalone * 0.30
            + self.hook * 0.20
            + self.emotional_impact * 0.20
        )
        return self


class ShortsEvaluationScores(BaseModel):
    """Shorts-first evaluation values returned by the analysis model."""

    hook_strength: int = Field(default=0, ge=0, le=100)
    universal_relevance: int = Field(default=0, ge=0, le=100)
    curiosity_gap: int = Field(default=0, ge=0, le=100)
    payoff_strength: int = Field(default=0, ge=0, le=100)
    standalone_clarity: int = Field(default=0, ge=0, le=100)
    emotional_intensity: int = Field(default=0, ge=0, le=100)
    brevity_efficiency: int = Field(default=0, ge=0, le=100)

    def weighted_score(self) -> int:
        return round(
            self.hook_strength * 0.25
            + self.universal_relevance * 0.20
            + self.curiosity_gap * 0.15
            + self.payoff_strength * 0.15
            + self.standalone_clarity * 0.10
            + self.emotional_intensity * 0.10
            + self.brevity_efficiency * 0.05
        )


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
    titles: List[AnalysisTitle] = Field(default_factory=list, max_length=3)
    shorts_scores: ShortsEvaluationScores = Field(default_factory=ShortsEvaluationScores)
    shorts_score: Optional[int] = Field(default=None, ge=0, le=100)
    opening_3s_score: int = Field(default=0, ge=0, le=100)
    scroll_stop_score: int = Field(default=0, ge=0, le=100)
    non_christian_clarity_score: int = Field(default=0, ge=0, le=100)
    title_potential_score: int = Field(default=0, ge=0, le=100)
    information_density_score: int = Field(default=0, ge=0, le=100)
    context_integrity: bool = True
    emotional_triggers: List[str] = Field(default_factory=list, max_length=5)
    core_theme: Optional[str] = None
    raw_opening_sentence: Optional[str] = None
    expected_payoff: Optional[str] = None

    def shorts_evaluation_scores(self) -> ShortsEvaluationScores:
        nested = ShortsEvaluationScores.model_validate(self.shorts_scores)
        if nested.weighted_score() > 0:
            return nested
        inline = ShortsEvaluationScores.model_validate({
            "hook_strength": self.scores.hook_strength,
            "universal_relevance": self.scores.universal_relevance,
            "curiosity_gap": self.scores.curiosity_gap,
            "payoff_strength": self.scores.payoff_strength,
            "standalone_clarity": self.scores.standalone_clarity,
            "emotional_intensity": self.scores.emotional_intensity,
            "brevity_efficiency": self.scores.brevity_efficiency,
        })
        return inline

    def shorts_score_value(self) -> int:
        """Return the documented seven-factor Shorts score."""
        legacy = self.scores
        shorts_scores = self.shorts_evaluation_scores()
        if shorts_scores.weighted_score() == 0:
            return max(0, min(100, round(
                legacy.centrality * 0.30
                + legacy.standalone * 0.30
                + legacy.hook * 0.20
                + legacy.emotional_impact * 0.20
            )))
        return shorts_scores.weighted_score()

    def effective_shorts_score(self) -> int:
        """Blend the Shorts score with first-three-seconds stop metrics for ranking."""
        legacy = self.scores
        base = self.shorts_score_value()
        opening = self.opening_3s_score or legacy.hook
        scroll_stop = self.scroll_stop_score or legacy.hook
        if opening == 0:
            opening = legacy.hook
        if scroll_stop == 0:
            scroll_stop = legacy.hook
        return max(0, min(100, round(base * 0.65 + opening * 0.20 + scroll_stop * 0.15)))


class CandidateDiscovery(BaseModel):
    """A broad candidate window before final scoring and title generation."""

    start_segment_id: int = Field(gt=0)
    end_segment_id: int = Field(gt=0)
    core_theme: str = Field(min_length=1, max_length=200)
    raw_opening_sentence: str = Field(default="", max_length=300)
    emotional_triggers: List[str] = Field(default_factory=list, max_length=5)
    hook_type: str = Field(default="", max_length=80)
    expected_payoff: str = Field(default="", max_length=300)
    context_integrity: bool = True


class CandidateDiscoveryResult(BaseModel):
    candidates: List[CandidateDiscovery] = Field(min_length=8, max_length=15)


class CandidateTitleSet(BaseModel):
    start_segment_id: int = Field(gt=0)
    end_segment_id: int = Field(gt=0)
    titles: List[AnalysisTitle] = Field(min_length=3, max_length=3)


class CandidateTitleResult(BaseModel):
    candidates: List[CandidateTitleSet] = Field(min_length=4, max_length=4)


class SermonAnalysisResult(BaseModel):
    sermon_summary: str
    sermon_topics: List[str]
    candidates: List[AnalysisCandidate] = Field(min_length=4, max_length=15)
