import { expect, test } from 'vitest';
import type { RevisionReading } from '$lib/apis/education';
import {
	teacherConversationEvents,
	teacherModelUsage,
	teacherPromptLabel
} from './teacher-writing-process';
const t = (s: string) => s;
const reading = {
	id: 'r1',
	purpose: 'first_read',
	created_at: 1,
	source_text: '初稿',
	thinking: 'low',
	model_id: 'reader-model',
	context: { description_version: 1, teaching_version: 1 },
	feedback: {
		understanding: '我读到的判断',
		strength: null,
		focus: [{ quote: '原句', feedback: '证据问题' }],
		overview: '概览'
	}
} as RevisionReading;

test('真实阅读消息在教师过程记录中不与阅读证据重复', () => {
	const linked = {
		...reading,
		context: { ...reading.context, chat_id: 'chat', message_id: 'reading-r1' }
	};
	const events = teacherConversationEvents(
		[{ id: 'chat-reading-r1', role: 'assistant', content: '已入历史的初读意见', created_at: 1 }],
		[linked],
		[],
		t
	);
	expect(events).toHaveLength(1);
	expect(events[0].label).toBe('已入历史的初读意见');
	expect(events[0].ai_step).toBe('first_read');
});
test('初读与后续交流合在同一时间线，冻结快照优先且不使用当前正文', () => {
	const prompts = [
		{ id: 'u', role: 'user', content: '我的说明', created_at: 2 },
		{
			id: 'a',
			role: 'assistant',
			content: '修改反馈',
			created_at: 3,
			education_context: { source_text: '不能覆盖冻结稿' }
		}
	];
	const events = teacherConversationEvents(
		prompts,
		[reading],
		[{ message_id: 'a', source_text: '本轮冻结的改稿', called_at: 3 }],
		t
	);
	expect(events.map((e) => e.key)).toEqual(['reading:r1', 'prompt:u', 'prompt:a']);
	expect(events[0].source?.text).toBe('初稿');
	expect(events[2].source?.text).toBe('本轮冻结的改稿');
	expect(events[0].label).toContain('证据问题');
	expect(events[0].label).toContain('概览');
	expect(events[1].source).toBeNull();
});

test('教师过程记录保留按提示词生成的连续回复', () => {
	const events = teacherConversationEvents(
		[],
		[
			{
				...reading,
				feedback: { understanding: '', strength: null, focus: [], overview: '完整回复' }
			}
		],
		[],
		t
	);
	expect(events[0].label).toBe('完整回复');
});

test('逐次模型切换与平台阅读分开汇总，缺失模型不按其他回复猜补', () => {
	const events = teacherConversationEvents(
		[
			{ id: 'u', role: 'user', content: '问题', model_id: 'not-an-ai-reply' },
			{
				id: 'a1',
				role: 'assistant',
				content: '回复1',
				model_id: 'deepseek-flash',
				thinking_level: 'medium'
			},
			{
				id: 'a2',
				role: 'assistant',
				content: '回复2',
				model_id: 'other-model',
				thinking_level: 'off'
			},
			{ id: 'a3', role: 'assistant', content: '回复3', model_id: 'deepseek-flash' },
			{ id: 'a4', role: 'assistant', content: '未记录模型的回复' }
		],
		[reading],
		[],
		t
	);
	expect(events.find((e) => e.key === 'prompt:a1')).toMatchObject({
		model_id: 'deepseek-flash',
		thinking_level: 'medium',
		ai_step: 'coaching_chat'
	});
	expect(events.find((e) => e.key === 'prompt:a2')).toMatchObject({
		model_id: 'other-model',
		thinking_level: 'off'
	});
	expect(events.find((e) => e.key === 'reading:r1')).toMatchObject({
		model_id: 'reader-model',
		ai_step: 'first_read'
	});
	expect(teacherModelUsage(events, [{ step: 'reader_check', model_id: 'check-model' }])).toEqual([
		{ step: 'coaching_chat', models: ['deepseek-flash', 'other-model', null] },
		{ step: 'first_read', models: ['reader-model'] },
		{ step: 'reader_check', models: ['check-model'] }
	]);
});
test('区分快捷请求、自己输入的说明和未记录具体动作的预设消息', () => {
	expect(
		teacherPromptLabel(
			{ id: 'u', role: 'user', content: '', revision_review_requested: true, auto_started: true },
			t
		)
	).toBe('学生请求查看修改（快捷按钮）');
	expect(
		teacherPromptLabel(
			{ id: 'u', role: 'user', content: '说明', revision_review_requested: true },
			t
		)
	).toBe('学生说明并请求查看修改');
	expect(teacherPromptLabel({ id: 'u', role: 'user', content: '', auto_started: true }, t)).toBe(
		'平台预设消息'
	);
	expect(teacherPromptLabel({ id: 'u', role: 'user', content: '问题' }, t)).toBe('Student');
});
test('空稿可查看，未记录的稿件不补造；同秒初读在问题前', () => {
	const events = teacherConversationEvents(
		[
			{ id: 'a', role: 'assistant', content: '反馈', created_at: 1 },
			{ id: 'b', role: 'assistant', content: '另一条', created_at: 2 }
		],
		[reading],
		[{ message_id: 'b', source_text: '' }],
		t
	);
	expect(events[0].key).toBe('reading:r1');
	expect(events[1].source).toBeNull();
	expect(events[2].source?.text).toBe('');
});
