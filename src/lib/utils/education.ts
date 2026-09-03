// 教学模块页面共用的展示层辅助函数。
// 这些函数都要翻译，所以由调用方把 t 传进来（页面各自持有 i18n context）。

import i18next from 'i18next';

type Translate = (key: string, options?: Record<string, unknown>) => string;

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
	active: 'Ongoing',
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

/**
 * 展示层的日期时间跟随界面语言，而不是浏览器语言——整页中文时，
 * 截止时间不能还渲染成 "9/10/2026, 11:59 PM"。界面语言不被 Intl 支持时退回浏览器默认。
 */
const getUiLocale = () => {
	try {
		return Intl.DateTimeFormat.supportedLocalesOf(i18next.language ?? [])[0];
	} catch {
		return undefined;
	}
};

// 时间线、提交列表都在循环里格式化，Intl 实例按「语言 + 选项」缓存复用。
const formatterCache = new Map<string, Intl.DateTimeFormat>();
const getFormatter = (options: Intl.DateTimeFormatOptions) => {
	const locale = getUiLocale();
	const cacheKey = `${locale ?? ''}|${JSON.stringify(options)}`;
	let formatter = formatterCache.get(cacheKey);
	if (!formatter) {
		formatter = new Intl.DateTimeFormat(locale, options);
		formatterCache.set(cacheKey, formatter);
	}
	return formatter;
};

/** epoch 秒 → 「2026年9月10日 23:59」这类完整可读时间。 */
export const formatEpoch = (epoch: number | null | undefined) =>
	epoch ? getFormatter({ dateStyle: 'medium', timeStyle: 'short' }).format(epoch * 1000) : '';

/**
 * `<input type="datetime-local">` 的显示格式由浏览器语言决定，页面改不了：
 * 中文界面里它可能依旧渲染成 mm/dd/yyyy。在输入框下方按界面语言回显一遍，
 * 教师布置作业时不会把年月日看反。
 */
export const formatDateTimeInput = (value: string | null | undefined) => {
	if (!value) return '';
	const time = new Date(value).getTime();
	return Number.isNaN(time) ? '' : formatEpoch(Math.floor(time / 1000));
};

/** epoch 秒 → 只到日期（目标日期这类不看时分的场景）。 */
export const formatEpochDate = (epoch: number | null | undefined) =>
	epoch ? getFormatter({ dateStyle: 'medium' }).format(epoch * 1000) : '';

/** epoch 秒 → 只到时分（同一段时间线里逐条事件的时刻）。 */
export const formatEpochTime = (epoch: number | null | undefined) =>
	epoch ? getFormatter({ hour: '2-digit', minute: '2-digit' }).format(epoch * 1000) : '';

/** 成长画像的趋势图横轴：只要月日，避免刻度挤在一起。 */
export const formatShortDate = (epoch: number | null | undefined) =>
	epoch ? getFormatter({ month: 'short', day: 'numeric' }).format(epoch * 1000) : '';

/**
 * 后端把校验与权限错误的文案直接放在 detail 里（英文），整页中文时不能原样 toast。
 * 这些文案在词条表里逐条落了译文；缺词条时 i18next 会原样返回英文，不会渲染成空。
 */
export const resolveErrorMessage = (error: unknown, t: Translate) => {
	const detail = (error as { detail?: unknown } | null)?.detail ?? error;
	if (typeof detail === 'string') return t(detail);
	if (detail && typeof detail === 'object') {
		const nested = (detail as { detail?: unknown }).detail;
		if (typeof nested === 'string') return t(nested);
	}
	return `${detail}`;
};

/** 0-1 的比率 → 百分比整数文案。 */
export const formatRatioPercent = (ratio: number | null | undefined) =>
	ratio == null ? '—' : `${Math.round(ratio * 100)}%`;

/** 秒 → 「3 小时 20 分」这类紧凑时长；不足 1 分钟按 1 分钟算。 */
export const formatDuration = (seconds: number | null | undefined, t: Translate) => {
	if (!seconds || seconds <= 0) return '—';
	const days = Math.floor(seconds / 86400);
	if (days >= 1) {
		return t('{{count}}d', { count: days });
	}
	const hours = Math.floor(seconds / 3600);
	const minutes = Math.max(Math.round((seconds % 3600) / 60), hours > 0 ? 0 : 1);
	if (hours > 0) {
		return t('{{hours}}h {{minutes}}m', { hours, minutes });
	}
	return t('{{count}}m', { count: minutes });
};

/**
 * 评分维度的 key 只是后端 rubric_scores 的字段名，教师不该关心，
 * 所以新增维度时自动生成一个不与现有 key 冲突的标识。
 */
export const nextCriterionKey = (existingKeys: string[]) => {
	const used = new Set(existingKeys);
	let index = 1;
	while (used.has(`criterion_${index}`)) {
		index += 1;
	}
	return `criterion_${index}`;
};

/** 把作业满分平均摊到各维度上，余数从第一个维度依次加 1，保证总和刚好等于满分。 */
export const distributeCriterionScores = (count: number, total: number) => {
	if (count <= 0 || !Number.isInteger(total) || total < count) return [];
	const base = Math.floor(total / count);
	const remainder = total - base * count;
	return Array.from({ length: count }, (_, index) => base + (index < remainder ? 1 : 0));
};
