// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import Page from './+page.svelte';

const { list, visibility } = vi.hoisted(() => ({ list: vi.fn(), visibility: vi.fn() }));
vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		url: new URL('http://localhost/teacher/assignments')
	})
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/apis/education', () => ({
	getTeacherAssignments: list,
	getTeacherClassrooms: vi.fn(async () => []),
	setAssignmentVisibility: visibility
}));
vi.mock('$lib/apis/education/teaching', () => ({ teachingApi: vi.fn(async () => []) }));
vi.mock('$lib/utils/transitions', () => ({ flyAndScale: () => ({ duration: 0 }) }));
const context = new Map([['i18n', readable({ t: (key: string) => key, language: 'en' })]]);
const row = (id: string, hidden: boolean) => ({
	assignment: { id, title: id, hidden, due_at: 2000000000 },
	classroom: { id: 'class', name: 'Writing' },
	submission_count: 1,
	student_count: 2,
	pending_review_count: 1
});
beforeEach(() => {
	localStorage.token = 'test-token';
	vi.stubGlobal(
		'ResizeObserver',
		class {
			observe() {}
			unobserve() {}
			disconnect() {}
		}
	);
	list.mockResolvedValue([row('Visible essay', false), row('Hidden essay', true)]);
	visibility.mockReset();
	visibility.mockImplementation(async (_, id, hidden) => row(id, hidden).assignment);
});
afterEach(cleanup);

test('hides and restores assignments between separate groups', async () => {
	render(Page, { context });
	const visibleGroup = await screen.findByRole('region', { name: 'Assignments Shown to Students' });
	const hiddenGroup = screen.getByRole('region', { name: 'Hidden Assignments' });
	expect(within(visibleGroup).getByText('Visible essay')).toBeTruthy();
	expect(within(hiddenGroup).getByText('Hidden essay').className).toContain('text-gray-500');
	await fireEvent.click(within(visibleGroup).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Hide Assignment' }));
	await within(hiddenGroup).findByText('Visible essay');
	expect(visibility).toHaveBeenCalledWith(expect.anything(), 'Visible essay', true);
	expect(screen.queryByRole('region', { name: 'Assignments Shown to Students' })).toBeNull();
	const hiddenRow = within(hiddenGroup).getByText('Visible essay').closest('tr')!;
	await fireEvent.click(within(hiddenRow).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Show Assignment' }));
	expect(await screen.findByRole('region', { name: 'Assignments Shown to Students' })).toBeTruthy();
	expect(visibility).toHaveBeenLastCalledWith(expect.anything(), 'Visible essay', false);
});

test('failed visibility changes leave the assignment in its original group', async () => {
	visibility.mockRejectedValue(new Error('Unable to save'));
	render(Page, { context });
	const group = await screen.findByRole('region', { name: 'Assignments Shown to Students' });
	await fireEvent.click(within(group).getByRole('button', { name: 'More' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Hide Assignment' }));
	expect(within(group).getByText('Visible essay')).toBeTruthy();
	expect(
		within(screen.getByRole('region', { name: 'Hidden Assignments' })).queryByText('Visible essay')
	).toBeNull();
});
