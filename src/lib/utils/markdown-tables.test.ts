import { expect, test } from 'vitest';
import { marked } from 'marked';
import { normalizeMarkdownTables } from './markdown-tables';

test('missing separator in model feedback becomes a real table without changing cells', () => {
	const original =
		'一、诊断表格\n| 要素 | 当前表现 | 评分 |\n| 观点 | 判断明确 | 合格 |\n| 理由 | 理由错位 | 不合格 |\n\n二、致命漏洞';
	const tokens = marked.lexer(normalizeMarkdownTables(original));
	const table = tokens.find((token) => token.type === 'table');
	expect(table?.type).toBe('table');
	if (table?.type === 'table')
		expect(table.rows.map((row) => row.map((cell) => cell.text))).toEqual([
			['观点', '判断明确', '合格'],
			['理由', '理由错位', '不合格']
		]);
	expect(normalizeMarkdownTables(normalizeMarkdownTables(original))).toBe(
		normalizeMarkdownTables(original)
	);
});

test('valid tables, fenced code and ambiguous pipe text remain unchanged', () => {
	for (const text of [
		'| A | B |\n| --- | --- |\n| a | b |',
		'```md\n| A | B |\n| a | b |\n| c | d |\n```',
		'~~~\n| A | B |\n| a | b |\n| c | d |\n~~~',
		'| A | B |\n| a | b |',
		'    | A | B |\n    | a | b |\n    | c | d |',
		'| A | B |\n| a | b | c |\n| d | e |'
	])
		expect(normalizeMarkdownTables(text)).toBe(text);
});

test('escaped and inline-code pipes do not add columns', () => {
	const text = '| A | B |\n| `x|y` | z |\n| x\\|y | z |';
	expect(normalizeMarkdownTables(text)).toContain('| --- | --- |');
});
