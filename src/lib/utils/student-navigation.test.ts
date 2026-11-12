import { describe, expect, it } from 'vitest';
import { getHomeHref, getSignInRedirect } from './student-navigation';

describe('student landing navigation', () => {
	it('defaults students to assignments after sign-in, including a root redirect', () => {
		const student = { education_role: 'student' };
		expect(getHomeHref(student)).toBe('/me/writing');
		for (const redirect of [undefined, null, '', '/']) {
			expect(getSignInRedirect(student, redirect)).toBe('/me/writing');
		}
	});
	it('preserves explicit assignment, conversation and invitation destinations', () => {
		for (const path of [
			'/assignments/task/write?chat=chat-id',
			'/c/chat-id',
			'/join?code=CLASS',
			'/?models=model&q=hello'
		]) {
			expect(getSignInRedirect({ education_role: 'student' }, path)).toBe(path);
		}
	});
	it('retains the ordinary home for other roles', () => {
		for (const user of [
			undefined,
			null,
			{},
			{ education_role: 'teacher' },
			{ education_role: 'admin' }
		]) {
			expect(getHomeHref(user)).toBe('/');
			expect(getSignInRedirect(user)).toBe('/');
		}
	});
});
