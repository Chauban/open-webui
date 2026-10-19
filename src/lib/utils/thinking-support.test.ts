import { describe, expect, it } from 'vitest';

import { thinkingSupportNote, thinkingSupportOf } from './thinking-support';

const t = ((key: string) => key) as never;

const MODELS = [
	{ id: 'kimi-k2.6', thinking_support: { graded: false } },
	{ id: 'kimi-k3', thinking_support: { graded: true } },
	{ id: 'local-llama' }
];

describe('thinking support', () => {
	it('reads the support the backend attached to the model', () => {
		expect(thinkingSupportOf(MODELS, 'kimi-k2.6')).toEqual({ graded: false });
		expect(thinkingSupportOf(MODELS, 'local-llama')).toBeNull();
		expect(thinkingSupportOf(MODELS, null)).toBeNull();
	});

	it('notes on/off-only models and stays quiet otherwise', () => {
		expect(thinkingSupportNote({ graded: false }, t)).toBe(
			'This model only turns thinking on or off: Low, Medium and High all just turn it on.'
		);
		expect(thinkingSupportNote({ graded: true }, t)).toBeNull();
		expect(thinkingSupportNote(null, t)).toBeNull();
	});
});
