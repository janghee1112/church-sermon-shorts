export type ProjectStatus =
  | "uploading"
  | "uploaded"
  | "extracting_audio"
  | "transcribing"
  | "analyzing"
  | "completed"
  | "failed";

export interface Project {
  project_id: string;
  original_file_name: string;
  stored_file_name: string;
  duration_seconds: number;
  width: number;
  height: number;
  file_size: number;
  status: ProjectStatus;
  progress: number;
  error_message: string | null;
  error_stage: string | null;
  analysis_mode: "mock" | "real";
  created_at: string;
  updated_at: string;
}

export interface TranscriptWord {
  word: string;
  start_sec: number;
  end_sec: number;
}

export interface TranscriptSegment {
  id: number;
  start_sec: number;
  end_sec: number;
  text: string;
  segment_order: number;
  words: TranscriptWord[];
}

export interface Transcript {
  project_id: string;
  full_text: string;
  segments: TranscriptSegment[];
}

export interface CandidateTitle {
  title: string;
  title_type: string;
  title_order: number;
}

export interface Candidate {
  id: number;
  candidate_order: number;
  recommendation_type: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  transcript: string;
  main_topic: string;
  selection_reason: string;
  scores: {
    centrality: number;
    standalone: number;
    hook: number;
    emotional_impact: number;
    overall: number;
  };
  shorts_score?: number;
  opening_3s_score?: number;
  scroll_stop_score?: number;
  non_christian_clarity_score?: number;
  emotional_triggers?: string[];
  context_integrity?: boolean;
  core_theme?: string;
  titles: CandidateTitle[];
}

export interface CandidateResults {
  project_id: string;
  analysis_mode: "mock" | "real";
  sermon_summary: string;
  sermon_topics: string[];
  candidates: Candidate[];
  debug: AnalysisDebug | null;
}

export interface AnalysisDebug {
  analysis_mode: "mock" | "real";
  transcription_model: string | null;
  transcript_segment_count: number;
  transcript_char_count: number;
  first_segment: TranscriptBoundaryDebug | null;
  last_segment: TranscriptBoundaryDebug | null;
  candidates: Array<{
    candidate_order: number;
    start_segment_id: number | null;
    end_segment_id: number | null;
    segment_count: number;
    shorts_score?: number;
    hook_strength?: number;
    universal_relevance?: number;
    curiosity_gap?: number;
    payoff_strength?: number;
    standalone_clarity?: number;
    emotional_intensity?: number;
    brevity_efficiency?: number;
    opening_3s_score?: number;
    scroll_stop_score?: number;
    non_christian_clarity_score?: number;
    title_potential_score?: number;
    information_density_score?: number;
    context_integrity?: boolean;
    emotional_triggers?: string[];
    core_theme?: string | null;
  }>;
}

export interface TranscriptBoundaryDebug {
  segment_id: number;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface DraftCandidate {
  id: number;
  candidate_order: number;
  main_topic: string;
  recommended_start_segment_id: number;
  recommended_end_segment_id: number;
  recommended_start_sec: number;
  recommended_end_sec: number;
  title_placeholder: string;
}

export interface DraftRange {
  start_segment_id: number;
  end_segment_id: number;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
}

export interface DraftSubtitle {
  id: number;
  cue_order: number;
  start_sec: number;
  end_sec: number;
  relative_start_sec: number;
  relative_end_sec: number;
  original_text: string;
  edited_text: string;
  is_edited: boolean;
}

export interface TitleHighlightRange {
  start: number;
  end: number;
}

export interface TitleLayoutLine {
  text: string;
  source_start: number;
  source_end: number;
  width_px: number;
}

export interface TitleLayoutPreview {
  canvas_width: number;
  canvas_height: number;
  initial_font_size_px: number;
  font_size_px: number;
  line_height_px: number;
  total_height_px: number;
  auto_fit_applied: boolean;
  character_wrap_applied: boolean;
  area: { x: number; y: number; width: number; height: number };
  lines: TitleLayoutLine[];
  font_key: string;
  font_name: string;
  image_data_url: string;
}

export interface SubtitleLayoutPreview {
  canvas_width: number;
  canvas_height: number;
  font_size_px: number;
  line_height_px: number;
  lines: string[];
  font_key: string;
  font_name: string;
}

export interface ClipDraft {
  id: number;
  project_id: string;
  project_original_file_name: string;
  analysis_mode: "mock" | "real";
  candidate_id: number;
  candidate: DraftCandidate;
  range: DraftRange;
  custom_title: string;
  title_highlight_text: string;
  title_highlight_ranges: TitleHighlightRange[];
  zoom_scale: number;
  crop_position_x: number;
  crop_position_y: number;
  video_area_position_y: number;
  video_area_height: number;
  title_font_scale: number;
  title_position_y: number;
  subtitle_font_scale: number;
  subtitle_position_y: number;
  playback_rate: number;
  template_type: "sermon_letterbox_v1";
  status: "editing" | "ready";
  subtitles: DraftSubtitle[];
  updated_at: string;
}

export type DraftVisualSettings = Pick<
  ClipDraft,
  | "custom_title"
  | "title_highlight_ranges"
  | "zoom_scale"
  | "crop_position_x"
  | "crop_position_y"
  | "video_area_position_y"
  | "video_area_height"
  | "title_font_scale"
  | "title_position_y"
  | "subtitle_font_scale"
  | "subtitle_position_y"
  | "playback_rate"
  | "template_type"
>;

export type DraftEditableSettings = Pick<
  ClipDraft,
  | "custom_title"
  | "title_highlight_ranges"
  | "zoom_scale"
  | "crop_position_x"
  | "crop_position_y"
  | "video_area_position_y"
  | "video_area_height"
  | "title_font_scale"
  | "title_position_y"
  | "subtitle_font_scale"
  | "subtitle_position_y"
  | "playback_rate"
  | "template_type"
>;

export type RenderStatus = "queued" | "preparing" | "rendering" | "completed" | "failed" | "cancelled";

export interface RenderJob {
  id: number;
  project_id: string;
  draft_id: number;
  version: number;
  status: RenderStatus;
  progress: number;
  current_step: string;
  error_code: string | null;
  error_message: string | null;
  output_file_name: string | null;
  output_file_size: number | null;
  output_duration_sec: number | null;
  output_width: number | null;
  output_height: number | null;
  preview_url: string | null;
  download_url: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}
