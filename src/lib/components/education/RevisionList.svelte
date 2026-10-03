<script lang="ts">
	// 修订初稿作业的修改清单:第一次通读给每个评分维度的结论,学生在提交时交代怎么处理的。
	//
	// 结论在学生交初稿后就逐项定好了,首轮回复按它写;之后的对话不改这张表。
	// 只在提交弹窗里出现:写作过程中对话管「怎么改」,这里管「最后交代」。
	// - 要改:每一项都要选怎么处理的,没全改的写为什么;
	// - 可改进:可选可不选;
	// - 达标、暂缓:只列出来,不用表态。
	// 选处理方式立即存;理由在失焦时存,提交时再随请求带上一遍,不会丢最后一次修改。
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		updateRevisionItem,
		type RevisionDecision,
		type RevisionItem
	} from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';

	export let sessionId: string;
	export let items: RevisionItem[] = [];
	export let status: 'ready' | 'pending' | 'failed' | null = null;
	export let criteriaLabels: Record<string, string> = {};
	export let showMissing = false;
	export let onRetry: () => void = () => {};

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const DECISIONS: Array<{ value: RevisionDecision; label: string }> = [
		{ value: 'revised', label: 'Changed it' },
		{ value: 'partly', label: 'Changed part of it' },
		{ value: 'kept', label: 'Left it as is' }
	];

	let savingNo: number | null = null;

	$: mustFix = items.filter((item) => item.status === 'problem');
	$: couldImprove = items.filter((item) => item.status === 'minor');
	$: passed = items.filter((item) => item.status === 'ok');
	$: deferred = items.filter((item) => item.status === 'deferred');
	$: blocking = items.find((item) => item.is_blocking) ?? null;

	const labelOf = (item: RevisionItem) => criteriaLabels[item.criterion_key] ?? item.criterion_key;

	const isMissing = (item: RevisionItem) =>
		item.status === 'problem' &&
		(!item.decision || (item.decision !== 'revised' && !(item.reason ?? '').trim()));

	const save = async (item: RevisionItem) => {
		savingNo = item.item_no;
		try {
			const result = await updateRevisionItem(localStorage.token, sessionId, item.item_no, {
				decision: item.decision,
				reason: (item.reason ?? '').trim() || null
			});
			// 只回填处理方式,理由以本地为准:学生可能在请求返回前又多打了几个字。
			const saved = new Map(result.items.map((entry) => [entry.item_no, entry]));
			items = items.map((entry) => ({
				...entry,
				decision: saved.get(entry.item_no)?.decision ?? entry.decision
			}));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingNo = null;
		}
	};

	const choose = (item: RevisionItem, decision: RevisionDecision) => {
		// 可改进的条目再点一下已选的,就是撤回表态。
		item.decision = item.status === 'minor' && item.decision === decision ? null : decision;
		items = items;
		void save(item);
	};

	const setReason = (item: RevisionItem, reason: string) => {
		item.reason = reason;
		items = items;
	};

	const reasonPlaceholder = (decision: RevisionDecision | null) =>
		decision === 'partly' ? t('Which part did you leave, and why?') : t('Why did you leave it?');
</script>

{#if status === 'pending' || status === 'failed' || items.length > 0}
	<div
		class="rounded-2xl border border-gray-200 bg-white px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900"
	>
		<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
			{$i18n.t('Revision list')}
		</div>

		{#if status === 'pending' && items.length === 0}
			<p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('The first read-through is still running…')}
			</p>
		{:else if status === 'failed' && items.length === 0}
			<p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('The first read-through did not finish.')}
				<button
					type="button"
					class="ml-1 underline underline-offset-2 hover:text-gray-700 dark:hover:text-gray-300"
					on:click={onRetry}
				>
					{$i18n.t('Try again')}
				</button>
			</p>
		{:else}
			<p class="mt-1 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
				{$i18n.t(
					'What the first read-through concluded for each rubric criterion. Say how you handled each item that needed changing; if you did not change it, or only part of it, say why.'
				)}
			</p>

			{#each [{ key: 'problem', title: 'Needs changing', list: mustFix }, { key: 'minor', title: 'Could be better (optional)', list: couldImprove }] as group (group.key)}
				{#if group.list.length > 0}
					<div class="mt-3 text-[11px] font-medium text-gray-500 dark:text-gray-400">
						{$i18n.t(group.title)}
					</div>
					<ol class="mt-1.5 space-y-2">
						{#each group.list as item (item.item_no)}
							{@const missing = showMissing && isMissing(item)}
							<li
								data-revision-missing={missing ? 'true' : undefined}
								class="rounded-xl px-2.5 py-2 {missing
									? 'bg-rose-50 ring-1 ring-rose-200 dark:bg-rose-950/30 dark:ring-rose-900'
									: 'bg-gray-50 dark:bg-gray-850'}"
							>
								<div class="text-[11px] font-medium text-gray-700 dark:text-gray-300">
									{labelOf(item)}
									{#if item.follow_up_at && item.is_blocking}
										<span
											class="ml-1 rounded-full bg-sky-50 px-1.5 py-px text-[10px] font-normal text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
											>{$i18n.t('Fixed, confirmed on follow-up')}</span
										>
									{:else if item.follow_up_at}
										<span
											class="ml-1 rounded-full bg-sky-50 px-1.5 py-px text-[10px] font-normal text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
											>{$i18n.t('Follow-up read')}</span
										>
									{/if}
								</div>
								{#if item.finding}
									<div class="mt-0.5 text-xs leading-relaxed text-gray-800 dark:text-gray-200">
										{item.finding}
									</div>
								{/if}
								{#if item.quoted_span}
									<div
										class="mt-1 border-l-2 border-gray-300 pl-2 text-[11px] leading-relaxed text-gray-500 dark:border-gray-700 dark:text-gray-400"
									>
										{item.quoted_span}
									</div>
								{/if}

								<div class="mt-2 flex flex-wrap gap-1.5">
									{#each DECISIONS as option}
										<button
											type="button"
											class="rounded-full border px-2.5 py-1 text-[11px] transition disabled:cursor-not-allowed {item.decision ===
											option.value
												? 'border-black bg-black text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
												: 'border-gray-300 bg-white text-gray-700 hover:border-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300'}"
											aria-pressed={item.decision === option.value}
											disabled={savingNo === item.item_no}
											on:click={() => choose(item, option.value)}
										>
											{$i18n.t(option.label)}
										</button>
									{/each}
								</div>

								{#if item.decision === 'partly' || item.decision === 'kept'}
									<textarea
										class="mt-2 w-full resize-none rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
										rows="2"
										maxlength="500"
										placeholder={reasonPlaceholder(item.decision)}
										value={item.reason ?? ''}
										on:input={(event) => setReason(item, event.currentTarget.value)}
										on:blur={() => save(item)}
									></textarea>
								{/if}
							</li>
						{/each}
					</ol>
				{/if}
			{/each}

			{#if passed.length > 0}
				<div class="mt-3 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
					<span class="font-medium">{$i18n.t('Meets the standard')}</span>
					· {passed.map(labelOf).join('、')}
				</div>
			{/if}
			{#if deferred.length > 0}
				<div class="mt-1 text-[11px] leading-relaxed text-gray-400 dark:text-gray-500">
					<span class="font-medium">{$i18n.t('Not looked at yet')}</span>
					· {deferred.map(labelOf).join('、')}
					<!-- 提交时还暂缓,就不会再补看了:说清为什么没看、现在交意味着什么。 -->
					· {$i18n.t(
						'These are read only after "{{blocking}}" is fixed and you click "Fixed it, read the rest". If you submit now, your teacher sees no verdict on them.',
						{ blocking: blocking ? labelOf(blocking) : '' }
					)}
				</div>
			{/if}
		{/if}
	</div>
{/if}
