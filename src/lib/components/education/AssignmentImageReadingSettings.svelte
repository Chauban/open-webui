<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';

	export let enabled = false;
	export let platformModel: import('$lib/apis/education').ImageParsingModelView | null = null;
	const i18n = getContext<Writable<I18n>>('i18n');
</script>

<div class="space-y-2">
	<label class="flex cursor-pointer items-center gap-3 text-sm font-medium">
		<input type="checkbox" role="switch" bind:checked={enabled} class="h-4 w-4 rounded" />
		{$i18n.t('AI image reading for this assignment')}
	</label>
	<p class="break-words text-xs text-gray-600 dark:text-gray-300">
		{$i18n.t('Image reading uses the platform model: {{model}}', {
			model: platformModel?.name ?? $i18n.t('Not configured')
		})}
	</p>
	<p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
		{$i18n.t(
			'Off by default. When enabled, AI can read document images, scanned pages and uploaded photos. Recognition may contain errors or omissions; check the original when needed.'
		)}
	</p>
	<p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
		{$i18n.t(
			'When off, document text and native notes remain available; original images are kept for people to view, and image transcriptions are excluded from new AI attachments. Confirmed writing and conversation history are retained.'
		)}
	</p>
	{#if enabled && !platformModel?.available}
		<p role="status" class="text-xs text-amber-700 dark:text-amber-300">
			{$i18n.t(
				platformModel
					? 'The configured image-to-text model is unavailable. Ask an administrator to check it.'
					: 'An administrator must configure an image parsing model before image reading can work.'
			)}
		</p>
	{/if}
</div>
