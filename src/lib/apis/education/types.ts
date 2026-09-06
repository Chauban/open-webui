export type AIHelpType =
	| 'Understand Assignment'
	| 'Outline'
	| 'Examples'
	| 'Explain Concepts'
	| 'Revise Structure'
	| 'Polish'
	| 'Check Errors'
	| "Help Break Through Writer's Block"
	| 'Strengthen Reasoning'
	| 'Other';
export type WritingSourceType =
	| 'ai_inserted'
	| 'ai_pasted'
	| 'user_typed'
	| 'external_paste'
	| 'suspected_unmarked_import'
	| 'unknown';
export type WritingVersionTrigger = 'autosave' | 'manual' | 'submit' | 'submit_preflight';
export type EditorOperationType =
	| 'keyboard_input'
	| 'replace'
	| 'delete_text'
	| 'ai_insert_clicked'
	| 'paste_detected'
	| 'platform_ai_insert'
	| 'ai_reply_selection_copied'
	| 'ai_copy_button_clicked';

export type ProfileReviewStatus = 'unsubmitted' | 'pending' | 'reviewed' | 'returned';
export type ProfileCompletenessStatus = 'complete' | 'missing' | 'pending' | 'not_applicable';
export type ProfileMetricKey =
	| 'total_chars'
	| 'normalized_score'
	| 'process_index'
	| 'collaboration_index'
	| 'revision_depth'
	| 'active_writing_seconds'
	| 'end_loaded_ratio'
	| 'deadline_window_ratio'
	| 'ai_ratio'
	| 'digestion_ratio'
	| 'prompt_count'
	| 'reflection_quality';
export type ProfileInsightCode =
	| 'not_enough_data'
	| 'digestion_up'
	| 'digestion_low'
	| 'ai_share_changed'
	| 'round_improvement'
	| 'round_revision_thin'
	| 'help_type_shift_refining'
	| 'deadline_rush'
	| 'process_up'
	| 'reflection_thin'
	| 'ai_revision_productive'
	| 'ai_use_needs_review';
export type ProfileInsightActionCode =
	| 'complete_more_submissions'
	| 'keep_rewriting_ai_text'
	| 'rewrite_one_ai_section'
	| 'review_ai_use_pattern'
	| 'reuse_successful_revision'
	| 'revise_feedback_deeply'
	| 'continue_refining_own_writing'
	| 'start_next_assignment_earlier'
	| 'keep_current_process'
	| 'add_specific_reflection_evidence'
	| 'repeat_productive_ai_revision'
	| 'reduce_ai_share_and_deepen_revision';
export type ProfileFormulaMetric =
	| 'revised_chars / inserted_chars'
	| 'writing_span_seconds'
	| 'end_loaded_ratio'
	| 'digestion_ratio'
	| 'prompt_count'
	| 'reflection_quality';

export type RubricCriterion = { key: string; label: string; max_score: number };
export type ProfileClassroom = {
	id: string;
	name: string;
	teacher_id: string;
	invite_code: string;
	status: 'active' | 'archived';
	created_at: number;
	updated_at: number;
};
export type ProfileAssignment = {
	id: string;
	title: string;
	description?: string | null;
	due_at?: number | null;
	score_max: number;
	rubric_schema: { criteria: RubricCriterion[] };
	teacher_id: string;
	classroom_id: string | null;
	status: 'active' | 'archived';
	archived_at: number | null;
	created_at: number;
	updated_at: number;
};

export type ProfileDataCompleteness = {
	version_data: ProfileCompletenessStatus;
	editor_operations: ProfileCompletenessStatus;
	source_tracking: ProfileCompletenessStatus;
	scoring: ProfileCompletenessStatus;
};

export type StudentProfileTimelinePoint = {
	submission_id: string;
	assignment_id: string;
	assignment_title: string;
	round_no: number;
	is_current: boolean;
	submitted_at: number;
	data_completeness: ProfileDataCompleteness;
	total_chars: number;
	score: number | null;
	score_max: number;
	normalized_score: number | null;
	rubric: Record<string, number> | null;
	review_status: Exclude<ProfileReviewStatus, 'unsubmitted'>;
	inserted_chars: number | null;
	revised_chars: number | null;
	revision_depth: number | null;
	writing_span_seconds: number | null;
	active_writing_seconds: number | null;
	lead_time_seconds: number | null;
	end_loaded_ratio: number | null;
	deadline_window_ratio: number | null;
	process_index: number | null;
	typed_ratio: number | null;
	ai_ratio: number | null;
	unknown_ratio: number | null;
	prompt_count: number | null;
	digestion_ratio: number | null;
	reflection_char_count: number;
	reflection_quality: number;
	ai_help_types: AIHelpType[];
	collaboration_index: number | null;
	burst_count: number | null;
	suspected_unmarked_import_count: number | null;
	// 作业没开提交前试读时全为 null，表示「不适用」而不是「表现差」。
	challenge_status: 'completed' | 'skipped' | null;
	challenge_answer_ratio: number | null;
	challenge_unresolved_count: number | null;
	challenge_revised: boolean | null;
};

export type StudentProfileMetricTrend = {
	key: ProfileMetricKey;
	first: number;
	last: number;
	delta: number;
	direction: 'up' | 'down' | 'flat';
	sample_count: number;
	comparison_scope: 'cross_assignment';
};

export type StudentProfileInsightParams = {
	delta?: number | null;
	last?: number | null;
	digestion_ratio?: number | null;
	ai_ratio?: number | null;
	count?: number | null;
	best_delta?: number | null;
	revision_ratio?: number | null;
	ratio?: number | null;
	average_score?: number | null;
	normalized_score?: number | null;
	revision_depth?: number | null;
	reflection_quality?: number | null;
	score_delta?: number | null;
};

export type StudentProfileInsight = {
	code: ProfileInsightCode;
	tone: 'positive' | 'warning' | 'neutral';
	params: StudentProfileInsightParams;
	action_code: ProfileInsightActionCode | null;
	submission_id: string | null;
	severity: 'low' | 'medium' | 'high';
	confidence: number;
	sample_count: number;
	data_completeness: number;
	teaching_value: number;
	priority_score: number;
	evidence_codes: Array<
		| 'sample_size'
		| 'version_evidence'
		| 'editor_evidence'
		| 'source_evidence'
		| 'scoring_evidence'
		| 'reflection_evidence'
		| 'round_evidence'
	>;
};

export type StudentProfileRoundProgress = {
	assignment_id: string;
	assignment_title: string;
	from_round: number;
	to_round: number;
	char_delta: number;
	revision_ratio: number;
	score_delta: number | null;
	turnaround_seconds: number | null;
	comparison_scope: 'same_assignment_rounds';
};

export type StudentGrowthGoal = {
	id: string;
	student_id: string;
	classroom_id: string | null;
	assignment_id: string | null;
	goal_text: string;
	target_at: number | null;
	status: 'active' | 'completed' | 'archived';
	created_at: number;
	updated_at: number;
};

export type TeacherStudentNote = {
	id: string;
	teacher_id: string;
	classroom_id: string;
	student_id: string;
	content: string;
	observed_at: number;
	edited_at: number | null;
	created_at: number;
	updated_at: number;
};

export type ProfileFormulaTerm = {
	metric: ProfileFormulaMetric;
	weight: number;
	target: number | null;
	inverted: boolean;
};

export type StudentProfileIndexFormula = {
	process_index: {
		revision_depth: ProfileFormulaTerm;
		span_effort: ProfileFormulaTerm;
		pacing: ProfileFormulaTerm;
	};
	collaboration_index: {
		digestion: ProfileFormulaTerm;
		inquiry: ProfileFormulaTerm;
		reflection: ProfileFormulaTerm;
		no_ai_fallback_metric: 'reflection_quality';
	};
	reflection_quality: Record<
		'action' | 'location' | 'judgement' | 'next_step',
		{ target_chars: number; max_score: number }
	>;
};

export type StudentProfile = {
	metric_version: string;
	active_metric_version: string;
	insight_version: string;
	aggregate_materialized: boolean;
	aggregate_revision: number | null;
	available_metric_versions: string[];
	excluded_snapshot_count: number;
	student_id: string;
	student_name: string | null;
	student_email: string | null;
	classrooms: ProfileClassroom[];
	portfolio_summary: {
		assignment_count: number;
		submitted_count: number;
		unsubmitted_count: number;
		reviewed_count: number;
		returned_count: number;
		average_score_percent: number | null;
	};
	filtered_summary: {
		point_count: number;
		assignment_count: number;
		reviewed_point_count: number;
		average_score_percent: number | null;
	};
	filters_applied: boolean;
	timeline_pagination: { total: number; limit: number; offset: number };
	assignments: Array<{
		assignment: ProfileAssignment;
		submission_id: string | null;
		submitted_at: number | null;
		round_no: number | null;
		review_status: ProfileReviewStatus;
		score: number | null;
	}>;
	timeline: StudentProfileTimelinePoint[];
	cross_assignment_timeline: StudentProfileTimelinePoint[];
	round_progress: StudentProfileRoundProgress[];
	trends: StudentProfileMetricTrend[];
	ai_help_type_distribution: Partial<Record<AIHelpType, number>>;
	ai_help_type_shift: {
		early: { generative: number; refining: number; refining_ratio: number | null };
		recent: { generative: number; refining: number; refining_ratio: number | null };
		refining_ratio_delta: number | null;
	};
	reflection_quality: {
		count: number;
		average_score: number | null;
		average_chars: number | null;
	};
	index_formula: StudentProfileIndexFormula;
	insights: StudentProfileInsight[];
	data_completeness: {
		point_count: number;
		version_complete_count: number;
		version_missing_count: number;
		editor_operations_complete_count: number;
		editor_operations_missing_count: number;
		source_tracking_complete_count: number;
		source_tracking_missing_count: number;
		scoring_comparable_count: number;
		scoring_pending_count: number;
		scoring_not_applicable_count: number;
		scoring_missing_count: number;
		overall_ratio: number | null;
	};
	growth_goals: StudentGrowthGoal[];
};

export type TeacherStudentProfile = StudentProfile & {
	teacher_notes: TeacherStudentNote[];
};

export type StudentProfileFilters = {
	start_at?: number;
	end_at?: number;
	assignment_id?: string;
	round_no?: number;
	metric_version?: string;
	limit?: number;
	offset?: number;
};
