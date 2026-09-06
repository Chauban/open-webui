<script lang="ts">
	// 一轮一轮的质疑往来，师生两端共用。
	//
	// 学生端（写作面板的收尾清单里）用它回看自己被问了什么、当时怎么答的——真正要
	// 拿这份记录去改文章的是学生，教师端反而先有了完整记录，方向本来是反的。
	// 教师端（提交详情）多传一个 revisionByTurn，就在每轮下面并排出「被质疑的原文 /
	// 最终稿的样子」两栏。
	//
	// 结论一律由教师自己下：这里只把证据摆在一起，不出现「糊弄」「敷衍」这类判定词。
	import { getContext } from 'svelte';

	import type { ChallengeRevisionTurn, ChallengeTurn } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let turns: ChallengeTurn[] = [];
	export let plannedRounds = 0;
	/** 评分维度 key → 名称，让读的人看到质疑打的是哪一项。 */
	export let criteriaLabels: Record<string, string> = {};
	/** 教师端才传：轮次 → 该处正文在最终稿里的变化。学生端不传。 */
	export let revisionByTurn: Record<number, ChallengeRevisionTurn> = {};
</script>

<div class="space-y-4">
	{#each turns as turn (turn.id)}
		{@const revision = revisionByTurn[turn.turn_no] ?? null}
		<div>
			<div class="text-xs text-gray-400">
				{$i18n.t('Round {{current}} of {{total}}', {
					current: turn.turn_no,
					total: plannedRounds
				})}
				{#if criteriaLabels[turn.focus_key]}
					· {criteriaLabels[turn.focus_key]}
				{/if}
			</div>

			{#if turn.quoted_span}
				<p
					class="mt-1.5 whitespace-pre-wrap border-l-2 border-amber-400 bg-amber-50/60 py-1 pl-3 text-sm leading-relaxed text-gray-700 dark:border-amber-500/70 dark:bg-amber-950/20 dark:text-gray-200"
				>
					{turn.quoted_span}
				</p>
			{/if}

			<p class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700 dark:text-gray-200">
				{turn.challenge_text}
			</p>

			{#if turn.response_text}
				<p
					class="mt-2 whitespace-pre-wrap border-l-2 border-gray-300 pl-3 text-sm leading-relaxed text-gray-900 dark:border-gray-600 dark:text-gray-100"
				>
					{turn.response_text}
				</p>
			{:else}
				<p
					class="mt-2 border-l-2 border-gray-200 pl-3 text-sm text-gray-400 dark:border-gray-700"
				>
					{$i18n.t('No answer to this round')}
				</p>
			{/if}

			{#if revision}
				<!--
					第三栏：被质疑的这处在最终稿里成了什么样。判的是位置不是字数——
					只要学生没动这句话，片段就会原样出现在最终正文里。
				-->
				<div class="mt-2.5 rounded-xl bg-white px-3 py-2 dark:bg-gray-900">
					{#if !revision.changed}
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('This sentence is unchanged in the submitted draft.')}
						</div>
					{:else if revision.final_span}
						<div class="text-xs font-medium text-gray-600 dark:text-gray-300">
							{$i18n.t('In the submitted draft')}
						</div>
						<p
							class="mt-1 whitespace-pre-wrap border-l-2 border-emerald-400 pl-3 text-sm leading-relaxed text-gray-800 dark:border-emerald-500/70 dark:text-gray-100"
						>
							{revision.final_span}
						</p>
					{:else}
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('This sentence is gone from the submitted draft.')}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/each}
</div>
