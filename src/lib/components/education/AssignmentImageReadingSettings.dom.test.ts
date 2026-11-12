// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test } from 'vitest';
import AssignmentImageReadingSettings from './AssignmentImageReadingSettings.svelte';

afterEach(cleanup);
const context = new Map([
	[
		'i18n',
		readable({
			t: (key: string, values: Record<string, string> = {}) =>
				Object.entries(values).reduce(
					(text, [name, value]) => text.replace(`{{${name}}}`, value),
					key
				)
		})
	]
]);

test('识图默认关闭，老师可开关，缺少平台模型时清楚提示', async () => {
	render(AssignmentImageReadingSettings, { props: { platformModel: null }, context });
	const toggle = screen.getByRole('switch', {
		name: 'AI 读取参考图片'
	}) as HTMLInputElement;
	expect(toggle.checked).toBe(false);
	await fireEvent.click(toggle);
	expect(toggle.checked).toBe(true);
	expect(screen.getByRole('status').textContent).toContain('参考图片识读模型尚未配置');
	await fireEvent.click(toggle);
	expect(toggle.checked).toBe(false);
	expect(screen.queryByRole('status')).toBeNull();
});

test('回显已开启的作业，并提示识别文字可能错漏', () => {
	render(AssignmentImageReadingSettings, {
		props: {
			enabled: true,
			platformModel: { id: 'platform-vision', name: '平台识图 A', available: true }
		},
		context
	});
	expect(
		(screen.getByRole('switch', { name: 'AI 读取参考图片' }) as HTMLInputElement).checked
	).toBe(true);
	expect(screen.getByText(/识别结果请对照原图核对/)).toBeTruthy();
	expect(screen.queryByRole('status')).toBeNull();
	expect(screen.getByText('参考图片识读模型：平台识图 A')).toBeTruthy();
	expect(screen.queryByRole('combobox')).toBeNull();
});

test('展示平台已配置但不可用的模型，不显示作业辅导模型作为替代', () => {
	render(AssignmentImageReadingSettings, {
		props: { enabled: true, platformModel: { id: 'gone', name: '原识图模型', available: false } },
		context
	});
	expect(screen.getByText('参考图片识读模型：原识图模型')).toBeTruthy();
	expect(screen.getByRole('status').textContent).toContain('参考图片识读模型尚未配置或不可用');
});

test('教师可以只开启照片转正文，参考图片识读保持关闭', async () => {
	render(AssignmentImageReadingSettings, {
		props: {
			photoTranscriptionModel: { id: 'photo', name: '手写转录模型', available: true },
			platformModel: null
		},
		context
	});
	const photo = screen.getByRole('switch', { name: '照片转正文' }) as HTMLInputElement;
	const reference = screen.getByRole('switch', { name: 'AI 读取参考图片' }) as HTMLInputElement;
	await fireEvent.click(photo);
	expect(photo.checked).toBe(true);
	expect(reference.checked).toBe(false);
	expect(screen.queryByRole('status')).toBeNull();
});
