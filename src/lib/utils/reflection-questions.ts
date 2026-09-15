// 提交前反思：教师出题、学生作答两侧共用的规则。
// 后端 models/education.py 的 ReflectionQuestion / build_reflection_record 是最终裁判，
// 这里只是提前把错误拦在表单上，让教师和学生不必等到保存/提交才知道哪里没填好。

import type {
	ReflectionAnswer,
	ReflectionQuestion,
	ReflectionQuestionKind,
	ReflectionShowWhen
} from '$lib/apis/education/types';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export const REFLECTION_MAX_QUESTIONS = 20;
export const REFLECTION_MAX_OPTIONS = 12;
export const REFLECTION_PROMPT_MAX = 300;
export const REFLECTION_OPTION_MAX = 100;

export type AiUsage = 'used' | 'none' | null;

export const newReflectionQuestionId = () =>
	(crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)
		.replace(/-/g, '')
		.slice(0, 16);

export const createReflectionQuestion = (kind: ReflectionQuestionKind): ReflectionQuestion => ({
	id: newReflectionQuestionId(),
	kind,
	prompt: '',
	options: kind === 'text' ? [] : ['', ''],
	allow_other: false,
	placeholder: null,
	required: true,
	show_when: 'always'
});

type RecommendedQuestion = {
	/** 进默认题组（教师第一次出题时预填的那一套）。 */
	isDefault: boolean;
	kind: ReflectionQuestionKind;
	prompt: string;
	options?: string[];
	allowOther?: boolean;
	placeholder?: string;
	required?: boolean;
	showWhen?: ReflectionShowWhen;
};

// 词条 key 是英文，插入时按教师界面语言翻成正文——题目一旦进了作业就是教师自己的文字，
// 学生看到的就是这段原文，不再跟着界面语言变。
const RECOMMENDED_QUESTIONS: RecommendedQuestion[] = [
	{
		isDefault: true,
		kind: 'multi_choice',
		prompt: 'What did AI help you with?',
		options: [
			'Understand Assignment',
			'Outline',
			'Examples',
			'Explain Concepts',
			'Revise Structure',
			'Polish',
			'Check Errors',
			"Help Break Through Writer's Block",
			'Strengthen Reasoning'
		],
		allowOther: true,
		showWhen: 'ai_used'
	},
	{
		isDefault: true,
		kind: 'text',
		prompt: 'What did you change?',
		placeholder: 'Describe the concrete revision you made.'
	},
	{
		isDefault: true,
		kind: 'text',
		prompt: 'Where did you make this change?',
		placeholder: 'For example: paragraph 2, the conclusion, or the evidence section.'
	},
	{
		isDefault: true,
		kind: 'text',
		prompt: 'Why did you make this judgement?',
		placeholder: 'Explain why you accepted, rejected, or changed the suggestion or feedback.'
	},
	{
		isDefault: true,
		kind: 'text',
		prompt: 'What will you do next time?',
		placeholder: 'Write one concrete action for your next assignment.'
	},
	{
		isDefault: false,
		kind: 'text',
		prompt: 'Which AI suggestion did you not adopt, and why?',
		placeholder: 'Name the suggestion and your reason.',
		showWhen: 'ai_used'
	},
	{
		isDefault: false,
		kind: 'single_choice',
		prompt: 'How much of your final draft did AI shape?',
		options: ['Hardly any', 'Some parts', 'Most of it'],
		showWhen: 'ai_used'
	},
	{
		isDefault: false,
		kind: 'single_choice',
		prompt: 'Why did you choose not to use AI?',
		options: ['I did not need it', 'I wanted to practise on my own', 'I do not trust its answers'],
		allowOther: true,
		required: false,
		showWhen: 'ai_not_used'
	},
	{
		isDefault: false,
		kind: 'single_choice',
		prompt: 'How satisfied are you with this draft?',
		options: ['Not satisfied', 'Mostly satisfied', 'Very satisfied']
	},
	{
		isDefault: false,
		kind: 'text',
		prompt: 'What was the hardest part of this assignment?',
		placeholder: 'For example: finding evidence, or structuring the argument.'
	}
];

const materialize = (item: RecommendedQuestion, t: Translate): ReflectionQuestion => ({
	id: newReflectionQuestionId(),
	kind: item.kind,
	prompt: t(item.prompt),
	options: (item.options ?? []).map((option) => t(option)),
	allow_other: item.allowOther ?? false,
	placeholder: item.placeholder ? t(item.placeholder) : null,
	required: item.required ?? true,
	show_when: item.showWhen ?? 'always'
});

/** 推荐题库，按教师界面语言成文。 */
export const getRecommendedReflectionQuestions = (t: Translate) =>
	RECOMMENDED_QUESTIONS.map((item) => ({
		isDefault: item.isDefault,
		question: materialize(item, t)
	}));

export const getDefaultReflectionQuestions = (t: Translate) =>
	getRecommendedReflectionQuestions(t)
		.filter((item) => item.isDefault)
		.map((item) => item.question);

/** 换一套 id 复制一份，免得两份作业共用同一组题目 id。 */
export const cloneReflectionQuestions = (questions: ReflectionQuestion[]) =>
	questions.map((question) => ({
		...question,
		id: newReflectionQuestionId(),
		options: [...question.options]
	}));

/** 忽略 id 比较两套题是否内容相同。 */
export const reflectionQuestionsFingerprint = (questions: ReflectionQuestion[]) =>
	JSON.stringify(
		questions.map(({ kind, prompt, options, allow_other, placeholder, required, show_when }) => [
			kind,
			prompt.trim(),
			kind === 'text' ? [] : options.map((option) => option.trim()).filter(Boolean),
			kind === 'text' ? false : allow_other,
			kind === 'text' ? (placeholder?.trim() ?? '') : '',
			required,
			show_when
		])
	);

/** 保存前整理：去首尾空白、丢掉空选项，按题型清掉不适用的字段。 */
export const normalizeReflectionQuestions = (
	questions: ReflectionQuestion[]
): ReflectionQuestion[] =>
	questions.map((question) => {
		const isText = question.kind === 'text';
		return {
			...question,
			prompt: question.prompt.trim(),
			options: isText
				? []
				: question.options.map((option) => option.trim()).filter((option) => option.length > 0),
			allow_other: isText ? false : question.allow_other,
			placeholder: isText ? question.placeholder?.trim() || null : null
		};
	});

export type ReflectionQuestionsError = {
	key: string;
	params?: Record<string, unknown>;
};

/** 对整理后的题目做保存前校验，返回第一处错误。 */
export const getReflectionQuestionsError = (
	questions: ReflectionQuestion[]
): ReflectionQuestionsError | null => {
	if (questions.length > REFLECTION_MAX_QUESTIONS) {
		return {
			key: 'An assignment can have at most {{max}} reflection questions.',
			params: { max: REFLECTION_MAX_QUESTIONS }
		};
	}
	for (const [index, question] of questions.entries()) {
		const params = { number: index + 1 };
		if (!question.prompt) {
			return { key: 'Reflection question {{number}} needs a prompt.', params };
		}
		if (question.prompt.length > REFLECTION_PROMPT_MAX) {
			return { key: 'Reflection question {{number}} is too long.', params };
		}
		if (question.kind === 'text') continue;
		if (question.options.length + (question.allow_other ? 1 : 0) < 2) {
			return { key: 'Reflection question {{number}} needs at least two options.', params };
		}
		if (question.options.length > REFLECTION_MAX_OPTIONS) {
			return {
				key: 'Reflection question {{number}} can have at most {{max}} options.',
				params: { ...params, max: REFLECTION_MAX_OPTIONS }
			};
		}
		if (question.options.some((option) => option.length > REFLECTION_OPTION_MAX)) {
			return { key: 'An option in reflection question {{number}} is too long.', params };
		}
		if (new Set(question.options).size !== question.options.length) {
			return { key: 'Reflection question {{number}} has duplicate options.', params };
		}
	}
	return null;
};

export const isReflectionQuestionVisible = (question: ReflectionQuestion, aiUsage: AiUsage) => {
	if (question.show_when === 'ai_used') return aiUsage === 'used';
	if (question.show_when === 'ai_not_used') return aiUsage === 'none';
	return true;
};

/** 学生作答时的草稿。「其他」勾选与说明分开存，勾上还没写字时不能丢掉勾选。 */
export type ReflectionAnswerDraft = {
	selected: string[];
	otherChosen: boolean;
	otherText: string;
	text: string;
};

export type ReflectionAnswerDrafts = Record<string, ReflectionAnswerDraft>;

export const emptyReflectionAnswerDraft = (): ReflectionAnswerDraft => ({
	selected: [],
	otherChosen: false,
	otherText: '',
	text: ''
});

export const getReflectionAnswersError = (
	questions: ReflectionQuestion[],
	aiUsage: AiUsage,
	drafts: ReflectionAnswerDrafts
): ReflectionQuestionsError | null => {
	if (aiUsage == null) return { key: 'Choose whether AI was used.' };
	for (const question of questions) {
		if (!isReflectionQuestionVisible(question, aiUsage)) continue;
		const draft = drafts[question.id] ?? emptyReflectionAnswerDraft();
		const params = { prompt: question.prompt };
		if (question.kind === 'text') {
			if (question.required && !draft.text.trim()) {
				return { key: 'Please answer: {{prompt}}', params };
			}
			continue;
		}
		const selected = draft.selected.filter((option) => question.options.includes(option));
		const otherChosen = question.allow_other && draft.otherChosen;
		if (otherChosen && !draft.otherText.trim()) {
			return { key: 'Please describe your "Other" answer to: {{prompt}}', params };
		}
		if (question.required && selected.length === 0 && !otherChosen) {
			return { key: 'Please answer: {{prompt}}', params };
		}
	}
	return null;
};

/** 只提交当前可见题目的回答；题目被教师改掉的残留草稿在这里自然丢弃。 */
export const buildReflectionAnswers = (
	questions: ReflectionQuestion[],
	aiUsage: AiUsage,
	drafts: ReflectionAnswerDrafts
): ReflectionAnswer[] =>
	questions
		.filter((question) => isReflectionQuestionVisible(question, aiUsage))
		.map((question) => {
			const draft = drafts[question.id] ?? emptyReflectionAnswerDraft();
			if (question.kind === 'text') {
				return {
					question_id: question.id,
					selected: [],
					other_text: null,
					text: draft.text.trim() || null
				};
			}
			const otherChosen = question.allow_other && draft.otherChosen;
			const selected = draft.selected.filter((option) => question.options.includes(option));
			return {
				question_id: question.id,
				selected: question.kind === 'single_choice' && otherChosen ? [] : selected,
				other_text: otherChosen ? draft.otherText.trim() || null : null,
				text: null
			};
		});
