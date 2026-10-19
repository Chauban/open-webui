import type { i18n as i18nType } from 'i18next';

// 模型在思考上能做什么(只有开 / 关等)。表在后端 utils/thinking.py(MODEL_THINKING_SUPPORT),
// 发送时按它翻译;模型列表里每个模型带着同一张表算出的 thinking_support,这里写成提示。

export type ThinkingSupport = { graded: boolean };

type ModelWithSupport = { id: string; thinking_support?: ThinkingSupport | null };

type Translate = i18nType['t'];

/** 没有这项(不是 OpenAI 兼容连接上的模型)时当作没有限制。 */
export const thinkingSupportOf = (
	models: ModelWithSupport[] | null | undefined,
	id: string | null | undefined
): ThinkingSupport | null =>
	id ? (models?.find((model) => model.id === id)?.thinking_support ?? null) : null;

export const thinkingSupportNote = (
	support: ThinkingSupport | null,
	t: Translate
): string | null => {
	if (!support) return null;
	if (!support.graded) {
		return t('This model only turns thinking on or off: Low, Medium and High all just turn it on.');
	}
	return null;
};
