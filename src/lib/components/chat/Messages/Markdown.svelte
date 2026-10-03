<script context="module">
	import { marked } from 'marked';

	import markedExtension from '$lib/utils/marked/extension';
	import markedKatexExtension from '$lib/utils/marked/katex-extension';
	import { disableSingleTilde } from '$lib/utils/marked/strikethrough-extension';
	import { mentionExtension } from '$lib/utils/marked/mention-extension';
	import colonFenceExtension from '$lib/utils/marked/colon-fence-extension';
	import footnoteExtension from '$lib/utils/marked/footnote-extension';
	import citationExtension from '$lib/utils/marked/citation-extension';

	const options = {
		throwOnError: false
	};

	marked.use(markedKatexExtension(options));
	marked.use(markedExtension(options));
	marked.use(citationExtension(options));
	marked.use(footnoteExtension(options));
	marked.use(colonFenceExtension(options));
	marked.use(disableSingleTilde);
	marked.use({
		extensions: [
			mentionExtension({ triggerChar: '@' }),
			mentionExtension({ triggerChar: '#' }),
			mentionExtension({ triggerChar: '$' })
		]
	});
</script>

<script>
	import { onDestroy } from 'svelte';
	import { replaceTokens, processResponseContent } from '$lib/utils';
	import { user } from '$lib/stores';

	import MarkdownTokens from './Markdown/MarkdownTokens.svelte';

	export let id = '';
	export let chatId = '';
	export let messageId = '';
	export let content;
	export let done = true;
	export let model = null;
	export let save = false;
	export let preview = false;
	export let compactPreview = false;

	export let paragraphTag = 'p';
	export let editCodeBlock = true;
	export let topPadding = false;
	export let allowEmbeds = true;

	export let sourceIds = [];

	export let onSave = () => {};
	export let onUpdate = () => {};

	export let onPreview = () => {};

	export let onSourceClick = () => {};
	export let onTaskClick = () => {};
	export let onToolCallResolved = () => {};

	let tokens = [];
	let pendingUpdate = null;
	let lastContent = '';
	let lastParsedContent = '';

	const parseTokens = () => {
		if (content === lastContent) return;
		lastContent = content;

		const processed = replaceTokens(processResponseContent(content), model?.name, $user?.name);
		if (processed === lastParsedContent) return;
		lastParsedContent = processed;

		tokens = marked.lexer(processed);
	};

	// done 也要作为依赖:最后一段内容常在 done 还为假时到达、排进动画帧,done 随后变真时
	// 内容没变,只依赖 content 就不会再跑。后台标签页里浏览器暂停动画帧,那一帧永远不来,
	// 回复就一直是空白(学生等第一次通读时切去别的页面就会碰上)。不绘制时直接解析。
	const updateHandler = (content, done) => {
		if (content) {
			if (done || document.hidden) {
				cancelAnimationFrame(pendingUpdate);
				pendingUpdate = null;
				parseTokens();
			} else if (!pendingUpdate) {
				pendingUpdate = requestAnimationFrame(() => {
					pendingUpdate = null;
					parseTokens();
				});
			}
		}
	};

	$: updateHandler(content, done);

	// Throttle parsing to once per animation frame while streaming
	onDestroy(() => {
		cancelAnimationFrame(pendingUpdate);
	});
</script>

{#key id}
	<MarkdownTokens
		{tokens}
		{id}
		{chatId}
		{messageId}
		{done}
		{save}
		{preview}
		{compactPreview}
		{paragraphTag}
		{editCodeBlock}
		{sourceIds}
		{topPadding}
		{allowEmbeds}
		{onTaskClick}
		{onSourceClick}
		{onToolCallResolved}
		{onSave}
		{onUpdate}
		{onPreview}
	/>
{/key}
