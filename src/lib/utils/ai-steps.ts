import type {
	AiStepKey,
	AiStepModelSource,
	ThinkingControl,
	ThinkingSetting
} from '$lib/apis/education';

// 管理员「AI 思考设置」表与教师作业页 AI 设置卡共用的文案。步骤本身由后端登记下发,
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
		hint: 'Transcribes photos and scanned pages into text.'
	},
	class_insight: {
		title: 'Class argument summary',
		hint: 'Groups the points students could not defend; started by the teacher on the analysis page.'
	}
};

export const MODEL_SOURCE_TEXT: Record<AiStepModelSource, string> = {
	student_chat_model: 'Model the student picked',
	draft_image_model: 'Draft image parsing model',
	teacher_chat_model: 'Model the teacher picked'
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
