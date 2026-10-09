// @vitest-environment jsdom

import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return { config: writable({ features: { enable_education_return: false } }) };
});

vi.mock('$lib/apis/education', () => ({
	createGrowthGoal: vi.fn(),
	createTeacherStudentNote: vi.fn(),
	deleteTeacherStudentNote: vi.fn(),
	updateGrowthGoal: vi.fn(),
	updateTeacherStudentNote: vi.fn()
}));

import type { StudentProfile, TeacherStudentProfile } from '$lib/apis/education/types';
import { config } from '$lib/stores';
import StudentGrowthProfile from './StudentGrowthProfile.svelte';

const context = new Map([
	[
		'i18n',
		readable({
			t: (key: string) => key
		})
	]
]);

const term = { metric: 'prompt_quality' as const, weight: 1 / 2, target: null, inverted: false };
const indexFormula: TeacherStudentProfile['index_formula'] = {
	process_index: { revision_depth: term, span_effort: term, pacing: term },
	collaboration_index: {
		inquiry: term,
		reflection: term,
		no_conversation_fallback_metric: 'reflection_quality'
	}
};
const profile: StudentProfile = {
	metric_version: '2026-09-03.1',
	active_metric_version: '2026-09-03.1',
	aggregate_materialized: true,
	aggregate_revision: 1,
	insight_version: '2026-09-01.1',
	available_metric_versions: ['2026-09-03.1'],
	excluded_snapshot_count: 0,
	student_id: 'student-1',
	student_name: 'Student',
	student_email: 'student@example.com',
	classrooms: [
		{
			id: 'class-1',
			name: 'Class 1',
			teacher_id: 'teacher-1',
			invite_code: 'ABC123',
			status: 'active',
			created_at: 0,
			updated_at: 0
		}
	],
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
	reflection_quality: { count: 0, average_score: null },
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
const teacherProfile: TeacherStudentProfile = {
	...profile,
	index_formula: indexFormula,
	teacher_notes: []
};

const setReturnEnabled = (enabled: boolean) => {
	config.update((current) => ({
		...current!,
		features: { ...current!.features, enable_education_return: enabled }
	}));
};

beforeEach(() => setReturnEnabled(false));
afterEach(cleanup);

describe('StudentGrowthProfile', () => {
	test('renders responsive filters and hides evidence metadata from students', () => {
		const { container } = render(StudentGrowthProfile, {
			context,
			props: { profile, variant: 'student' }
		});

		const body = container.innerHTML;
		expect(body).toContain('sm:grid-cols-2');
		expect(body).toContain('Overview');
		expect(body).toContain('Writing Process');
		expect(body).toContain('Add goal');
		// 置信度、样本数、指标/洞察版本号是给教师核对口径的,学生端不出现
		expect(body).not.toContain('Samples');
		expect(body).not.toContain('Confidence');
		expect(body).not.toContain('Latest data completeness');
	});

	describe.each(['student', 'teacher'] as const)('%s round revision section', (variant) => {
		const variantProfile = variant === 'teacher' ? teacherProfile : profile;

		test('hides the section when returns are disabled and there are no resubmissions', () => {
			const { queryByRole } = render(StudentGrowthProfile, {
				context,
				props: { profile: variantProfile, variant }
			});

			expect(queryByRole('button', { name: 'Revision Between Rounds' })).toBeNull();
		});

		test('shows the section when returns are enabled even without resubmissions', async () => {
			setReturnEnabled(true);
			const { getByRole, getByText } = render(StudentGrowthProfile, {
				context,
				props: { profile: variantProfile, variant }
			});

			await fireEvent.click(getByRole('button', { name: 'Revision Between Rounds' }));
			expect(getByText('No resubmissions yet.')).toBeTruthy();
		});

		test('keeps existing resubmissions accessible when returns are disabled', async () => {
			const { getByRole, getByText, queryByText } = render(StudentGrowthProfile, {
				context,
				props: {
					profile: {
						...variantProfile,
						round_progress: [
							{
								assignment_id: 'assignment-1',
								assignment_title: 'Revised essay',
								from_round: 1,
								to_round: 2,
								char_delta: 120,
								revision_ratio: 25,
								score_delta: 5,
								turnaround_seconds: 3600,
								comparison_scope: 'same_assignment_rounds'
							}
						]
					},
					variant
				}
			});

			await fireEvent.click(getByRole('button', { name: 'Revision Between Rounds' }));
			expect(getByText('Revised essay')).toBeTruthy();
			expect(queryByText('No resubmissions yet.')).toBeNull();
		});
	});

	test('shows evidence metadata and data completeness only in the teacher variant', () => {
		const { container } = render(StudentGrowthProfile, {
			context,
			props: { profile: teacherProfile, variant: 'teacher' }
		});

		const body = container.innerHTML;
		expect(body).toContain('Samples');
		expect(body).toContain('Confidence');
		expect(body).toContain('Latest data completeness');
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
