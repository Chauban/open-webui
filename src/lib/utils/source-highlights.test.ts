import { describe, expect, test } from 'vitest';

import { buildSourceHighlightedHtml, buildTiptapSnapshotHtml } from './source-highlights';

describe('buildSourceHighlightedHtml', () => {
	test('does not match later segments inside generated mark attributes', () => {
		const html = buildSourceHighlightedHtml({
			text: 'Claude',
			segments: [
				{
					segment_id: 'segment-one',
					segment_text: 'Clau',
					source_type: 'user_typed'
				},
				{
					segment_id: 'segment-two',
					segment_text: 'de',
					source_type: 'user_typed'
				}
			]
		});

		expect(html).toContain('>Clau</mark><mark');
		expect(html).toContain('>de</mark>');
		expect(html).not.toContain('>data-segment-id=');
		expect(html).not.toContain('>class=');
	});

	test('escapes text and uses explicit offsets when available', () => {
		const html = buildSourceHighlightedHtml({
			text: 'A < B\nClaude Claude',
			segments: [
				{
					segment_id: 'second-claude',
					segment_text: 'Claude',
					source_type: 'ai_inserted',
					start_offset: 13,
					end_offset: 19
				}
			],
			activeSegmentId: 'second-claude'
		});

		expect(html).toContain('A &lt; B<br />Claude ');
		expect(html).toContain('data-segment-id="second-claude"');
		expect(html).toContain('ring-2 ring-black/40');
		expect(html).toContain('>Claude</mark>');
	});

	test('renders tiptap json formatting instead of markdown markers', () => {
		const html = buildTiptapSnapshotHtml({
			json: {
				type: 'doc',
				content: [
					{
						type: 'paragraph',
						content: [
							{ type: 'text', text: '不过严格来说，' },
							{
								type: 'text',
								text: '我（Claude）本身并没有“版本号”的概念',
								marks: [{ type: 'bold' }]
							},
							{ type: 'text', text: '——Anthropic发布的是不同的模型系列。' }
						]
					},
					{
						type: 'orderedList',
						content: [
							{
								type: 'listItem',
								content: [
									{
										type: 'paragraph',
										content: [
											{ type: 'text', text: 'Claude 1', marks: [{ type: 'bold' }] },
											{ type: 'text', text: '（2023年初）' }
										]
									}
								]
							}
						]
					}
				]
			},
			fallbackText:
				'不过严格来说，**我（Claude）本身并没有“版本号”的概念**——Anthropic发布的是不同的模型系列。\n\n1. **Claude 1**（2023年初）',
			segments: [
				{
					segment_id: 'bold-segment',
					segment_text: '**我（Claude）本身并没有“版本号”的概念**',
					source_type: 'user_typed'
				}
			]
		});

		expect(html).toContain('<strong>');
		expect(html).toContain('我（Claude）本身并没有“版本号”的概念');
		expect(html).toContain('<ol>');
		expect(html).toContain('<li>');
		expect(html).toContain('data-segment-id="bold-segment"');
		expect(html).not.toContain('**');
	});

	test('matches segments across paragraph breaks when block separators differ', () => {
		// The stored segment_text spans two paragraphs and was captured with the
		// editor's single-\n block separator, but the reconstructed Tiptap text
		// uses its own separators. Matching must ignore whitespace differences.
		const html = buildTiptapSnapshotHtml({
			json: {
				type: 'doc',
				content: [
					{
						type: 'paragraph',
						content: [{ type: 'text', text: '这是一段由 AI 生成并插入的完整文字' }]
					},
					{
						type: 'paragraph',
						content: [{ type: 'text', text: '它跨越了两个自然段落需要被完整高亮显示' }]
					}
				]
			},
			segments: [
				{
					segment_id: 'ai-block',
					segment_text:
						'这是一段由 AI 生成并插入的完整文字\n它跨越了两个自然段落需要被完整高亮显示',
					source_type: 'ai_inserted'
				}
			]
		});

		expect(html).toContain('data-segment-id="ai-block"');
		expect(html).toContain('bg-amber-100');
		// Both paragraphs' contents should be wrapped by a highlight mark.
		expect(html).toContain('这是一段由 AI 生成并插入的完整文字');
		expect(html).toContain('它跨越了两个自然段落需要被完整高亮显示');
	});

	test('matches literal numbered heading text before markdown-stripped fallback', () => {
		const segmentText = 'Intro paragraph\n1. Literal numbered heading\nConclusion paragraph';
		const html = buildTiptapSnapshotHtml({
			json: {
				type: 'doc',
				content: [
					{
						type: 'paragraph',
						content: [{ type: 'text', text: 'Intro paragraph' }]
					},
					{
						type: 'heading',
						attrs: { level: 2 },
						content: [{ type: 'text', text: '1. Literal numbered heading' }]
					},
					{
						type: 'paragraph',
						content: [{ type: 'text', text: 'Conclusion paragraph' }]
					}
				]
			},
			segments: [
				{
					segment_id: 'ai-full',
					segment_text: segmentText,
					source_type: 'ai_inserted',
					start_offset: 0,
					end_offset: segmentText.length
				}
			]
		});

		expect(html.match(/data-segment-id="ai-full"/g)?.length).toBe(3);
		expect(html).toContain('>1. Literal numbered heading</mark>');
	});

	test('uses offsets for repeated manual edits and ignores low-signal typed fragments', () => {
		const repeatedText = '哈哈哈哈';
		const firstPrefix = '如果我知识范围内的红红火火恍恍惚惚';
		const secondPrefix = `${firstPrefix}${repeatedText}哈哈说法：Claude 4\n\n直接问我：`;
		const html = buildTiptapSnapshotHtml({
			json: {
				type: 'doc',
				content: [
					{
						type: 'paragraph',
						content: [{ type: 'text', text: `${secondPrefix}${repeatedText}的是哪个模型` }]
					}
				]
			},
			segments: [
				{ segment_id: 'noise-de', segment_text: 'de', source_type: 'user_typed' },
				{ segment_id: 'noise-h', segment_text: 'h', source_type: 'user_typed' },
				{
					segment_id: 'first-laugh',
					segment_text: repeatedText,
					source_type: 'user_typed',
					start_offset: firstPrefix.length,
					end_offset: firstPrefix.length + repeatedText.length
				},
				{
					segment_id: 'second-laugh',
					segment_text: repeatedText,
					source_type: 'user_typed',
					start_offset: secondPrefix.length,
					end_offset: secondPrefix.length + repeatedText.length
				}
			]
		});

		expect(html).toContain('data-segment-id="first-laugh"');
		expect(html).toContain('data-segment-id="second-laugh"');
		expect(html).not.toContain('data-segment-id="noise-de"');
		expect(html).not.toContain('data-segment-id="noise-h"');
	});

	test('uses distinct colors for external paste and unknown source ranges', () => {
		const html = buildSourceHighlightedHtml({
			text: 'paste?',
			segments: [
				{
					segment_id: 'external',
					segment_text: 'paste',
					source_type: 'external_paste',
					start_offset: 0,
					end_offset: 5
				},
				{
					segment_id: 'unknown',
					segment_text: '?',
					source_type: 'unknown',
					start_offset: 5,
					end_offset: 6
				}
			]
		});

		expect(html).toContain(
			'data-segment-id="external" class="rounded px-1 bg-rose-100 text-rose-950"'
		);
		expect(html).toContain(
			'data-segment-id="unknown" class="rounded px-1 bg-gray-100 text-gray-700"'
		);
	});
});
