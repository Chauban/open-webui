// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import StudentGrowthProfile from './StudentGrowthProfile.svelte';
import {
	createGrowthGoal,
	deleteTeacherStudentNote,
	updateTeacherStudentNote
} from '$lib/apis/education';

vi.mock('$lib/apis/education', () => ({
	createGrowthGoal: vi.fn(),
	createTeacherStudentNote: vi.fn(),
	deleteTeacherStudentNote: vi.fn(),
	updateGrowthGoal: vi.fn(),
	updateTeacherStudentNote: vi.fn()
}));

const context = new Map([
	[
		'i18n',
		readable({
			t: (key: string) => key
		})
	]
]);

const makeProfile = (teacher = false): any => ({
	metric_version: '2026-09-01.3',
	insight_version: '2026-09-01.1',
	available_metric_versions: ['2026-09-01.3'],
	excluded_snapshot_count: 0,
	student_id: 'student-1',
	student_name: 'Student',
	student_email: null,
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
		process_index: {
			revision_depth: { metric: 'revised_chars / inserted_chars', weight: 1 / 3 },
			span_effort: { metric: 'writing_span_seconds', weight: 1 / 3 },
			pacing: { metric: 'end_loaded_ratio', weight: 1 / 3 }
		},
		collaboration_index: {
			digestion: { metric: 'digestion_ratio', weight: 1 / 3 },
			inquiry: { metric: 'prompt_count', weight: 1 / 3 },
			reflection: { metric: 'reflection_quality', weight: 1 / 3 },
			no_ai_fallback_metric: 'reflection_quality'
		},
		reflection_quality: {
			action: { target_chars: 60, max_score: 30 },
			location: { target_chars: 20, max_score: 20 },
			judgement: { target_chars: 60, max_score: 30 },
			next_step: { target_chars: 40, max_score: 20 }
		}
	},
	insights: [],
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
	growth_goals: [],
	...(teacher
		? {
				teacher_notes: [
					{
						id: 'note-1',
						teacher_id: 'teacher-1',
						classroom_id: 'class-1',
						student_id: 'student-1',
						content: 'Original observation',
						observed_at: 1,
						edited_at: null,
						created_at: 1,
						updated_at: 1
					}
				]
			}
		: {})
});

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.setItem('token', 'test-token');
});

describe('StudentGrowthProfile browser interactions', () => {
	test('adds a student growth goal through the rendered form', async () => {
		vi.mocked(createGrowthGoal).mockResolvedValue({
			id: 'goal-1',
			student_id: 'student-1',
			classroom_id: 'class-1',
			assignment_id: null,
			goal_text: 'Create the outline two days early',
			target_at: null,
			status: 'active',
			created_at: 1,
			updated_at: 1
		});
		render(StudentGrowthProfile, {
			context,
			props: { profile: makeProfile(), variant: 'student' }
		});

		await fireEvent.input(
			screen.getByPlaceholderText('Example: create an outline two days before the next deadline'),
			{ target: { value: 'Create the outline two days early' } }
		);
		await fireEvent.click(screen.getByRole('button', { name: 'Add goal' }));

		await waitFor(() => expect(createGrowthGoal).toHaveBeenCalledTimes(1));
		expect(await screen.findByText('Create the outline two days early')).toBeTruthy();
	});

	test('edits and confirms deletion of a private teacher note', async () => {
		vi.mocked(updateTeacherStudentNote).mockResolvedValue({
			...makeProfile(true).teacher_notes[0],
			content: 'Updated observation',
			edited_at: 2,
			updated_at: 2
		});
		vi.mocked(deleteTeacherStudentNote).mockResolvedValue({ ok: true });
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		render(StudentGrowthProfile, {
			context,
			props: { profile: makeProfile(true), variant: 'teacher' }
		});

		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		const editor = screen.getByDisplayValue('Original observation');
		await fireEvent.input(editor, { target: { value: 'Updated observation' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(updateTeacherStudentNote).toHaveBeenCalledTimes(1));

		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
		expect(window.confirm).toHaveBeenCalledTimes(1);
		await waitFor(() => expect(deleteTeacherStudentNote).toHaveBeenCalledTimes(1));
	});
});
