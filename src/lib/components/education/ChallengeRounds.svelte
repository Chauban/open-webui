<script lang="ts">
	// 教师端：这一轮提交前的读者试读往来。
	//
	// 提交详情里其它块给的都是量化占比（typed / AI inserted / AI pasted %），教师看完
	// 也不知道该说什么。这一块给的是学生思考过程的直接证据：他被问到哪一句、怎么答的、
	// 那一句最后有没有动。这才是能拿到课堂上讲的东西。
	//
	// 判的是位置不是字数。老口径用全文改动量加最小字符阈值，方向是反的：被质疑之后
	// 最理想的修改往往最小（删掉一个站不住的例子、把「所有人都认为」限缩为「我采访的
	// 12 个同学里有 9 个」），那些都过不了阈值；而在结尾补一句无关的套话稳过。
	//
	// 这里只呈现「那处变没变」，不判「改得对不对、是不是真回应了质疑」——后者要不要
	// 交给 AI 判是个待定问题（PRD 16.4），本期由教师看这三栏自己下结论。
	import { getContext } from 'svelte';

	import ChallengeTranscript from '$lib/components/education/ChallengeTranscript.svelte';
	import type { ChallengeDetail, ChallengeRevisionTurn } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let detail: ChallengeDetail | null = null;
	/** 评分维度 key → 名称，让教师看到质疑打的是哪一项。 */
	export let criteriaLabels: Record<string, string> = {};

	$: session = detail?.session ?? null;
	$: turns = detail?.turns ?? [];
	$: answered = turns.filter((turn) => turn.response_text !== null);
	$: closing = session?.closing_summary_json ?? null;
	$: revision = detail?.revision ?? null;
	$: revisionByTurn = (revision?.turns ?? []).reduce<Record<number, ChallengeRevisionTurn>>(
		(acc, item) => {
			acc[item.turn_no] = item;
			return acc;
		},
		{}
	);
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
					{#if revision && revision.total_spans > 0}
						<!-- 服务端两份快照直接比对得出，不依赖客户端上报，也不受客户端时钟影响。 -->
						<span
							class={revision.revised
								? 'font-medium text-emerald-700 dark:text-emerald-400'
								: 'font-medium text-rose-600 dark:text-rose-400'}
						>
							{revision.revised
								? $i18n.t('Changed {{changed}} of {{total}} challenged sentences', {
										changed: revision.changed_spans,
										total: revision.total_spans
									})
								: $i18n.t('None of the challenged sentences changed')}
						</span>
					{/if}
				{/if}
			</div>

			{#if session.status !== 'skipped'}
				<div class="mt-4">
					<ChallengeTranscript
						{turns}
						plannedRounds={session.planned_rounds}
						{criteriaLabels}
						{revisionByTurn}
					/>
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
												<span aria-hidden="true">·</span><span>{item.text}</span>
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
				信任层级（PRD 12.9.7）：质疑文本、引用的原文片段与回合数是服务端生成的
				权威数据；学生回应是他自己敲的字，可信度等同 typed 正文；「那一句有没有
				变」由两份服务端快照比对得出，同样不依赖客户端上报。所以这一块不挂
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
