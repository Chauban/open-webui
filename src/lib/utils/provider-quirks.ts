import type { i18n as i18nType } from 'i18next';

import { getProviderQuirks } from '$lib/apis/openai';

// 管理员页的「服务商注意事项」。条目由后端按发送时实际读的表生成(utils/provider_quirks.py),
// 这里只把每种 kind 写成话;管理员看到的说法和代码执行的不会脱节。

export type FixedParam = {
	param: string;
	allowed: number;
	allowed_without_thinking: number | null;
};
export type ProviderQuirk = {
	kind: string;
	/** 针对哪些模型(id 前缀);空 = 整家,'*' = 表里没单列的其余型号,'this' = 当前这个模型。 */
	models: string[];
	params?: FixedParam[];
	mapping?: Record<string, string>;
	formats?: string[];
	seconds?: number;
};
export type ProviderQuirks = { thinking_format: string | null; quirks: ProviderQuirk[] };

type Translate = i18nType['t'];

const PROVIDER_LABEL: Record<string, string> = {
	deepseek: 'DeepSeek',
	kimi: 'Kimi',
	zhipu: 'GLM',
	doubao: 'Doubao',
	qwen: 'Qwen',
	openai: 'OpenAI',
	anthropic: 'Anthropic',
	openrouter: 'OpenRouter',
	chat_template: 'chat_template'
};

export const providerLabel = (format: string, t: Translate) => t(PROVIDER_LABEL[format] ?? format);

const modelsLabel = (models: string[], t: Translate) =>
	models
		.map((model) =>
			model === '*' ? t('Other models') : model === 'this' ? t('This model') : model
		)
		.join(t(', '));

const paramText = (rule: FixedParam, t: Translate) =>
	rule.allowed_without_thinking !== null
		? t('{{param}} = {{allowed}} ({{without}} with thinking off)', {
				param: rule.param,
				allowed: rule.allowed,
				without: rule.allowed_without_thinking
			})
		: t('{{param}} = {{allowed}}', { param: rule.param, allowed: rule.allowed });

/** 一条注意事项写成一句话;format 是这条所属的服务商(思考格式)。不认识的 kind 返回 null。 */
export const quirkText = (
	quirk: ProviderQuirk,
	format: string | null,
	t: Translate
): string | null => {
	const provider = format ? providerLabel(format, t) : '';
	const models = quirk.models.length > 0 ? modelsLabel(quirk.models, t) : provider;
	switch (quirk.kind) {
		case 'fixed_sampling':
			return t(
				'{{provider}} only accepts fixed sampling values: {{params}}. Whatever is set here is removed before sending.',
				{ provider, params: (quirk.params ?? []).map((rule) => paramText(rule, t)).join(t(', ')) }
			);
		case 'on_off_only':
			return t(
				'{{models}}: thinking is only on or off; Low, Medium and High all just turn it on.',
				{
					models
				}
			);
		case 'cannot_turn_off':
			return t('{{models}}: thinking cannot be turned off; Off uses the lowest level instead.', {
				models
			});
		case 'always_thinking':
			return t(
				'{{models}}: always thinks and has no levels; no thinking setting is sent, whatever is chosen.',
				{ models }
			);
		case 'effort_mapping':
			return t(
				'{{models}}: only low / high / max exist, so Medium is sent as {{medium}} and High as {{high}}; medium is never sent.',
				{ models, medium: quirk.mapping?.medium, high: quirk.mapping?.high }
			);
		case 'thinks_by_default':
			return t('{{provider}}: Model default means thinking is on.', { provider });
		case 'peak_pricing':
			return t(
				'DeepSeek charges double at peak hours (Beijing time, weekdays 9:00–12:00 and 14:00–18:00), which overlap with class and homework time.'
			);
		case 'summary_billing':
			return t(
				'Doubao seed-2.1 and some newer models return only a thinking summary but bill all the original thinking tokens, so the bill can be much larger than the visible thinking.'
			);
		case 'json_mode':
			return t('Qwen does not support JSON mode or structured output while thinking is on.');
		case 'model_default_thinks':
			return t(
				'Model default means thinking is on for {{providers}}; pick a level to control cost and speed.',
				{
					providers: (quirk.formats ?? []).map((item) => providerLabel(item, t)).join(t(', '))
				}
			);
		case 'slow_step':
			return t(
				'With High or Model default, a first read can take longer than the {{seconds}}-second timeout; Low is recommended.',
				{ seconds: quirk.seconds }
			);
		default:
			return null;
	}
};

export const quirkTexts = (quirks: ProviderQuirks | null, t: Translate): string[] =>
	(quirks?.quirks ?? [])
		.map((quirk) => quirkText(quirk, quirks?.thinking_format ?? null, t))
		.filter((text): text is string => Boolean(text));

export type ModelDefaultGroup =
	| { outcome: 'effort'; format: string; effort: string }
	| { outcome: 'on' | 'default_on' | 'always'; models: { label: string; series: boolean }[] };

/**
 * 「模型默认」的说明:第一句是定义;后半句按后端从目前接入的模型与能力表算出的分组(model_default_meaning)写,
 * 接入的模型变了说法跟着变。
 */
export const modelDefaultNote = (groups: ModelDefaultGroup[] | null | undefined, t: Translate) => {
	const definition = t('Model default = no thinking parameter is sent; the provider decides.');
	if (!groups || groups.length === 0) return definition;
	const names = (models: { label: string; series: boolean }[]) =>
		models
			.map((model) => (model.series ? t('{{model}} series', { model: model.label }) : model.label))
			.join(t(', '));
	const parts = groups.map((group) =>
		group.outcome === 'effort'
			? t('{{provider}}: {{effort}}', {
					provider: providerLabel(group.format, t),
					effort: group.effort
				})
			: group.outcome === 'on'
				? t('{{models}}: on', { models: names(group.models) })
				: group.outcome === 'default_on'
					? t('{{models}} thinks by default', { models: names(group.models) })
					: t('{{models}} always thinks', { models: names(group.models) })
	);
	if (groups.some((group) => group.outcome === 'default_on' || group.outcome === 'always')) {
		parts.push(t('the provider does not publish the exact level'));
	}
	const note = `${definition}${t(
		'For the models connected now it usually means thinking is on: {{details}}.',
		{
			details: parts.join(t('; '))
		}
	)}`;
	// 拼出来的中文里两个汉字之间不留空格(「glm-5.3 系列 始终思考」→「glm-5.3 系列始终思考」),英文不受影响。
	return note.replace(/([一-鿿]) (?=[一-鿿])/g, '$1');
};

/** 读不到(非管理员、模型不在连接里)时当作没有注意事项,不挡编辑。 */
export const loadProviderQuirks = async (
	token: string,
	body: { model_id?: string; url?: string; thinking_format?: string }
): Promise<ProviderQuirks | null> => getProviderQuirks(token, body).catch(() => null);
