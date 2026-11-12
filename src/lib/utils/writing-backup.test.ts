// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { createWritingBackup } from './writing-backup';
import { textDocument } from './writing-document';

afterEach(() => {
	localStorage.clear();
	vi.restoreAllMocks();
});
test('reload recovery is isolated by account, writing session, stage and open page', () => {
	const first = createWritingBackup('alice', 'a', 'draft');
	const second = createWritingBackup('alice', 'a', 'draft');
	first.write({ document: textDocument('first tab') });
	second.write({ document: textDocument('second tab') });
	expect(createWritingBackup('bob', 'a', 'draft').list()).toEqual([]);
	expect(createWritingBackup('alice', 'b', 'draft').list()).toEqual([]);
	expect(createWritingBackup('alice', 'a', 'baseline').list()).toEqual([]);
	first.clear();
	const reloaded = createWritingBackup('alice', 'a', 'draft');
	expect(reloaded.list()).toHaveLength(1);
	expect(reloaded.list()[0].data.document).toEqual(textDocument('second tab'));
});
test('discarding an observed backup cannot delete a newer edit from the original tab', () => {
	const original = createWritingBackup('alice', 'a', 'draft');
	const reopened = createWritingBackup('alice', 'a', 'draft');
	original.write({ document: textDocument('old') });
	const old = reopened.list()[0];
	original.write({ document: textDocument('new') });
	reopened.discard(old);
	expect(reopened.list()[0].data.document).toEqual(textDocument('new'));
});
test('quota failures surface rather than claiming the browser copy is safe', () => {
	vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
		throw new DOMException('Quota exceeded');
	});
	expect(() =>
		createWritingBackup('alice', 'a', 'draft').write({ document: textDocument('draft') })
	).toThrow();
});
