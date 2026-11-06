// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get, readable, writable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('$app/stores', () => ({
	page: readable({ url: new URL('https://example.test/courseware') })
}));
vi.mock('$lib/stores', () => ({
	config: writable({ features: { enable_courseware: true } }),
	user: writable({ role: 'user', education_role: 'student' }),
	mobile: writable(false),
	showSidebar: writable(true)
}));

import { config, mobile, showSidebar, user } from '$lib/stores';
import CoursewareLink from './CoursewareLink.svelte';

const context = new Map([['i18n', readable({ t: (key: string) => key })]]);
afterEach(cleanup);

test.each(['student', 'teacher', 'admin'])(
	'visible to active %s accounts even without pinned menu settings',
	(role) => {
		config.set({ features: { enable_courseware: true } } as any);
		user.set({ role: role === 'admin' ? 'admin' : 'user', education_role: role } as any);
		render(CoursewareLink, { context });
		expect(screen.getByRole('link', { name: 'Courseware' }).getAttribute('href')).toBe(
			'/courseware'
		);
	}
);

test('disabled instance does not expose the entry', () => {
	config.set({ features: { enable_courseware: false } } as any);
	render(CoursewareLink, { context });
	expect(screen.queryByRole('link', { name: 'Courseware' })).toBeNull();
});

test('collapsed entry remains accessible and closes the mobile sidebar', async () => {
	config.set({ features: { enable_courseware: true } } as any);
	user.set({ role: 'user' } as any);
	mobile.set(true);
	showSidebar.set(true);
	render(CoursewareLink, { props: { collapsed: true }, context });
	const link = screen.getByRole('link', { name: 'Courseware' });
	link.addEventListener('click', (event) => event.preventDefault());
	await fireEvent.click(link);
	expect(get(showSidebar)).toBe(false);
});
