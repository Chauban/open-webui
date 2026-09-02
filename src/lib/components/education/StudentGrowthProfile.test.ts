// @vitest-environment jsdom

import { render } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { describe, expect, test, vi } from 'vitest';

vi.mock('$lib/apis/education', () => ({
	createGrowthGoal: vi.fn(),
	createTeacherStudentNote: vi.fn(),
	deleteTeacherStudentNote: vi.fn(),
	updateGrowthGoal: vi.fn(),
	updateTeacherStudentNote: vi.fn()
}));

import type { StudentProfile, TeacherStudentProfile } from '$lib/apis/education/types';
import StudentGrowthProfile from './StudentGrowthProfile.svelte';

const context = new Map([
	[
		'i18n',
		readable({
			t: (key: string) => key
		})
	]
]);

const term = { metric: 'prompt_count' as const, weight: 1 / 3, target: null, inverted: false };
const profile: StudentProfile = {
	metric_version: '2026-09-01.3',
	insight_version: '2026-09-01.1',
	available_metric_versions: ['2026-09-01.3'],
	excluded_snapshot_count: 0,
	student_id: 'student-1',
	student_name: 'Student',
	student_email: 'student@example.com',
	classrooms: [{ id: 'class-1', name: 'Class 1' }],
	portfolio_summary: {
		assignment_count: 0,
		submitted_count: 0,
		unsubmitted_count: 0,
		reviewed_count: 0,
		returned_count: 0,
		average_score_percent: null
	},
	filtered_summary: {
		point_count: 0,
		assignment_count: 0,
		reviewed_point_count: 0,
		average_score_percent: null
	},
	filters_applied: false,
	timeline_pagination: { total: 0, limit: 200, offset: 0 },
	assignments: [],
	timeline: [],
	cross_assignment_timeline: [],
	round_progress: [],
	trends: [],
	ai_help_type_distribution: {},
	ai_help_type_shift: {
		early: { generative: 0, refining: 0, refining_ratio: null },
		recent: { generative: 0, refining: 0, refining_ratio: null },
		refining_ratio_delta: null
	},
	reflection_quality: { count: 0, average_score: null, average_chars: null },
	index_formula: {
		process_index: { revision_depth: term, span_effort: term, pacing: term },
		collaboration_index: {
			digestion: term,
			inquiry: term,
			reflection: term,
			no_ai_fallback_metric: 'reflection_quality'
		},
		reflection_quality: {
			action: { target_chars: 60, max_score: 30 },
			location: { target_chars: 20, max_score: 20 },
			judgement: { target_chars: 60, max_score: 30 },
			next_step: { target_chars: 40, max_score: 20 }
		}
	},
	insights: [
		{
			code: 'not_enough_data',
			tone: 'neutral',
			params: {},
			action_code: 'complete_more_submissions',
			submission_id: null,
			severity: 'low',
			confidence: 1,
			sample_count: 0,
			data_completeness: 0,
			teaching_value: 5,
			priority_score: 15,
			evidence_codes: ['sample_size']
		}
	],
	data_completeness: {
		point_count: 0,
		version_complete_count: 0,
		version_missing_count: 0,
		editor_operations_complete_count: 0,
		editor_operations_missing_count: 0,
		source_tracking_complete_count: 0,
		source_tracking_missing_count: 0,
		scoring_comparable_count: 0,
		scoring_pending_count: 0,
		scoring_not_applicable_count: 0,
		scoring_missing_count: 0,
		overall_ratio: null
	},
	growth_goals: []
};
const teacherProfile: TeacherStudentProfile = { ...profile, teacher_notes: [] };

describe('StudentGrowthProfile', () => {
	test('renders responsive filters, six sections, and evidence metadata', () => {
		const { container } = render(StudentGrowthProfile, {
			context,
			props: { profile, variant: 'student' }
		});

		const body = container.innerHTML;
		expect(body).toContain('sm:grid-cols-2');
		expect(body).toContain('Overview');
		expect(body).toContain('Writing Process');
		expect(body).toContain('Revision Between Rounds');
		expect(body).toContain('Samples');
		expect(body).toContain('Confidence');
		expect(body).toContain('Add goal');
	});

	test('shows private coaching notes only in the teacher variant', () => {
		const { container } = render(StudentGrowthProfile, {
			context,
			props: { profile: teacherProfile, variant: 'teacher' }
		});

		const body = container.innerHTML;
		expect(body).toContain('Teacher observations and coaching notes');
		expect(body).toContain('Add note');
	});
});
