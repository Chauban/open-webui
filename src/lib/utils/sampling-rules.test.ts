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
		{ param: 'temperature', allowed: 1, models: [] },
		{ param: 'top_p', allowed: 0.95, models: ['kimi-k2.6'] }
	]
};

describe('samplingNote', () => {
	it('names only the params a model sets to a value the provider rejects', () => {
		expect(samplingNote(KIMI, t, { temperature: 0.3, top_p: null })).toBe(
			'Kimi does not accept custom temperature (only 1); they are removed automatically when sending.'
		);
		expect(samplingNote(KIMI, t, { temperature: 1, top_p: 0.95 })).toBeNull();
		expect(samplingNote(KIMI, t, {})).toBeNull();
	});

	it('lists the whole table for a connection, with the models a rule is limited to', () => {
		expect(samplingNote(KIMI, t)).toBe(
			'Kimi does not accept custom temperature (only 1), top_p (only 0.95, kimi-k2.6); they are removed automatically when sending.'
		);
	});

	it('says nothing for providers without fixed params', () => {
		expect(samplingNote({ thinking_format: 'deepseek', rules: [] }, t)).toBeNull();
		expect(samplingNote(null, t, { temperature: 0.3 })).toBeNull();
	});
});
