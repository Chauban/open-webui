<script lang="ts">
	// 读者试读收尾清单回流到写作面板。
	//
	// 没有这一步，试读就只是「被问一顿」，学生带不走任何东西，下次必然跳过。
	// 清单里的每条都是一句照着就能改的提示，勾选状态存服务端，刷新不丢。
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { updateChallengeChecklist } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import type { ChallengeDetail } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let detail: ChallengeDetail | null = null;
	export let onDetailChange: (next: ChallengeDetail) => void = () => {};

	let expanded = true;
	let saving = false;

	$: unresolved =
		detail?.session?.status === 'completed'
			? (detail.session.closing_summary_json?.unresolved ?? [])
			: [];
	$: checked = new Set(detail?.session?.checklist_state_json?.checked_indexes ?? []);

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
								{item}
							</span>
						</label>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}
