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
import { educationNotificationSummary } from '$lib/stores';
import WritingPage from './+page.svelte';

afterEach(() => {
	cleanup();
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
		screen.getByRole('button', { name: /Past due, not submitted 1/ }).getAttribute('aria-expanded')
	).toBe('true');
});
