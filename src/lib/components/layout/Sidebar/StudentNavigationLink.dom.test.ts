// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$lib/stores', () => ({
	settings: writable({ keyboardShortcuts: false }),
	user: readable({ id: 'student' })
}));
vi.mock('$lib/apis/education/home', () => ({
	writingHomeIdentity: () => 'student-scope',
	writingHomeRequests: { load: vi.fn().mockResolvedValue({}) }
}));
import { writingHomeRequests } from '$lib/apis/education/home';
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
import { goto } from '$app/navigation';
import StudentNavigationLink from './StudentNavigationLink.svelte';
import FreeChatNotice from '$lib/components/chat/FreeChatNotice.svelte';
import zh from '$lib/i18n/locales/zh-CN/translation.json';

const context = new Map([['i18n', readable({ t: (key: string) => zh[key] ?? key })]]);
afterEach(() => {
	cleanup();
	localStorage.clear();
	vi.clearAllMocks();
});

test.each([false, true])(
	'assignment and chat destinations stay distinct when collapsed=%s',
	async (collapsed) => {
		localStorage.token = 'test-token';
		const onNavigate = vi.fn();
		render(StudentNavigationLink, {
			context,
			props: { collapsed, active: true, unread: 2, onNavigate }
		});
		const assignments = screen.getByRole('link', { name: '我的作业' });
		expect(assignments.getAttribute('href')).toBe('/me/writing');
		expect(assignments.getAttribute('aria-current')).toBe('page');
		expect(screen.getByText('2')).toBeTruthy();
		const assignmentClick = new MouseEvent('click', { bubbles: true, cancelable: true });
		await fireEvent(assignments, assignmentClick);
		expect(assignmentClick.defaultPrevented).toBe(true);
		expect(goto).toHaveBeenLastCalledWith('/me/writing');
		expect(writingHomeRequests.load).toHaveBeenCalledWith('student-scope', 'test-token');
		expect(vi.mocked(writingHomeRequests.load).mock.invocationCallOrder[0]).toBeLessThan(
			vi.mocked(goto).mock.invocationCallOrder[0]
		);
		expect(onNavigate).toHaveBeenCalledOnce();

		render(StudentNavigationLink, { context, props: { kind: 'free-chat', collapsed } });
		const freeChat = screen.getByRole('link', { name: '自由交流' });
		expect(freeChat.getAttribute('href')).toBe('/');
		const chatClick = new MouseEvent('click', { bubbles: true, cancelable: true });
		await fireEvent(freeChat, chatClick);
		expect(chatClick.defaultPrevented).toBe(true);
		expect(goto).toHaveBeenLastCalledWith('/');
	}
);

test.each(['ctrlKey', 'metaKey', 'shiftKey', 'altKey'])(
	'%s clicks retain native browser navigation without resetting the current conversation',
	async (modifier) => {
		const onNavigate = vi.fn();
		render(StudentNavigationLink, { context, props: { kind: 'free-chat', onNavigate } });
		const link = screen.getByRole('link', { name: '自由交流' });
		let preventedByComponent: boolean | undefined;
		link.addEventListener('click', (event) => {
			preventedByComponent = event.defaultPrevented;
			// Stop jsdom's unsupported native navigation after observing the component.
			event.preventDefault();
		});
		await fireEvent.click(link, { [modifier]: true });
		expect(preventedByComponent).toBe(false);
		expect(onNavigate).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	}
);

test('the persistent notice links to assignments and has no dismiss action', () => {
	const { container } = render(FreeChatNotice, { context });
	expect(container.textContent).toContain('此处对话不计入课程作业。完成作业请前往');
	expect(screen.getByRole('link', { name: '我的作业' }).getAttribute('href')).toBe('/me/writing');
	expect(screen.queryByRole('button')).toBeNull();
});
