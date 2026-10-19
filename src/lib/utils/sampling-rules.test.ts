import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/apis/openai', () => ({ getSamplingRules: vi.fn() }));

import { samplingNote, type SamplingRules } from './sampling-rules';

const t = ((key: string, options?: Record<string, unknown>) =>
	Object.entries(options ?? {}).reduce(
		(text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
		key
	)) as never;

const KIMI: SamplingRules = {
	thinking_format: 'kimi',
	rules: [
		{ param: 'temperature', allowed: 1, allowed_without_thinking: 0.6 },
		{ param: 'top_p', allowed: 0.95, allowed_without_thinking: null },
		{ param: 'n', allowed: 1, allowed_without_thinking: null }
	]
};

describe('samplingNote', () => {
	it('names every fixed param a model sets, whatever the value', () => {
		expect(samplingNote(KIMI, t, { temperature: 0.3, top_p: null })).toBe(
			'Kimi does not accept custom temperature (only 1; 0.6 with thinking off); they are removed automatically when sending.'
		);
		expect(samplingNote(KIMI, t, { top_p: 0.95, n: 1 })).toBe(
			'Kimi does not accept custom top_p (only 0.95), n (only 1); they are removed automatically when sending.'
		);
		expect(samplingNote(KIMI, t, { max_tokens: 100 })).toBeNull();
		expect(samplingNote(KIMI, t, {})).toBeNull();
	});

	it('lists the whole table for a connection', () => {
		expect(samplingNote(KIMI, t)).toBe(
			'Kimi does not accept custom temperature (only 1; 0.6 with thinking off), top_p (only 0.95), n (only 1); they are removed automatically when sending.'
		);
	});

	it('says nothing for providers without fixed params', () => {
		expect(samplingNote({ thinking_format: 'deepseek', rules: [] }, t)).toBeNull();
		expect(samplingNote(null, t, { temperature: 0.3 })).toBeNull();
	});
});
