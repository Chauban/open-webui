import type {
	AssignmentModelParams,
	CoachingStyle,
	ReflectionQuestion,
	TaskMode,
	ThinkingControl,
	ThinkingSetting
} from '$lib/apis/education';
import {
	getReflectionQuestionsError,
	normalizeReflectionQuestions
} from '$lib/utils/reflection-questions';

// 新建作业与作业设置共用的表单草稿与校验。此前两页各抄一份,校验顺序和提示一字不差。

export type RubricCriterionDraft = { key: string; label: string; maxScore: string };

export type AssignmentDraft = {
	title: string;
	description: string;
	dueAt: string;
	scoreMax: string;
	coachingStyle: CoachingStyle;
	taskMode: TaskMode;
	challengeEnabled: boolean;
	challengeRounds: number;
	challengeFocusKeys: string[];
	reflectionQuestions: ReflectionQuestion[];
	rubricCriteria: RubricCriterionDraft[];
	/** 辅导对话的思考档位;null 沿用管理员默认。只在管理员下放后可设。 */
	thinking: ThinkingSetting | null;
	studentsChooseThinking: boolean;
};

export const draftThinkingFrom = (params?: AssignmentModelParams | null) => ({
	thinking: params?.thinking ?? null,
	studentsChooseThinking: params?.students_choose_thinking ?? false
});

export type AssignmentPayload = {
	title: string;
	description: string;
	due_at: number;
	score_max: number;
	coaching_style: CoachingStyle;
	task_mode: TaskMode;
	challenge_enabled: boolean;
	challenge_rounds: number;
	challenge_focus_keys: string[];
	reflection_questions: ReflectionQuestion[];
	rubric_schema: { criteria: Array<{ key: string; label: string; max_score: number }> };
	model_params?: AssignmentModelParams;
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * 校验通过返回提交体;不通过返回已翻译的第一条错误。班级由调用方单独校验(新建多选、编辑单选)。
 * thinkingControl 是管理员对辅导对话思考档位的下放方式:仅管理员时不提交 model_params,
 * 作业里原有的设置留着但后端不再采用;下放给教师时不能交给学生开关(后端同样拒绝)。
 */
export const buildAssignmentPayload = (
	draft: AssignmentDraft,
	t: Translate,
	thinkingControl: ThinkingControl = 'admin'
): { payload: AssignmentPayload; error?: undefined } | { payload?: undefined; error: string } => {
	if (!draft.title.trim()) return { error: t('Assignment title is required.') };
	if (!draft.dueAt) return { error: t('Assignment due time is required.') };

	const scoreMax = Number(draft.scoreMax);
	if (!Number.isInteger(scoreMax) || scoreMax <= 0) {
		return { error: t('Maximum score must be a positive whole number.') };
	}
	const criteria = draft.rubricCriteria.map((criterion) => ({
		key: criterion.key.trim(),
		label: criterion.label.trim(),
		max_score: Number(criterion.maxScore)
	}));
	if (
		criteria.some(
			(criterion) =>
				!criterion.label || !Number.isInteger(criterion.max_score) || criterion.max_score <= 0
		)
	) {
		return { error: t('Every rubric criterion needs a name and a positive whole-number maximum.') };
	}
	if (criteria.reduce((sum, criterion) => sum + criterion.max_score, 0) !== scoreMax) {
		return { error: t('Rubric maximum scores must add up to the assignment maximum.') };
	}

	// 修订初稿作业结构上没有质疑式读者(后端同样拒绝)。
	const challengeEnabled = draft.taskMode === 'from_scratch' && draft.challengeEnabled;

	const reflectionQuestions = normalizeReflectionQuestions(draft.reflectionQuestions);
	const reflectionError = getReflectionQuestionsError(reflectionQuestions);
	if (reflectionError) return { error: t(reflectionError.key, reflectionError.params) };

	const studentsChooseThinking = thinkingControl === 'student' && draft.studentsChooseThinking;
	if (studentsChooseThinking && (draft.thinking === null || draft.thinking === 'off')) {
		return { error: t('Pick the thinking level students switch on.') };
	}

	return {
		payload: {
			title: draft.title.trim(),
			description: draft.description.trim(),
			due_at: Math.floor(new Date(draft.dueAt).getTime() / 1000),
			score_max: scoreMax,
			coaching_style: draft.coachingStyle,
			task_mode: draft.taskMode,
			challenge_enabled: challengeEnabled,
			challenge_rounds: draft.challengeRounds,
			challenge_focus_keys: challengeEnabled ? draft.challengeFocusKeys : [],
			reflection_questions: reflectionQuestions,
			rubric_schema: { criteria },
			...(thinkingControl === 'admin'
				? {}
				: {
						model_params: {
							thinking: draft.thinking,
							students_choose_thinking: studentsChooseThinking
						}
					})
		}
	};
};

export type DefaultRubrics = Partial<Record<TaskMode, Array<{ label: string; max_score: number }>>>;

/**
 * 新建作业预填的评分维度。管理员按作业形式设过就用设定的,没设(空列表)用内置三项。
 * 修订初稿的第一次通读按作业的评分维度逐项下结论,所以实例要按提示词里的标准设这一份。
 */
export const getDefaultRubricCriteria = (
	rubrics: DefaultRubrics | undefined,
	taskMode: TaskMode,
	t: Translate
): RubricCriterionDraft[] => {
	const configured = rubrics?.[taskMode] ?? [];
	const criteria = configured.length
		? configured.map((criterion) => ({ label: criterion.label, maxScore: String(criterion.max_score) }))
		: [
				{ label: t('Ideas'), maxScore: '34' },
				{ label: t('Structure'), maxScore: '33' },
				{ label: t('Evidence'), maxScore: '33' }
			];
	return criteria.map((criterion, index) => ({ key: `criterion_${index + 1}`, ...criterion }));
};

export const rubricTotal = (criteria: RubricCriterionDraft[]) =>
	String(criteria.reduce((sum, criterion) => sum + (Number(criterion.maxScore) || 0), 0));

export const isSameRubric = (a: RubricCriterionDraft[], b: RubricCriterionDraft[]) =>
	a.length === b.length &&
	a.every(
		(criterion, index) =>
			criterion.label.trim() === b[index].label.trim() && criterion.maxScore === b[index].maxScore
	);
