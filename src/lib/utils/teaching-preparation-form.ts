import type { AiCandidate } from '$lib/apis/education/teaching';
import { getAssignmentScoringError, type AssignmentDraft } from './assignment-form';
import { getReflectionQuestionsError, normalizeReflectionQuestions } from './reflection-questions';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export const getAiCandidateErrors = (ai: AiCandidate, t: Translate) => {
	const errors: string[] = [];
	if (!ai.prompt.trim()) errors.push(t('请填写辅导提示词。'));
	else if (ai.prompt.length > 65000) errors.push(t('辅导提示词不能超过 65000 个字符。'));
	if (!ai.model_id) errors.push(t('请选择本次作业的辅导模型。'));
	return errors;
};

export const getPreparationErrors = (draft: AssignmentDraft, ai: AiCandidate, t: Translate) => {
	const errors = draft.taskMode === 'revise_argument' ? getAiCandidateErrors(ai, t) : [];
	const scoringError = getAssignmentScoringError(draft, t);
	if (scoringError) errors.push(scoringError);
	const reflectionError = getReflectionQuestionsError(
		normalizeReflectionQuestions(draft.reflectionQuestions)
	);
	if (reflectionError) errors.push(t(reflectionError.key, reflectionError.params));
	return errors;
};

const FIELD_LABELS: Record<string, string> = {
	title: 'Assignment title',
	description: 'Assignment description',
	classroom_ids: '班级',
	due_at: 'Due At',
	score_max: 'Maximum Score',
	rubric_schema: 'Rubric Criteria',
	reflection_questions: 'Reflection Before Submitting',
	prompt: '你希望 AI 怎样辅导学生',
	model_id: '本次作业的辅导模型',
	thinking: '思考设置',
	change_summary: '调整说明'
};

/** FastAPI 的字段校验与业务错误都转换为可读文案，不显示对象或内部字段路径。 */
export const preparationErrorMessages = (error: unknown, t: Translate): string[] => {
	const fallback = () => [t('操作失败，请检查填写内容后重试。')];
	if (error instanceof Error) return [t(error.message)];
	if (typeof error === 'string') return [t(error)];
	if (!error || typeof error !== 'object') return fallback();
	const detail = (error as { detail?: unknown }).detail;
	if (Array.isArray(detail)) {
		const messages = detail.map((item: unknown) => {
			if (!item || typeof item !== 'object') return fallback()[0];
			const issue = item as { loc?: unknown; msg?: unknown; type?: unknown };
			const message = typeof issue.msg === 'string' ? issue.msg.replace(/^Value error, /, '') : '';
			if (message) {
				const translated = t(message);
				if (
					translated !== message ||
					issue.msg !== message ||
					issue.type === 'required_for_publication'
				)
					return translated;
			}
			const field = Array.isArray(issue.loc)
				? [...issue.loc].reverse().find((part) => typeof part === 'string' && FIELD_LABELS[part])
				: undefined;
			return field
				? t('请检查“{{field}}”的填写内容。', { field: t(FIELD_LABELS[field]) })
				: fallback()[0];
		});
		return messages.length ? [...new Set(messages)] : fallback();
	}
	if (typeof detail === 'string') return [t(detail)];
	if (detail && typeof detail === 'object') return preparationErrorMessages(detail, t);
	const message = (error as { message?: unknown }).message;
	return typeof message === 'string' ? [t(message)] : fallback();
};
