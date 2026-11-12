<script lang="ts">
	import { getContext } from 'svelte';
	import type { Readable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import type { SubmissionTiming } from '$lib/apis/education';
	import { formatEpoch } from '$lib/utils/education';
	import EduBadge from './EduBadge.svelte';

	const i18n = getContext<Readable<I18n>>('i18n');
	export let timing: SubmissionTiming | null | undefined;
</script>

{#if timing?.is_late}
	<EduBadge
		soft
		tone="rose"
		title={timing.effective_due_at
			? `${$i18n.t('Deadline at submission')}: ${formatEpoch(timing.effective_due_at)}`
			: undefined}
	>
		{$i18n.t('Late submission')}
	</EduBadge>
{/if}
