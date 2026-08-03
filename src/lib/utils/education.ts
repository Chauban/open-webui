// 教学模块页面共用的展示层辅助函数。
// 这些函数都要翻译，所以由调用方把 t 传进来（页面各自持有 i18n context）。

type Translate = (key: string) => string;

/** 系统建的默认班级名走词条，教师自定义的班级名原样显示。 */
export const getClassroomDisplayName = (name: string | null | undefined, t: Translate) =>
	name?.trim() === 'Default Classroom' ? t('Default Classroom') : (name ?? '');

const AI_HELP_TYPE_KEYS = [
	'Understand Assignment',
	'Outline',
	'Examples',
	'Explain Concepts',
	'Revise Structure',
	'Polish',
	'Check Errors',
	"Help Break Through Writer's Block",
	'Strengthen Reasoning',
	'Other'
];

/** 微反思里学生勾选的 AI 帮助类型；未知值原样返回。 */
export const getAiHelpTypeLabel = (value: string, t: Translate) =>
	AI_HELP_TYPE_KEYS.includes(value) ? t(value) : value;

const REVIEW_STATUS_KEYS: Record<string, string> = {
	pending: 'Pending Review',
	reviewed: 'Reviewed',
	returned: 'Returned'
};

/** SubmissionReview.review_status 的展示文案。 */
export const getReviewStatusLabel = (value: string, t: Translate) =>
	REVIEW_STATUS_KEYS[value] ? t(REVIEW_STATUS_KEYS[value]) : value;

const ASSIGNMENT_STATUS_KEYS: Record<string, string> = {
	active: 'Active',
	archived: 'Archived'
};

/** Assignment.status 的展示文案（「已截止」由 due_at 派生，不在这里）。 */
export const getAssignmentStatusLabel = (value: string, t: Translate) =>
	ASSIGNMENT_STATUS_KEYS[value] ? t(ASSIGNMENT_STATUS_KEYS[value]) : value;

/** epoch 秒 → `<input type="datetime-local">` 需要的本地时间字符串。 */
export const toLocalDateTimeInput = (epoch: number) => {
	const date = new Date(epoch * 1000);
	const pad = (value: number) => String(value).padStart(2, '0');
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

/** epoch 秒 → 浏览器本地时区的可读时间。 */
export const formatEpoch = (epoch: number | null | undefined) =>
	epoch ? new Date(epoch * 1000).toLocaleString() : '';
