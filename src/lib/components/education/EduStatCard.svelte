<script lang="ts">
	import { getContext } from 'svelte';
	import EduCard from './EduCard.svelte';

	// 看板统计卡：小标题 + 大数字。此前在 4 个页面里逐字重复，
	// 每处自己拼 uppercase tracking 与配色。
	export let label = '';
	export let value: string | number = 0;
	// 口径说明：数字本身分不清「份/人次/个」，统计卡下方补一行小字。
	export let hint = '';
	export let tone: 'default' | 'rose' | 'amber' | 'sky' = 'default';
	// 给了 href 整张卡就是入口:「待批改 7」应该一点就进到那 7 份,而不是只能看。
	export let href = '';

	const i18n = getContext('i18n');

	const LABEL_TONES = {
		default: 'text-gray-500 dark:text-gray-400',
		rose: 'text-rose-600 dark:text-rose-400',
		amber: 'text-amber-600 dark:text-amber-400',
		sky: 'text-sky-600 dark:text-sky-400'
	};
	const VALUE_TONES = {
		default: '',
		rose: 'text-rose-700 dark:text-rose-300',
		amber: 'text-amber-700 dark:text-amber-300',
		sky: 'text-sky-700 dark:text-sky-300'
	};
</script>

<!-- 统计卡的底色跟随语义色，default 用普通白卡。 -->
{#if href}
	<a {href} class="group block rounded-3xl transition hover:-translate-y-px">
		<EduCard {tone} class="h-full transition group-hover:border-gray-400 dark:group-hover:border-gray-600">
			<div class="flex items-center justify-between text-xs uppercase tracking-[0.16em] {LABEL_TONES[tone]}">
				<span>{$i18n.t(label)}</span>
				<span aria-hidden="true" class="opacity-0 transition group-hover:opacity-100">&rarr;</span>
			</div>
			<div class="mt-2 text-3xl font-semibold {VALUE_TONES[tone]}">{value}</div>
			{#if hint}
				<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">{$i18n.t(hint)}</div>
			{/if}
		</EduCard>
	</a>
{:else}
	<EduCard {tone}>
		<div class="text-xs uppercase tracking-[0.16em] {LABEL_TONES[tone]}">{$i18n.t(label)}</div>
		<div class="mt-2 text-3xl font-semibold {VALUE_TONES[tone]}">{value}</div>
		{#if hint}
			<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">{$i18n.t(hint)}</div>
		{/if}
	</EduCard>
{/if}
