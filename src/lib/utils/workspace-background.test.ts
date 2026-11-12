import { expect, test, vi } from 'vitest';
import { workspaceBackground } from './workspace-background';

test('optional jobs are deduplicated, bounded and skipped after their consumer leaves', async () => {
	let finish;
	const first = vi.fn(() => new Promise<void>((r) => (finish = r)));
	const a = workspaceBackground('first', first, () => true);
	expect(workspaceBackground('first', first, () => true)).toBe(a);
	let mounted = true;
	const skipped = vi.fn(async () => {});
	const b = workspaceBackground('left', skipped, () => mounted);
	await vi.waitFor(() => expect(first).toHaveBeenCalledOnce());
	expect(skipped).not.toHaveBeenCalled();
	mounted = false;
	const reopened = vi.fn(async () => 'new page');
	const c = workspaceBackground('left', reopened, () => true);
	finish();
	await Promise.all([a, b]);
	expect(skipped).not.toHaveBeenCalled();
	expect(await c).toBe('new page');
	const last = vi.fn(async () => 42);
	expect(await workspaceBackground('last', last, () => true)).toBe(42);
});
