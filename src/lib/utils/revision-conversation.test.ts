import { expect, test } from 'vitest';
import type { RevisionReading } from '$lib/apis/education';
import {
	revisionTimeline,
	lastReadDraft,
	hasDraftChanges,
	revisionReviewPrompt
} from './revision-conversation';
import { mergeReadingHistory } from './revision-conversation';
const reading = (id: string, time: number, text: string, status = 'ready') =>
	({ id, created_at: time, source_text: text, status }) as RevisionReading;

test('真实初读消息和阅读证据只展示一次', () => {
	const record = {
		...reading('r', 1, '原稿'),
		context: {
			message_id: 'reading-r',
			chat_id: 'chat',
			teaching_version: 1,
			description_version: 1,
			title: '作业',
			description: ''
		}
	};
	const rows = revisionTimeline([{ id: 'reading-r', timestamp: 1, role: 'assistant' }], [record]);
	expect(rows).toHaveLength(1);
	expect(rows[0].kind).toBe('reading');
	expect(rows[0].key).toBe('message:reading-r');
});

test('刷新阅读历史不会抹掉请求期间新写入的消息', () => {
	const local = {
		currentId: 'new',
		messages: { old: { childrenIds: ['new'] }, new: { content: '刚发出的消息' } }
	};
	const saved = {
		currentId: 'reading',
		messages: { old: { childrenIds: ['reading'] }, reading: { content: '初读意见' } }
	};
	const merged = mergeReadingHistory(local, saved);
	expect(merged.currentId).toBe('new');
	expect(merged.messages.old.childrenIds).toEqual(['reading', 'new']);
	expect(merged.messages.reading.content).toBe('初读意见');
	expect(local.messages.old.childrenIds).toEqual(['new']);
});
test('初读、消息、复看按时间连接，后续反馈不会替换旧消息；刷新排序一致', () => {
	const messages = [
		{ id: 'u1', timestamp: 2 },
		{ id: 'a1', timestamp: 3 },
		{ id: 'u2', timestamp: 5 }
	];
	const records = [reading('first', 1, '初稿'), reading('second', 4, '修改稿')];
	const expected = ['reading:first', 'message:u1', 'message:a1', 'reading:second', 'message:u2'];
	expect(revisionTimeline(messages, records).map((r) => r.key)).toEqual(expected);
	expect(
		revisionTimeline(structuredClone(messages), structuredClone(records)).map((r) => r.key)
	).toEqual(expected);
	expect(revisionTimeline([], records)).toHaveLength(2);
	expect(
		revisionTimeline([{ id: 'same', timestamp: 1 }], records)
			.slice(0, 2)
			.map((r) => r.kind)
	).toEqual(['reading', 'message']);
});
test('只以完成的真实读取快照判定改稿，失败不消除修改，空稿也有意义', () => {
	const records = [reading('r', 1, '初稿')];
	const messages = [
		{
			id: 'a',
			timestamp: 3,
			role: 'assistant',
			content: 'feedback',
			done: true,
			meta: { education_context: { called_at: 3, source_text: '修改稿' } }
		}
	];
	expect(lastReadDraft(messages, records, '基线')).toBe('修改稿');
	expect(lastReadDraft([{ ...messages[0], error: true }], records, '基线')).toBe('初稿');
	expect(lastReadDraft([{ ...messages[0], done: false }], records, '基线')).toBe('初稿');
	expect(lastReadDraft([{ ...messages[0], content: '' }], records, '基线')).toBe('初稿');
	expect(lastReadDraft([], [reading('failed', 4, '失败稿', 'failed')], '基线')).toBe('基线');
	expect(lastReadDraft([], [reading('empty', 5, '')], '基线')).toBe('');
	expect(hasDraftChanges('改稿', '初稿')).toBe(true);
	expect(hasDraftChanges('初稿\r\n', '初稿')).toBe(false);
	expect(revisionReviewPrompt('我的说明', '请看修改')).toBe('我的说明\n\n请看修改');
	expect(revisionReviewPrompt('  ', '请看修改')).toBe('请看修改');
});
