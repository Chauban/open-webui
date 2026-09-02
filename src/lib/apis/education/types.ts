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

export type RubricCriterion = { key: string; label: string; max_score: number };
export type ProfileAssignment = {
	id: string;
	title: string;
	description?: string | null;
	due_at?: number | null;
	score_max: number;
	rubric_schema: { criteria: RubricCriterion[] };
	[key: string]: unknown;
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
	code: string;
	tone: 'positive' | 'warning' | 'neutral';
	params: StudentProfileInsightParams;
	action_code: string | null;
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
	metric: string;
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
	insight_version: string;
	available_metric_versions: string[];
	excluded_snapshot_count: number;
	student_id: string;
	student_name: string | null;
	student_email: string | null;
	classrooms: Array<{ id: string; name: string } & Record<string, unknown>>;
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
