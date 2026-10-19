import { describe, expect, it } from 'vitest';

import { thinkingSupportOf, thinksAlways } from './thinking-support';

const MODELS = [
	{ id: 'kimi-k2.6', thinking_support: { can_turn_off: true, graded: false } },
	{ id: 'kimi-k3', thinking_support: { can_turn_off: true, graded: true } },
	{ id: 'local-llama' }
];

describe('thinking support', () => {
	it('reads the support the backend attached to the model', () => {
		expect(thinkingSupportOf(MODELS, 'kimi-k2.6')).toEqual({ can_turn_off: true, graded: false });
		expect(thinkingSupportOf(MODELS, 'local-llama')).toBeNull();
		expect(thinkingSupportOf(MODELS, null)).toBeNull();
	});

	it('marks only models that cannot turn thinking off as always thinking', () => {
		expect(thinksAlways({ can_turn_off: false, graded: true })).toBe(true);
		expect(thinksAlways({ can_turn_off: true, graded: false })).toBe(false);
		expect(thinksAlways(null)).toBe(false);
	});
});
