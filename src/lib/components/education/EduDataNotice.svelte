<script lang="ts">
	import { getContext } from 'svelte';
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte';

	// 给学生看的采集告知。刻意只说「记录了什么、谁能看到」,不含任何阈值、指标名
	// 或判定规则 —— 那些是 index_formula 的内容,只发给教师端。学生知道过程被记录
	// 不会带来新的规避手段(他本来就在这个界面里写字、聊天),但「过程被看见」这个
	// 教学机制成立的前提正是学生知道;不告知的话采到的就不是被看见后的写作行为。
	const i18n = getContext('i18n');

	export let scope: 'classroom' | 'assignment' | 'personal' = 'assignment';
	let className = '';
	export { className as class };
</script>

<div
	class="flex items-start gap-1.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400 {className}"
>
	<div class="mt-0.5 shrink-0">
		<InfoCircle className="size-3.5" />
	</div>
	<div class="space-y-1">
		<p>
			{$i18n.t(
				'This writing space records how you write: every edit, every saved version, your conversations with the AI, and where each passage came from.'
			)}
		</p>
		{#if scope === 'personal'}
			<p>
				{$i18n.t('This is your personal writing space. Teachers cannot see anything in it.')}
			</p>
		{:else}
			<p>
				{$i18n.t(
					'For assignment writing, your teacher can see these records and uses them to understand your process and give feedback.'
				)}
			</p>
			<p>{$i18n.t('Your personal writing space stays private — teachers cannot see it.')}</p>
		{/if}
	</div>
</div>
