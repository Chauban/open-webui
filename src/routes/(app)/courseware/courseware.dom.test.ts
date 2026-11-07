// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/constants', () => ({ WEBUI_API_BASE_URL: '/api/v1' }));
vi.mock('$lib/stores', () => ({
	config: writable({ features: { enable_courseware: true } }),
	showSidebar: writable(true)
}));

import { goto } from '$app/navigation';
import CoursewarePage from './+page.svelte';

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	vi.clearAllMocks();
});

test('checks cookie authentication before embedding and keeps a return link', async () => {
	const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
	vi.stubGlobal('fetch', fetchMock);
	render(CoursewarePage, { context });
	const frame = await screen.findByTitle('Courseware');
	expect(frame.getAttribute('src')).toBe('/api/v1/courseware/content/index.html');
	expect(fetchMock).toHaveBeenCalledWith('/api/v1/courseware/', {
		credentials: 'include',
		cache: 'no-store'
	});
	expect(screen.getByRole('link', { name: 'Back to Right Write' }).getAttribute('href')).toBe('/');
});

test('expired login returns through authentication without exposing an iframe', async () => {
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }));
	render(CoursewarePage, { context });
	await waitFor(() => expect(goto).toHaveBeenCalledWith('/auth?redirect=%2Fcourseware'));
	expect(screen.queryByTitle('Courseware')).toBeNull();
});

test('missing lesson shows a readable state while preserving the return link', async () => {
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
	render(CoursewarePage, { context });
	expect(await screen.findByText('Courseware is not available')).toBeTruthy();
	expect(screen.queryByTitle('Courseware')).toBeNull();
	expect(screen.getByRole('link', { name: 'Back to Right Write' })).toBeTruthy();
});
