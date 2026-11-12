// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/stores', () => ({ page: readable({ url: new URL('http://localhost/me/writing') }) }));
vi.mock('$lib/stores/chatList', () => ({ refreshChatList: vi.fn() }));
vi.mock('$lib/stores', () => ({
	educationNotificationSummary: writable(null),
	folders: writable([]),
	selectedFolder: writable(null),
	user: writable({ education_role: 'student' }),
	mobile: writable(false),
	showSidebar: writable(true)
}));
vi.mock('$lib/apis/education', () => ({
	getWritingHome: vi.fn(),
	createPersonalWriting: vi.fn(),
	deletePersonalWriting: vi.fn(),
	joinClassroom: vi.fn()
}));
import { goto } from '$app/navigation';
import { getWritingHome } from '$lib/apis/education';
import { educationNotificationSummary, user } from '$lib/stores';
import WritingPage from './+page.svelte';

const sessionUser = (education_role: string) => ({
	permissions: {},
	id: 'test-user',
	email: 'test@example.com',
	name: 'Test',
	role: 'user',
	profile_image_url: '',
	education_role
});

afterEach(() => {
	cleanup();
	user.set(sessionUser('student'));
	educationNotificationSummary.set(null);
	vi.clearAllMocks();
});

test('reveals the reviewed assignment and updates its unread reason without marking the home read', async () => {
	vi.mocked(getWritingHome).mockResolvedValue({
		role: 'student',
		classrooms: [{ name: 'Class' }],
		assignment_items: [
			{
				assignment: { id: 'a', title: 'Reviewed essay' },
				status: 'submitted',
				review_status: 'reviewed'
			},
			{
				assignment: { id: 'b', title: 'Other essay' },
				status: 'submitted',
				review_status: 'reviewed'
			}
		]
	});
	educationNotificationSummary.set({
		total: 1,
		by_type: { review_completed: 1 },
		by_assignment: { a: { review_completed: 1 } }
	});
	render(WritingPage, { context: new Map([['i18n', readable({ t: (key: string) => key })]]) });
	expect(await screen.findByText('Reviewed essay')).toBeTruthy();
	expect(screen.getAllByText(/Unread review/)).toHaveLength(1);
	expect(screen.getByRole('button', { name: /Submitted 2/ }).getAttribute('aria-expanded')).toBe(
		'true'
	);
	await fireEvent.click(screen.getAllByRole('button', { name: 'View Review' })[0]);
	expect(goto).toHaveBeenCalledWith('/assignments/a/write');
	educationNotificationSummary.set({ total: 0, by_type: {}, by_assignment: {} });
	await waitFor(() => expect(screen.queryByText(/Unread review/)).toBeNull());
	vi.mocked(getWritingHome).mockResolvedValue({
		role: 'student',
		classrooms: [{ name: 'Class' }],
		assignment_items: [
			{
				assignment: { id: 'b', title: 'Returned essay' },
				status: 'submitted',
				review_status: 'returned',
				effective_due_at: 1
			}
		]
	});
	educationNotificationSummary.set({
		total: 1,
		by_type: { submission_returned: 1 },
		by_assignment: { b: { submission_returned: 1 } }
	});
	expect(await screen.findByText('Returned essay')).toBeTruthy();
	expect(screen.getByText(/Unread return notice/)).toBeTruthy();
	expect(
		screen
			.getByRole('button', { name: /Overdue · still open for submission 1/ })
			.getAttribute('aria-expanded')
	).toBe('true');
});

test('overdue work remains actionable and only late submissions get a late label', async () => {
	vi.mocked(getWritingHome).mockResolvedValue({
		role: 'student',
		classrooms: [{ name: 'Class' }],
		assignment_items: [
			{
				assignment: { id: 'late', title: 'Overdue essay' },
				status: 'not_started',
				effective_due_at: 1
			},
			{
				assignment: { id: 'submitted', title: 'Late essay' },
				status: 'submitted',
				review_status: 'pending',
				effective_due_at: 1,
				submission_timing: { effective_due_at: 1, is_late: true }
			},
			{
				assignment: { id: 'on-time', title: 'On-time essay' },
				status: 'submitted',
				review_status: 'pending',
				effective_due_at: 1,
				submission_timing: { effective_due_at: 1, is_late: false }
			}
		]
	});
	render(WritingPage, { context: new Map([['i18n', readable({ t: (key: string) => key })]]) });
	const title = await screen.findByText('Overdue essay');
	expect(title.closest('.rounded-3xl')?.className).toContain('bg-rose-50');
	expect(screen.getAllByText('Late submission')).toHaveLength(1);
	expect(screen.getByText('On-time essay').closest('.rounded-3xl')?.className).not.toContain(
		'bg-rose-50'
	);
	await fireEvent.click(screen.getByRole('button', { name: 'Start Writing' }));
	expect(goto).toHaveBeenCalledWith('/assignments/late/write');
});

test.each(['student', 'teacher'])(
	'personal writing entry follows the server capability for %s',
	async (role) => {
		user.set(sessionUser(role));
		const home = {
			role,
			personal_writing_enabled: true,
			classrooms: [],
			assignment_items: [],
			personal_items: [],
			recent_items: []
		};
		vi.mocked(getWritingHome).mockResolvedValue(home);
		render(WritingPage, { context: new Map([['i18n', readable({ t: (key: string) => key })]]) });
		if (role === 'student') {
			await fireEvent.click(await screen.findByRole('button', { name: 'Personal Writing' }));
		}
		expect(await screen.findByRole('button', { name: 'New Writing' })).toBeTruthy();
		vi.mocked(getWritingHome).mockResolvedValue({ ...home, personal_writing_enabled: false });
		educationNotificationSummary.set({ total: 0, by_type: {}, by_assignment: {} });
		await waitFor(() => expect(screen.queryByRole('button', { name: 'New Writing' })).toBeNull());
		expect(screen.queryByRole('button', { name: 'Personal Writing' })).toBeNull();
		if (role === 'student') {
			expect(screen.getByRole('button', { name: 'Assignment Writing' })).toBeTruthy();
		} else {
			expect(screen.getByText('Personal writing is disabled by your administrator.')).toBeTruthy();
		}
	}
);
