import { expect, test } from 'vitest';
import i18next from 'i18next';
import zh from '$lib/i18n/locales/zh-CN/translation.json';
import en from '$lib/i18n/locales/en-US/translation.json';
import { preparationErrorMessages } from './teaching-preparation-form';

test.each(['zh-CN', 'en-US'])('后端字段校验显示字段名称并翻译业务错误：%s', async (lng) => {
	const i18n = i18next.createInstance();
	await i18n.init({
		lng,
		resources: { 'zh-CN': { translation: zh }, 'en-US': { translation: en } },
		interpolation: { escapeValue: false }
	});
	const messages = preparationErrorMessages(
		{
			detail: [
				{
					loc: ['body', 'payload', 'ai', 'model_id'],
					msg: 'String should have at least 1 character'
				},
				{
					loc: ['body', 'payload', 'assignment', 'score_max'],
					msg: 'Input should be greater than 0'
				},
				{
					loc: ['body', 'payload', 'assignment', 'score_max'],
					msg: 'Input should be a valid integer'
				},
				{
					loc: ['body', 'payload', 'assignment'],
					msg: 'Value error, Rubric maximum scores must add up to assignment maximum score'
				}
			]
		},
		(key, params) => i18n.t(key, params)
	);
	expect(messages).toEqual([
		i18n.t('请检查“{{field}}”的填写内容。', { field: i18n.t('本次作业的辅导模型') }),
		i18n.t('请检查“{{field}}”的填写内容。', { field: i18n.t('Maximum Score') }),
		i18n.t('Rubric maximum scores must add up to assignment maximum score')
	]);
	expect(messages.join()).not.toMatch(/\[object Object\]|model_id|score_max|Value error/);
	expect(
		preparationErrorMessages(
			{
				detail: [
					{
						loc: ['body', 'payload', 'assignment', 'due_at'],
						msg: 'Assignment due time is required.',
						type: 'required_for_publication'
					}
				]
			},
			(key, params) => i18n.t(key, params)
		)
	).toEqual([i18n.t('Assignment due time is required.')]);
});

test('字符串、业务异常与嵌套错误保留可读信息，未知对象不会直接显示', () => {
	const t = (key: string) => key;
	for (const error of [
		new Error('保存冲突'),
		'保存冲突',
		{ detail: '保存冲突' },
		{ detail: { detail: '保存冲突' } },
		{ message: '保存冲突' }
	]) {
		expect(preparationErrorMessages(error, t)).toEqual(['保存冲突']);
	}
	for (const error of [
		{ detail: { code: 'unknown' } },
		{ detail: [null, {}] },
		{ detail: [] },
		null
	]) {
		expect(preparationErrorMessages(error, t)).toEqual(['操作失败，请检查填写内容后重试。']);
	}
});
