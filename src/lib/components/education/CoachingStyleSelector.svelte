<script lang="ts">
	import { getContext } from 'svelte';

	import { eduSegmentClass } from '$lib/components/education/styles';
	import type { CoachingStyle } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let value: CoachingStyle = 'balanced';
	export let disabled = false;

	// 档位在这里只是标签；每档实际的提示词由管理员在管理面板里维护。
	const styles: Array<{ key: CoachingStyle; title: string; hint: string }> = [
		{
			key: 'socratic',
			title: 'Socratic',
			hint: 'The AI keeps asking until the student has decided; it never hands over ready-to-paste prose.'
		},
		{
			key: 'balanced',
			title: 'Balanced',
			hint: 'The AI clarifies intent first, then coaches with outlines, examples and demonstrated edits.'
		},
		{
			key: 'hands_off',
			title: 'Hands-off',
			hint: 'The AI helps as asked, with one round of clarification so the student does not write off-topic.'
		}
	];

	$: activeHint = styles.find((style) => style.key === value)?.hint ?? '';
</script>

<div>
	<div class="mb-2 text-sm font-semibold">{$i18n.t('AI Coaching Style')}</div>
	<div class="flex flex-wrap gap-2">
		{#each styles as style}
			<button
				type="button"
				class={eduSegmentClass(value === style.key)}
				{disabled}
				on:click={() => (value = style.key)}
			>
				{$i18n.t(style.title)}
			</button>
		{/each}
	</div>
	<div class="mt-2 text-xs text-gray-400">{$i18n.t(activeHint)}</div>
</div>
