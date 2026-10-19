import type { i18n as i18nType } from 'i18next';

import { getSamplingRules } from '$lib/apis/openai';

// 服务商固定死、只接受一个值的采样参数。规则表在后端 utils/thinking.py(FIXED_SAMPLING_PARAMS),
// 发送时按它去掉;这里只把同一张表(/openai/sampling-rules)写成管理员看得懂的提示。

export type FixedSamplingParam = {
	param: string;
	allowed: number;
	allowed_without_thinking: number | null;
};
export type SamplingRules = { thinking_format: string | null; rules: FixedSamplingParam[] };

const PROVIDER_LABEL: Record<string, string> = { kimi: 'Kimi' };

type Translate = i18nType['t'];

const describe = (rule: FixedSamplingParam, t: Translate) =>
	rule.allowed_without_thinking !== null
		? t('{{param}} (only {{allowed}}; {{without}} with thinking off)', {
				param: rule.param,
				allowed: rule.allowed,
				without: rule.allowed_without_thinking
			})
		: t('{{param}} (only {{allowed}})', { param: rule.param, allowed: rule.allowed });

/**
 * 给了 params 时只提设了的参数(模型编辑页):值固定,设了什么都会在发送时去掉;没给时列出整张表(连接设置)。
 * 没有要提的返回 null。
 */
export const samplingNote = (
	rules: SamplingRules | null,
	t: Translate,
	params?: Record<string, unknown>
): string | null => {
	if (!rules?.thinking_format || rules.rules.length === 0) return null;
	const relevant = params
		? rules.rules.filter((rule) => params[rule.param] !== null && params[rule.param] !== undefined)
		: rules.rules;
	if (relevant.length === 0) return null;
	return t(
		'{{provider}} does not accept custom {{params}}; they are removed automatically when sending.',
		{
			provider: PROVIDER_LABEL[rules.thinking_format] ?? rules.thinking_format,
			params: relevant.map((rule) => describe(rule, t)).join(', ')
		}
	);
};

/** 读不到(非管理员、模型不在连接里)时当作没有规则,不挡编辑。 */
export const loadSamplingRules = async (
	token: string,
	body: { model_id?: string; url?: string; thinking_format?: string }
): Promise<SamplingRules | null> => getSamplingRules(token, body).catch(() => null);
