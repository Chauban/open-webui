import { describe, expect, test } from 'vitest';

import { createLatestRequestGate } from './latest-request';

describe('latest request gate', () => {
	test('rejects a slower response after a newer filter request starts', () => {
		const gate = createLatestRequestGate();
		const first = gate.next();
		const second = gate.next();

		expect(gate.isLatest(first)).toBe(false);
		expect(gate.isLatest(second)).toBe(true);
	});
});
