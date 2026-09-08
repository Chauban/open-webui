<script lang="ts">
	// 写作前的评析环节。
	//
	// 和提交前的读者试读是一对：那边是别人质疑你，这边是你质疑别人。空白页阶段没法
	// 被质疑（没有可打的东西），但完全可以先读一篇有问题的文章，练同一只眼睛。
	//
	// 三条封顶，**不设及格线**——找出一条也放行。一旦设卡，学生就会开始猜「系统想要
	// 什么答案」，这个环节训练的东西当场变质。措辞也避开「考试」「测验」：他的位置是
	// 「先当一次读者」，不是「先考一次试」。
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { resolveErrorMessage } from '$lib/utils/education';
	import { submitAssignmentCritique } from '$lib/apis/education';
	import type { CritiqueState } from '$lib/apis/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => $i18n.t(key, options);

	export let assignmentId: string;
	export let state: CritiqueState;
	export let modelId: string;
	/** 完成或跳过之后回到写作区。 */
	export let onDone: (next: CritiqueState) => void;

	const MAX_ITEMS = 3;

	let items = ['', '', ''];
	let busy = false;

	$: filled = items.filter((item) => item.trim()).length;

	const send = async () => {
		if (busy) return;
		const payload = items.map((item) => item.trim()).filter(Boolean);
		if (payload.length === 0) {
			toast.error($i18n.t('Point out at least one thing.'));
			return;
		}
		if (!modelId) {
			toast.error($i18n.t('Pick a model first.'));
			return;
		}
		busy = true;
		try {
			onDone(await submitAssignmentCritique(localStorage.token, assignmentId, payload, modelId));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			busy = false;
		}
	};
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
	<div
		class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white p-6 shadow-2xl dark:bg-gray-850"
	>
		<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
			{$i18n.t('Read this one first')}
		</h2>
		<div class="mt-2 space-y-1 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
			<p>{$i18n.t('This piece has problems in it. Say where it does not convince you.')}</p>
			<p>{$i18n.t('Up to {{max}} things. One is enough to move on.', { max: MAX_ITEMS })}</p>
		</div>

		<div class="mt-4 flex-1 space-y-4 overflow-y-auto pr-1">
			<div
				class="whitespace-pre-wrap rounded-2xl bg-stone-50 px-4 py-3 text-sm leading-relaxed text-gray-800 dark:bg-gray-900 dark:text-gray-200"
			>
				{state.text}
			</div>

			{#each items as _, index}
				<div>
					<label
						for={`critique-item-${index}`}
						class="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300"
					>
						{$i18n.t('Problem {{n}}', { n: index + 1 })}
					</label>
					<textarea
						id={`critique-item-${index}`}
						bind:value={items[index]}
						rows="2"
						disabled={busy}
						class="w-full {EDU_FIELD_CLASS}"
						placeholder={index === 0
							? $i18n.t('For example: this conclusion rests on a single example.')
							: ''}
					/>
				</div>
			{/each}
		</div>

		<div class="mt-5 flex items-center justify-between gap-3">
			<span class="text-xs text-gray-400">
				{$i18n.t('{{filled}} of {{max}} written', { filled, max: MAX_ITEMS })}
			</span>
			<EduButton
				variant="primary"
				class="flex items-center gap-2"
				disabled={busy || filled === 0}
				on:click={send}
			>
				{#if busy}
					<Spinner className="size-4" />
					{$i18n.t('Sending...')}
				{:else}
					{$i18n.t('Done, start writing')}
				{/if}
			</EduButton>
		</div>
	</div>
</div>
