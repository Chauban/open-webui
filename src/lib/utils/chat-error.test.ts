import { expect, test } from 'vitest';
import { readableChatError } from './chat-error';
import { appendDiscussionPrompt } from './revision-conversation';
const t = (key: string) => key;
test('网关 HTML 在即时错误、嵌套模型错误和已保存错误中都变成可重试提示', () => {
	const html = '<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>';
	for (const error of [html, { detail: html }, { error: { message: html } }, { content: html }]) {
		expect(readableChatError(error, t)).toBe(
			'The connection was interrupted. Please retry your message in a moment.'
		);
	}
	expect(readableChatError({ detail: 'Access prohibited' }, t)).toBe('Access prohibited');
	expect(readableChatError(null, t)).toBe('Unable to get a reply. Please try again.');
});
test('讨论入口保留未发送的问题，空入口仅聚焦，不塞含糊的自动问题', () => {
	expect(appendDiscussionPrompt('我的问题', '')).toBe('我的问题');
	expect(appendDiscussionPrompt('我的问题', '引用原文')).toBe('我的问题\n\n引用原文');
	expect(appendDiscussionPrompt('', '引用原文')).toBe('引用原文');
});
