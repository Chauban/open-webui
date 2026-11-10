// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { goto } from '$app/navigation';
import Page from './+page.svelte';

vi.mock('$app/stores', async () => ({
	page: (await import('svelte/store')).readable({
		url: new URL('http://localhost/teacher/classrooms')
	})
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/apis/education', () => ({
	createClassroom: vi.fn(),
	getTeacherClassrooms: vi.fn(async () => [
		{
			classroom: { id: 'class-1', name: 'Writing class', invite_code: 'ABCD1234' },
			student_count: 1,
			assignment_count: 2
		}
	])
}));
vi.mock('$lib/utils/transitions', () => ({ flyAndScale: () => ({ duration: 0 }) }));
const context = new Map([['i18n', readable({ t: (key: string) => key, language: 'en' })]]);

beforeEach(() => {
	vi.mocked(goto).mockClear();
	localStorage.token = 'test-token';
	Object.defineProperty(navigator, 'clipboard', {
		configurable: true,
		value: { writeText: vi.fn(async () => {}) }
	});
});
afterEach(cleanup);

test('classroom link reaches the router; row space and invite copy keep their own actions', async () => {
	render(Page, { context });
	const link = await screen.findByRole('link', { name: 'Writing class' });
	const row = link.closest('tr')!;
	const routerClick = vi.fn((event: MouseEvent) => {
		expect(event.defaultPrevented).toBe(false);
		event.preventDefault();
	});
	document.addEventListener('click', routerClick);
	try {
		await fireEvent.click(link);
		expect(routerClick).toHaveBeenCalledTimes(1);
		expect(goto).not.toHaveBeenCalled();
	} finally {
		document.removeEventListener('click', routerClick);
	}
	await fireEvent.click(row.cells[0]);
	expect(goto).toHaveBeenCalledTimes(1);
	expect(goto).toHaveBeenCalledWith('/teacher/classrooms/class-1');
	vi.mocked(goto).mockClear();
	await fireEvent.click(within(row).getByRole('button', { name: 'ABCD1234' }));
	expect(navigator.clipboard.writeText).toHaveBeenCalledWith('ABCD1234');
	expect(goto).not.toHaveBeenCalled();
});
