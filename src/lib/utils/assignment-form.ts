import type { CoachingStyle, ReflectionQuestion } from '$lib/apis/education';
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
	challengeEnabled: boolean;
	challengeRounds: number;
	challengeFocusKeys: string[];
	reflectionQuestions: ReflectionQuestion[];
	rubricCriteria: RubricCriterionDraft[];
};

export type AssignmentPayload = {
	title: string;
	description: string;
	due_at: number;
	score_max: number;
	coaching_style: CoachingStyle;
	challenge_enabled: boolean;
	challenge_rounds: number;
	challenge_focus_keys: string[];
	reflection_questions: ReflectionQuestion[];
	rubric_schema: { criteria: Array<{ key: string; label: string; max_score: number }> };
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** 校验通过返回提交体;不通过返回已翻译的第一条错误。班级由调用方单独校验(新建多选、编辑单选)。 */
export const buildAssignmentPayload = (
	draft: AssignmentDraft,
	t: Translate
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

	const reflectionQuestions = normalizeReflectionQuestions(draft.reflectionQuestions);
	const reflectionError = getReflectionQuestionsError(reflectionQuestions);
	if (reflectionError) return { error: t(reflectionError.key, reflectionError.params) };

	return {
		payload: {
			title: draft.title.trim(),
			description: draft.description.trim(),
			due_at: Math.floor(new Date(draft.dueAt).getTime() / 1000),
			score_max: scoreMax,
			coaching_style: draft.coachingStyle,
			challenge_enabled: draft.challengeEnabled,
			challenge_rounds: draft.challengeRounds,
			challenge_focus_keys: draft.challengeEnabled ? draft.challengeFocusKeys : [],
			reflection_questions: reflectionQuestions,
			rubric_schema: { criteria }
		}
	};
};
