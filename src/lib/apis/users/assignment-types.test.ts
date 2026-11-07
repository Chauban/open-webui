import { afterEach, expect, test, vi } from 'vitest';
import { updateUserById } from './index';

afterEach(() => vi.unstubAllGlobals());
test('admin user update sends an explicit empty teacher authorization', async () => {
	const fetch = vi
		.fn()
		.mockResolvedValue(
			new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
		);
	vi.stubGlobal('fetch', fetch);
	await updateUserById('test-token', 'teacher-test', {
		role: 'user',
		profile_image_url: '/user.png',
		email: 'test@example.invalid',
		name: 'Test',
		password: '',
		education_role: 'teacher',
		assignment_types: { allowed_task_modes: [], default_task_mode: null }
	});
	expect(JSON.parse(fetch.mock.calls[0][1].body).assignment_types).toEqual({
		allowed_task_modes: [],
		default_task_mode: null
	});
});
