import { expect, test, vi } from 'vitest';
import { createWritingHomeRequests, writingHomeIdentity } from './home';

function deferred() {
	let resolve!: (value: any) => void;
	const promise = new Promise((r) => (resolve = r));
	return { promise, resolve };
}

test('shares an in-flight read and folds events during it into one fresh read', async () => {
	const first = deferred();
	const second = deferred();
	const fetch = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
	const requests = createWritingHomeRequests(fetch);
	const a = requests.load('student-a', 'token-a');
	expect(requests.load('student-a', 'token-a')).toBe(a);
	requests.invalidate();
	requests.invalidate();
	first.resolve({ title: 'old visibility' });
	await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
	second.resolve({ title: 'fresh visibility' });
	expect(await a).toEqual({ title: 'fresh visibility' });
});

test('late responses cannot cross identities and no resolved content is reused', async () => {
	const a = deferred();
	const fetch = vi.fn().mockReturnValueOnce(a.promise).mockResolvedValue({ title: 'B' });
	const requests = createWritingHomeRequests(fetch);
	const old = requests.load('A', 'token-a');
	expect(await requests.load('B', 'token-b')).toEqual({ title: 'B' });
	a.resolve({ title: 'A' });
	expect(await old).toBeNull();
	await requests.load('B', 'token-b');
	expect(fetch).toHaveBeenCalledTimes(3);
});

test('layout reuse expires, is scoped to class and clears on invalidation', () => {
	const requests = createWritingHomeRequests(vi.fn());
	requests.remember('account:class-a', { showDone: false });
	expect(requests.layout('account:class-b')).toBeNull();
	expect(requests.layout('account:class-a')).toEqual({ showDone: false });
	vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 15001);
	expect(requests.layout('account:class-a')).toBeNull();
	vi.restoreAllMocks();
	requests.remember('account:class-a', {});
	requests.invalidate();
	expect(requests.layout('account:class-a')).toBeNull();
	expect(writingHomeIdentity({ id: 'a', education_role: 'student' }, 'login-1')).not.toBe(
		writingHomeIdentity({ id: 'a', education_role: 'student' }, 'login-2')
	);
});
