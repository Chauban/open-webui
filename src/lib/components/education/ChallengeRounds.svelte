<script lang="ts">
	// 教师端：这一轮提交前的读者试读往来。
	//
	// 提交详情里其它块给的都是量化占比（typed / AI inserted / AI pasted %），教师看完
	// 也不知道该说什么。这一块给的是学生思考过程的直接证据：他被问到什么、怎么答的、
	// 答完之后有没有真的回去改。这才是能拿到课堂上讲的东西。
	import { getContext } from 'svelte';

	import type { ChallengeDetail } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let detail: ChallengeDetail | null = null;
	/** 评分维度 key → 名称，让教师看到质疑打的是哪一项。 */
	export let criteriaLabels: Record<string, string> = {};

	$: session = detail?.session ?? null;
	$: turns = detail?.turns ?? [];
	$: answered = turns.filter((turn) => turn.response_text !== null);
	$: closing = session?.closing_summary_json ?? null;
	$: revision = detail?.revision ?? null;
</script>

{#if session}
	<div>
		<div class="mb-3">
			<div class="text-sm font-semibold text-gray-950 dark:text-gray-100">
				{$i18n.t('Pre-submission Read-through')}
			</div>
			<div class="mt-0.5 text-xs text-gray-400">
				{$i18n.t(
					'An AI reader challenged the draft and the student answered. The reader never writes for the student.'
				)}
			</div>
		</div>

		<div class="rounded-2xl bg-gray-50 px-4 py-4 dark:bg-gray-800">
			<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
				{#if session.status === 'skipped'}
					<span class="font-medium text-amber-600 dark:text-amber-400">
						{$i18n.t('Student skipped the read-through')}
					</span>
				{:else}
					<span class="text-gray-600 dark:text-gray-300">
						{$i18n.t('Answered {{answered}} of {{planned}} rounds', {
							answered: answered.length,
							planned: session.planned_rounds
						})}
					</span>
					{#if revision}
						<!-- 服务端两份快照直接比对得出，不依赖客户端上报，也不受客户端时钟影响。 -->
						<span
							class={revision.revised
								? 'font-medium text-emerald-700 dark:text-emerald-400'
								: 'font-medium text-rose-600 dark:text-rose-400'}
						>
							{revision.revised
								? $i18n.t('Revised the draft afterwards ({{chars}} chars changed)', {
										chars: revision.changed_chars
									})
								: $i18n.t('Did not revise the draft afterwards')}
						</span>
					{/if}
				{/if}
			</div>

			{#if session.status !== 'skipped'}
				<div class="mt-4 space-y-4">
					{#each turns as turn (turn.id)}
						<div>
							<div class="text-xs text-gray-400">
								{$i18n.t('Round {{current}} of {{total}}', {
									current: turn.turn_no,
									total: session.planned_rounds
								})}
								{#if criteriaLabels[turn.focus_key]}
									· {criteriaLabels[turn.focus_key]}
								{/if}
							</div>
							<p
								class="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-gray-700 dark:text-gray-200"
							>
								{turn.challenge_text}
							</p>
							{#if turn.response_text}
								<p
									class="mt-2 whitespace-pre-wrap border-l-2 border-gray-300 pl-3 text-sm leading-relaxed text-gray-900 dark:border-gray-600 dark:text-gray-100"
								>
									{turn.response_text}
								</p>
							{:else}
								<p class="mt-2 border-l-2 border-gray-200 pl-3 text-sm text-gray-400 dark:border-gray-700">
									{$i18n.t('No answer to this round')}
								</p>
							{/if}
						</div>
					{/each}
				</div>

				{#if closing && (closing.stood.length > 0 || closing.unresolved.length > 0)}
					<div class="mt-4 border-t border-gray-200 pt-3 dark:border-gray-700">
						<div class="text-xs font-medium text-gray-600 dark:text-gray-300">
							{$i18n.t('What the reader concluded')}
						</div>
						<div class="mt-2 space-y-2">
							{#if closing.stood.length > 0}
								<div class="text-xs text-gray-500 dark:text-gray-400">
									<span class="font-medium">{$i18n.t('You held these up')}</span>
									<ul class="mt-1 space-y-0.5">
										{#each closing.stood as item}
											<li class="flex gap-1.5">
												<span aria-hidden="true">·</span><span>{item}</span>
											</li>
										{/each}
									</ul>
								</div>
							{/if}
							{#if closing.unresolved.length > 0}
								<div class="text-xs text-gray-500 dark:text-gray-400">
									<span class="font-medium">{$i18n.t('These still need work')}</span>
									<ul class="mt-1 space-y-0.5">
										{#each closing.unresolved as item}
											<li class="flex gap-1.5">
												<span aria-hidden="true">·</span><span>{item}</span>
											</li>
										{/each}
									</ul>
								</div>
							{/if}
						</div>
					</div>
				{/if}
			{/if}

			<!--
				信任层级（PRD 12.9.7）：质疑文本与回合数是服务端生成的权威数据；
				学生回应是他自己敲的字，可信度等同 typed 正文；「有没有回去改」由两份
				服务端快照比对得出，同样不依赖客户端上报。所以这一块不挂
				EduEvidenceDisclaimer——那句话说的是客户端上报的口径，挂在这里反而误导。
			-->
			<div class="mt-3 text-xs text-gray-400">
				{$i18n.t(
					'Questions and rounds are generated server-side; the answers are the student’s own words.'
				)}
			</div>
		</div>
	</div>
{/if}
