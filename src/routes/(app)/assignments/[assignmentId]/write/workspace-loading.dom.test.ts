// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

const api = vi.hoisted(() => ({
	getAssignmentWorkspace: vi.fn(),
	markEducationNotificationsRead: vi.fn(),
	getEducationNotificationSummary: vi.fn()
}));
vi.mock('$lib/apis/education', () => api);
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { assignmentId: 'assignment-1' } }) };
});
vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return { educationNotificationSummary: writable(null) };
});
vi.mock(
	'$lib/components/education/WritingWorkspaceShell.svelte',
	() => import('$lib/components/education/test-fixtures/WorkspaceLoader.svelte')
);
import Page from './+page.svelte';
import { educationNotificationSummary } from '$lib/stores';

afterEach(() => {
	cleanup();
	localStorage.clear();
	vi.resetAllMocks();
});

test('通知已读请求尚未完成时就返回作业，完成后仍刷新通知角标', async () => {
	localStorage.token = 'test-token';
	let finishNotifications!: () => void;
	api.getAssignmentWorkspace.mockResolvedValue({ assignment: { title: '原有作业' } });
	api.markEducationNotificationsRead.mockReturnValue(
		new Promise<void>((resolve) => (finishNotifications = resolve))
	);
	api.getEducationNotificationSummary.mockResolvedValue({ unread_count: 0 });
	render(Page);
	expect(await screen.findByRole('heading', { name: '原有作业' })).toBeTruthy();
	expect(api.markEducationNotificationsRead).toHaveBeenCalledWith(
		'test-token',
		expect.objectContaining({ assignment_id: 'assignment-1' })
	);
	expect(api.getEducationNotificationSummary).not.toHaveBeenCalled();
	finishNotifications();
	await waitFor(() => expect(get(educationNotificationSummary)).toEqual({ unread_count: 0 }));
});

test.each(['logout', 'unmount'])('迟到通知摘要不更新已离开的身份或页面（%s）', async (action) => {
	localStorage.token = 'account-a';
	let finishSummary;
	api.getAssignmentWorkspace.mockResolvedValue({ assignment: { title: 'A 作业' } });
	api.markEducationNotificationsRead.mockResolvedValue({});
	api.getEducationNotificationSummary.mockReturnValue(new Promise((r) => (finishSummary = r)));
	educationNotificationSummary.set(null);
	const view = render(Page);
	await screen.findByRole('heading', { name: 'A 作业' });
	await waitFor(() => expect(api.getEducationNotificationSummary).toHaveBeenCalledOnce());
	if (action === 'logout') localStorage.token = 'account-b';
	else view.unmount();
	finishSummary({ unread_count: 99 });
	await new Promise((r) => setTimeout(r, 0));
	expect(get(educationNotificationSummary)).toBeNull();
});
