import { afterEach, describe, expect, test } from 'vitest';
import i18next from 'i18next';

import { formatDateTimeInput, formatEpoch, resolveErrorMessage } from './education';

// 2026-09-10 23:59 UTC
const DUE_AT = Math.floor(Date.UTC(2026, 8, 10, 23, 59) / 1000);

const withLanguage = (language: string, run: () => void) => {
	(i18next as { language?: string }).language = language;
	run();
};

afterEach(() => {
	(i18next as { language?: string }).language = undefined;
});

describe('date formatting follows the UI language', () => {
	test('renders the same instant differently per interface language', () => {
		let zh = '';
		let en = '';
		withLanguage('zh-CN', () => (zh = formatEpoch(DUE_AT)));
		withLanguage('en-US', () => (en = formatEpoch(DUE_AT)));

		expect(zh).toContain('2026');
		expect(en).toContain('2026');
		expect(zh).not.toBe(en);
	});

	test('echoes a datetime-local value, and stays empty for an unusable one', () => {
		withLanguage('zh-CN', () => {
			expect(formatDateTimeInput('2026-09-10T23:59')).toContain('2026');
			expect(formatDateTimeInput('')).toBe('');
			expect(formatDateTimeInput('not-a-date')).toBe('');
		});
	});
});

describe('backend error details', () => {
	const t = (key: string) => (key === 'Assignment not found' ? '作业不存在' : key);

	test('translates a plain detail string', () => {
		expect(resolveErrorMessage({ detail: 'Assignment not found' }, t)).toBe('作业不存在');
	});

	test('reaches into a structured detail payload', () => {
		const error = {
			detail: { code: 'ASSIGNMENT_WORKSPACE_CORRUPTED', detail: 'Assignment not found' }
		};
		expect(resolveErrorMessage(error, t)).toBe('作业不存在');
	});

	test('falls back to the raw error when there is no detail', () => {
		expect(resolveErrorMessage(new Error('boom'), t)).toBe('Error: boom');
		expect(resolveErrorMessage('boom', t)).toBe('boom');
	});
});
