import { Marked } from 'marked';

import markedExtension from '$lib/utils/marked/extension';
import markedKatexExtension from '$lib/utils/marked/katex-extension';
import { disableSingleTilde } from '$lib/utils/marked/strikethrough-extension';
import { mentionExtension } from '$lib/utils/marked/mention-extension';
import footnoteExtension from '$lib/utils/marked/footnote-extension';
import citationExtension from '$lib/utils/marked/citation-extension';

type PrepareAssistantContentOptions = {
	content: string;
	modelName?: string;
	userName?: string;
};

const markedForWriting = new Marked({
	breaks: true
});

markedForWriting.use(markedKatexExtension({ throwOnError: false }));
markedForWriting.use(markedExtension({ throwOnError: false }));
markedForWriting.use(citationExtension({ throwOnError: false }));
markedForWriting.use(footnoteExtension({ throwOnError: false }));
markedForWriting.use(disableSingleTilde);
markedForWriting.use({
	extensions: [
		mentionExtension({ triggerChar: '@' }),
		mentionExtension({ triggerChar: '#' }),
		mentionExtension({ triggerChar: '$' })
	]
});

const replaceOutsideCode = (content: string, replacer: (str: string) => string) => {
	return content
		.split(/(```[\s\S]*?```|`[\s\S]*?`)/)
		.map((segment) => (segment.startsWith('```') || segment.startsWith('`') ? segment : replacer(segment)))
		.join('');
};

const removeDetails = (content: string) => {
	return replaceOutsideCode((content ?? '').toString(), (segment) =>
		segment
			.replace(/<details[^>]*>.*?<\/details>/gis, '')
			.replace(/<think>.*?<\/think>/gis, '')
			.replace(/<thinking>.*?<\/thinking>/gis, '')
			.replace(/<reasoning>.*?<\/reasoning>/gis, '')
	);
};

const replaceTokens = (content: string, modelName = '', userName = '') => {
	return replaceOutsideCode(content, (segment) =>
		segment
			.replace(/{{char}}/gi, modelName)
			.replace(/{{user}}/gi, userName)
	);
};

const htmlToVisibleText = (html: string) => {
	return html
		.replace(/<br\s*\/?>/gi, '\n')
		.replace(/<\/(p|div|h[1-6]|li|blockquote|pre|tr)>/gi, '\n')
		.replace(/<\/(ul|ol|table)>/gi, '\n')
		.replace(/<[^>]+>/g, '')
		.replace(/&nbsp;/g, ' ')
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/&#39;/g, "'")
		.split('\n')
		.map((line) => line.trim())
		.filter(Boolean)
		.join('\n');
};

export const prepareAssistantContentForWriting = ({
	content,
	modelName = '',
	userName = ''
}: PrepareAssistantContentOptions) => {
	const visibleMarkdown = replaceTokens(removeDetails(`${content ?? ''}`).trim(), modelName, userName);
	const html = markedForWriting.parse(visibleMarkdown) as string;

	return {
		html,
		text: htmlToVisibleText(html)
	};
};
