import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/apis/openai', () => ({ getProviderQuirks: vi.fn() }));

import { modelDefaultNote, quirkText, quirkTexts, type ProviderQuirk } from './provider-quirks';

const t = ((key: string, options?: Record<string, unknown>) =>
	Object.entries(options ?? {}).reduce(
		(text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
		key
	)) as never;

const KIMI_FIXED: ProviderQuirk = {
	kind: 'fixed_sampling',
	models: [],
	params: [
		{ param: 'temperature', allowed: 1, allowed_without_thinking: 0.6 },
		{ param: 'top_p', allowed: 0.95, allowed_without_thinking: null },
		{ param: 'n', allowed: 1, allowed_without_thinking: null }
	]
};

describe('provider quirks', () => {
	it('spells out every fixed Kimi value, including temperature with thinking off', () => {
		expect(quirkText(KIMI_FIXED, 'kimi', t)).toBe(
			'Kimi only accepts fixed sampling values: temperature = 1 (0.6 with thinking off), top_p = 0.95, n = 1. Whatever is set here is removed before sending.'
		);
	});

	it('names the models a thinking limit applies to', () => {
		expect(quirkText({ kind: 'on_off_only', models: ['kimi-k2.6'] }, 'kimi', t)).toBe(
			'kimi-k2.6: thinking is only on or off; Low, Medium and High all just turn it on.'
		);
		expect(
			quirkText({ kind: 'always_thinking', models: ['glm-4.7', 'glm-4.5v'] }, 'zhipu', t)
		).toContain('glm-4.7, glm-4.5v: always thinks');
		expect(quirkText({ kind: 'cannot_turn_off', models: ['this'] }, 'zhipu', t)).toContain(
			'This model: thinking cannot be turned off; Off uses the lowest level instead.'
		);
		expect(quirkText({ kind: 'on_off_only', models: ['*'] }, 'zhipu', t)).toContain('Other models');
		expect(
			quirkText(
				{ kind: 'effort_mapping', models: [], mapping: { medium: 'high', high: 'max' } },
				'deepseek',
				t
			)
		).toBe(
			'DeepSeek: only low / high / max exist, so Medium is sent as high and High as max; medium is never sent.'
		);
	});

	it('writes facts and step notes, and skips kinds it does not know', () => {
		const texts = quirkTexts(
			{
				thinking_format: 'deepseek',
				quirks: [
					{ kind: 'thinks_by_default', models: [] },
					{ kind: 'peak_pricing', models: [] },
					{ kind: 'something_new', models: [] }
				]
			},
			t
		);
		expect(texts).toEqual([
			'DeepSeek: Model default means thinking is on.',
			expect.stringContaining('DeepSeek charges double at peak hours')
		]);
		expect(quirkText({ kind: 'slow_step', models: [], seconds: 90 }, null, t)).toContain(
			'90-second timeout; Low is recommended'
		);
		expect(quirkTexts(null, t)).toEqual([]);
	});

	it('explains Model default from the connected-model groups', () => {
		expect(modelDefaultNote([], t)).toBe(
			'Model default = no thinking parameter is sent; the provider decides.'
		);
		const note = modelDefaultNote(
			[
				{ outcome: 'effort', format: 'deepseek', effort: 'high' },
				{ outcome: 'on', models: [{ label: 'kimi-k2.6', series: false }] },
				{ outcome: 'default_on', models: [{ label: 'kimi-k3', series: false }] },
				{ outcome: 'always', models: [{ label: 'glm-5.3', series: true }] }
			],
			t
		);
		expect(note).toBe(
			'Model default = no thinking parameter is sent; the provider decides.For the models connected now it usually means thinking is on: DeepSeek: high; kimi-k2.6: on; kimi-k3 thinks by default; glm-5.3 series always thinks; the provider does not publish the exact level.'
		);
		// 中文里系列与动词之间不留空格,拉丁字母与汉字之间照常留
		const zh = ((key: string, options?: Record<string, unknown>) =>
			Object.entries(options ?? {}).reduce(
				(text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
				(
					{
						'{{model}} series': '{{model}} 系列',
						'{{models}} always thinks': '{{models}} 始终思考',
						'{{models}} thinks by default': '{{models}} 默认思考'
					} as Record<string, string>
				)[key] ?? key
			)) as never;
		expect(
			modelDefaultNote(
				[
					{ outcome: 'default_on', models: [{ label: 'kimi-k3', series: false }] },
					{ outcome: 'always', models: [{ label: 'glm-5.3', series: true }] }
				],
				zh
			)
		).toContain('kimi-k3 默认思考; glm-5.3 系列始终思考');
		// 只有公开了档位的服务商时不提「未公开」
		expect(
			modelDefaultNote([{ outcome: 'effort', format: 'deepseek', effort: 'high' }], t)
		).not.toContain('does not publish');
	});
});
