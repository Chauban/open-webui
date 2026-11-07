<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte';

	export let content: unknown = '';

	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import { readableChatError } from '$lib/utils/chat-error';
	const i18n = getContext<Writable<I18nType>>('i18n');
	$: message = readableChatError(content, $i18n.t);
</script>

<div
	class="my-1.5 flex w-full items-start gap-2 rounded-2xl bg-black/[0.03] px-3 py-2 text-gray-500 dark:bg-white/[0.04] dark:text-gray-400"
>
	<Info className="mt-0.5 size-4 shrink-0 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />

	<div class="min-w-0 break-words text-[0.8125rem] leading-5">
		{message}
	</div>
</div>
