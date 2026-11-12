<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');
</script>

<div class="mx-auto mb-2 w-full max-w-[58rem] px-2">
	<p
		class="rounded-xl bg-[#F7F3EA] px-3 py-2 text-left text-xs leading-5 text-[#20406A] dark:bg-gray-800 dark:text-gray-200"
	>
		{$i18n.t('This conversation does not count toward coursework. Complete assignments in')}
		<a
			class="font-medium underline underline-offset-2 focus-visible:outline focus-visible:outline-2"
			href="/me/writing">{$i18n.t('My Assignments')}</a
		>{$i18n.t('Free chat notice punctuation')}
	</p>
</div>
