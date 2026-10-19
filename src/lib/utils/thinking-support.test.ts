import { describe, expect, it } from 'vitest';

import { thinkingSupportNote, thinkingSupportOf, thinksAlways } from './thinking-support';

const t = ((key: string) => key) as never;

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

	it('notes models that cannot turn thinking off or have no levels, and stays quiet otherwise', () => {
		expect(thinkingSupportNote({ can_turn_off: true, graded: false }, t)).toBe(
			'This model only turns thinking on or off: Low, Medium and High all just turn it on.'
		);
		expect(thinkingSupportNote({ can_turn_off: false, graded: true }, t)).toBe(
			'This model cannot turn thinking off: Off uses the lowest level instead.'
		);
		expect(thinkingSupportNote({ can_turn_off: false, graded: false }, t)).toBe(
			'This model always thinks and has no levels: every thinking setting leaves it at the model default.'
		);
		expect(thinkingSupportNote({ can_turn_off: true, graded: true }, t)).toBeNull();
		expect(thinkingSupportNote(null, t)).toBeNull();
	});

	it('marks only models that cannot turn thinking off as always thinking', () => {
		expect(thinksAlways({ can_turn_off: false, graded: true })).toBe(true);
		expect(thinksAlways({ can_turn_off: true, graded: false })).toBe(false);
		expect(thinksAlways(null)).toBe(false);
	});
});
