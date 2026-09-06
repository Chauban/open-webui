<script lang="ts">
	// 读者试读收尾清单回流到写作面板。
	//
	// 没有这一步，试读就只是「被问一顿」，学生带不走任何东西，下次必然跳过。
	// 清单里的每条都是一句照着就能改的提示，勾选状态存服务端，刷新不丢。
	//
	// 清单下面还挂着本轮完整往来。关掉试读弹窗之后就再也看不到自己被问了什么、
	// 当时怎么答的，这个方向是反的——真正要拿这份记录去改文章的是学生，而教师端
	// 反倒一直有完整记录。数据用写作面板已经持有的那份，不额外请求。
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import ChallengeTranscript from '$lib/components/education/ChallengeTranscript.svelte';
	import { updateChallengeChecklist } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import type { ChallengeDetail } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let detail: ChallengeDetail | null = null;
	export let onDetailChange: (next: ChallengeDetail) => void = () => {};

	let expanded = true;
	// 往来记录默认折叠：清单才是拿来改文章的，回看是需要时才展开的东西。
	let transcriptExpanded = false;
	let saving = false;

	$: unresolved =
		detail?.session?.status === 'completed'
			? (detail.session.closing_summary_json?.unresolved ?? [])
			: [];
	$: checked = new Set(detail?.session?.checklist_state_json?.checked_indexes ?? []);
	$: turns = detail?.turns ?? [];
	$: plannedRounds = detail?.session?.planned_rounds ?? 0;

	const toggle = async (index: number) => {
		if (!detail || saving) return;
		const next = new Set(checked);
		if (next.has(index)) {
			next.delete(index);
		} else {
			next.add(index);
		}
		saving = true;
		try {
			onDetailChange(
				await updateChallengeChecklist(localStorage.token, detail.session.id, [...next])
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, $i18n.t('Could not save the checklist.')));
		} finally {
			saving = false;
		}
	};
</script>

{#if unresolved.length > 0}
	<div class="mt-3 rounded-2xl bg-amber-50 px-3 py-2.5 dark:bg-amber-950/30">
		<button
			type="button"
			class="flex w-full items-center justify-between gap-2 text-left"
			on:click={() => (expanded = !expanded)}
		>
			<span
				class="text-[11px] font-medium uppercase tracking-[0.12em] text-amber-800 dark:text-amber-300"
			>
				{$i18n.t('From the read-through')}
			</span>
			<span class="text-[11px] text-amber-700 dark:text-amber-400">
				{$i18n.t('{{done}} of {{total}} done', {
					done: [...checked].filter((index) => index < unresolved.length).length,
					total: unresolved.length
				})}
			</span>
		</button>

		{#if expanded}
			<ul class="mt-2 space-y-1.5">
				{#each unresolved as item, index}
					<li>
						<label class="flex cursor-pointer items-start gap-2">
							<input
								type="checkbox"
								class="mt-0.5 size-3.5 shrink-0 accent-amber-600"
								checked={checked.has(index)}
								disabled={saving}
								on:change={() => toggle(index)}
							/>
							<span
								class="text-xs leading-relaxed {checked.has(index)
									? 'text-amber-700/60 line-through dark:text-amber-400/50'
									: 'text-amber-900 dark:text-amber-200'}"
							>
								{item.text}
							</span>
						</label>
					</li>
				{/each}
			</ul>

			{#if turns.length > 0}
				<div class="mt-2.5 border-t border-amber-200/70 pt-2 dark:border-amber-900/50">
					<button
						type="button"
						class="text-[11px] font-medium text-amber-700 underline-offset-2 hover:underline dark:text-amber-400"
						on:click={() => (transcriptExpanded = !transcriptExpanded)}
					>
						{transcriptExpanded
							? $i18n.t('Hide what the reader asked')
							: $i18n.t('See what the reader asked')}
					</button>

					{#if transcriptExpanded}
						<div class="mt-2 rounded-xl bg-white/70 px-3 py-2.5 dark:bg-gray-900/50">
							<ChallengeTranscript {turns} {plannedRounds} />
						</div>
					{/if}
				</div>
			{/if}
		{/if}
	</div>
{/if}
