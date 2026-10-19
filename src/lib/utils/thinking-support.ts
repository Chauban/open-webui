// 模型在思考上能做什么(只有开 / 关等)。表在后端 utils/thinking.py(MODEL_THINKING_SUPPORT),
// 发送时按它翻译;模型列表里每个模型带着同一张表算出的 thinking_support,学生端开关据此判断。

export type ThinkingSupport = { can_turn_off: boolean; graded: boolean };

type ModelWithSupport = { id: string; thinking_support?: ThinkingSupport | null };

/** 没有这项(不是 OpenAI 兼容连接上的模型)时当作没有限制。 */
export const thinkingSupportOf = (
	models: ModelWithSupport[] | null | undefined,
	id: string | null | undefined
): ThinkingSupport | null =>
	id ? (models?.find((model) => model.id === id)?.thinking_support ?? null) : null;

/** 关不掉思考的模型:学生的「深度思考」开关不可用,写明始终开着。 */
export const thinksAlways = (support: ThinkingSupport | null): boolean =>
	support?.can_turn_off === false;
