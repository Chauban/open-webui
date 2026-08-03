<script lang="ts">
	import { getContext } from 'svelte';

	// 教学模块统一的加载态：此前有的页面显示文案、有的显示卡片、
	// 有的什么都不渲染（首屏白屏）。
	export let messageKey = 'Loading...';

	const i18n = getContext('i18n');
</script>

<div class="mx-auto max-w-6xl px-4 py-16 text-sm text-gray-500 dark:text-gray-400">
	{$i18n.t(messageKey)}
</div>
