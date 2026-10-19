import type {
	AiStepKey,
	AiStepModelSource,
	RetryScope,
	ThinkingControl,
	ThinkingSetting
} from '$lib/apis/education';

// 管理员「AI 步骤设置」表与教师作业页 AI 设置卡共用的文案。步骤本身由后端登记下发,
// 这里只管每个步骤怎么称呼、怎么解释。

export const AI_STEP_TEXT: Record<AiStepKey, { title: string; hint: string; note?: string }> = {
	coaching_chat: {
		title: 'Coaching chat',
		hint: 'The chat in the student writing workspace.'
	},
	first_read: {
		title: 'First read and follow-up review',
		hint: 'Revise-a-draft assignments: the item-by-item read of the draft against the rubric, and the re-check of deferred items.',
		note: 'In trial runs, turning thinking off here led to clearly more missed and wrong judgements.'
	},
	reader_check: {
		title: 'AI reader check',
		hint: 'The questions about the student’s text before submitting.'
	},
	image_parsing: {
		title: 'Draft image parsing',
		hint: 'Transcribes photos and scanned pages of a draft into text for the student to check. Pick a model that can read images; a fast model without step-by-step thinking keeps the wait short. Students do not need access to it in chat. Without a model, image import is off.'
	},
	class_insight: {
		title: 'Class argument summary',
		hint: 'Groups the points students could not defend; started by the teacher on the analysis page.'
	}
};

/** 管理员没给这一步指定模型时用谁的。 */
export const MODEL_SOURCE_TEXT: Record<AiStepModelSource, string> = {
	student_chat_model: 'Model the student picked',
	teacher_chat_model: 'Model the teacher picked',
	admin_model: 'Not set'
};

/** 管理员表里「不指定」那一项的文字;图片识别不指定就是不提供图片导入。 */
export const FOLLOW_MODEL_TEXT: Record<AiStepModelSource, string> = {
	student_chat_model: 'Follow the student’s selected model',
	teacher_chat_model: 'Follow the teacher’s selected model',
	admin_model: 'Off (no image import)'
};

/** 指定的模型已被删掉时,这一步实际怎么办。 */
export const MISSING_MODEL_TEXT: Record<AiStepModelSource, string> = {
	student_chat_model:
		'The chosen model is no longer available; this step uses the student’s model until you pick another one.',
	teacher_chat_model:
		'The chosen model is no longer available; this step uses the teacher’s model until you pick another one.',
	admin_model:
		'The chosen model is no longer available. Image import will fail until you pick another one.'
};

export const THINKING_SETTING_TEXT: Record<ThinkingSetting, string> = {
	model_default: 'Model default',
	off: 'Off',
	low: 'Low',
	medium: 'Medium',
	high: 'High'
};

export const THINKING_SETTINGS = Object.keys(THINKING_SETTING_TEXT) as ThinkingSetting[];

export const THINKING_CONTROL_TEXT: Record<ThinkingControl, string> = {
	admin: 'Admin only',
	teacher: 'Teacher, per assignment',
	student: 'Teacher, may open to students'
};

/** 管理员「自动重发」各行的称呼与说明;行本身由后端登记(RETRY_SCOPES)下发。 */
export const RETRY_SCOPE_TEXT: Record<RetryScope['key'], { title: string; hint: string }> = {
	assignment_chat: {
		title: 'Assignment coaching chat',
		hint: 'The chat in an assignment writing workspace.'
	},
	platform_steps: {
		title: 'First read, AI reader check and class argument summary',
		hint: 'Draft image parsing retries each page on its own.'
	},
	personal_writing: {
		title: 'Personal writing coaching chat',
		hint: 'The chat in a student’s own writing outside assignments. Off by default.'
	}
};
