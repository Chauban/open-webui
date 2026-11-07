<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';
	import { getSubmissionProcess, type SubmissionProcess } from '$lib/apis/education';
	import type { TeacherConversationEvent } from '$lib/utils/teacher-writing-process';
	import {
		initialProcessState,
		processSnapshots,
		previousProcessSnapshot,
		snapshotLabel,
		conversationWithinRange,
		type ProcessViewState
	} from '$lib/utils/process-review';
	import { formatEpochTime, resolveErrorMessage } from '$lib/utils/education';
	import { THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';
	import EduButton from './EduButton.svelte';
	import { EDU_FILTER_FIELD_CLASS } from './styles';
	const i18n = getContext<Writable<I18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	export let submissionId: string;
	export let finalVersionId: string;
	export let events: TeacherConversationEvent[] = [];
	export let editingEvents: any[] = [];
	export let state: ProcessViewState = initialProcessState();
	export let catalog: SubmissionProcess | null = null;
	export let onInspect: (request: {
		beforeId: string;
		afterId: string;
		mode: 'snapshot' | 'compare';
	}) => Promise<void> = async () => {};
	let loading = false;
	let error = '';
	let alive = true;
	let catalogRequest: Promise<SubmissionProcess | null> | null = null;
	$: snapshots = processSnapshots(catalog, state);
	$: hiddenCount = (catalog?.snapshots ?? []).filter((s) => !s.major).length;
	$: byId = new Map((catalog?.snapshots ?? []).map((s) => [s.id, s]));
	$: before = byId.get(state.range?.beforeId ?? '');
	$: after = byId.get(state.range?.afterId ?? '');
	$: rows = [
		...(state.filter === 'changes'
			? []
			: events
					.filter(
						(e) =>
							!state.range ||
							!before ||
							!after ||
							conversationWithinRange(e.created_at, before, after)
					)
					.map((event) => ({ key: event.key, time: event.created_at, event, snapshot: null }))),
		...(state.filter === 'conversation'
			? []
			: snapshots
					.filter((s) => s.kind !== 'reading')
					.map((snapshot) => ({
						key: `snapshot:${snapshot.id}`,
						time: snapshot.created_at ?? 0,
						event: null,
						snapshot
					})))
	].sort((a, b) => a.time - b.time);
	const html = (text: string) => DOMPurify.sanitize(marked.parse(text, { async: false }) as string);
	const ensureCatalog = async () => {
		if (catalog?.final_version_id === finalVersionId) return catalog;
		if (catalogRequest) return catalogRequest;
		loading = true;
		error = '';
		const id = submissionId,
			version = finalVersionId;
		catalogRequest = getSubmissionProcess(localStorage.token, id, version)
			.then((result) => {
				if (!alive || id !== submissionId || version !== finalVersionId) return null;
				catalog = result;
				state = {
					...state,
					beforeId: state.beforeId || result.default_before_id,
					afterId: state.afterId || result.default_after_id
				};
				return result;
			})
			.catch((err) => {
				if (alive) error = resolveErrorMessage(err, t);
				return null;
			})
			.finally(() => {
				if (alive) loading = false;
				catalogRequest = null;
			});
		return catalogRequest;
	};
	const inspect = (beforeId: string, afterId: string, mode: 'snapshot' | 'compare') =>
		onInspect({ beforeId, afterId, mode });
	const selectEvent = (event: TeacherConversationEvent) => {
		const id = catalog?.event_snapshots[event.key];
		if (!id) return;
		state = {
			...state,
			selectedKey: event.key,
			afterId: id,
			beforeId: previousProcessSnapshot(snapshots, id)
		};
		void inspect(id, id, 'snapshot');
	};
	const selectChange = (id: string) => {
		const prev = previousProcessSnapshot(snapshots, id);
		state = { ...state, selectedKey: `snapshot:${id}`, beforeId: prev, afterId: id };
		void inspect(prev, id, prev === id ? 'snapshot' : 'compare');
	};
	const compare = () => {
		if (state.beforeId && state.afterId) void inspect(state.beforeId, state.afterId, 'compare');
	};
	const setMode = (mode: 'process' | 'compare') => {
		state = { ...state, mode };
		if (mode === 'compare') compare();
	};
	export const showOverall = async () => {
		const value = await ensureCatalog();
		if (!value) return;
		state = {
			...state,
			mode: 'compare',
			beforeId: value.default_before_id,
			afterId: value.default_after_id,
			selectedKey: '',
			range: null
		};
		compare();
	};
	const step = (delta: number) => {
		const index = snapshots.findIndex((s) => s.id === state.afterId);
		const next = snapshots[index + delta];
		if (next) selectChange(next.id);
	};
	const toggle = (key: string) =>
		(state = {
			...state,
			expanded: state.expanded.includes(key)
				? state.expanded.filter((k) => k !== key)
				: [...state.expanded, key]
		});
	onMount(() => {
		void ensureCatalog();
	});
	onDestroy(() => {
		alive = false;
	});
</script>

<section aria-label={$i18n.t('写作过程浏览器')}>
	<div class="mb-3 flex flex-wrap gap-2">
		<EduButton
			size="sm"
			variant={state.mode === 'process' ? 'primary' : 'secondary'}
			on:click={() => setMode('process')}>{$i18n.t('过程回放')}</EduButton
		>
		<EduButton
			size="sm"
			variant={state.mode === 'compare' ? 'primary' : 'secondary'}
			disabled={!catalog}
			on:click={() => setMode('compare')}>{$i18n.t('版本对照')}</EduButton
		>
	</div>
	<p class="mb-3 text-xs leading-5 text-gray-500">
		{$i18n.t(
			'点击记录，左侧查看对应稿件或修改。只展示本次提交保留的内容，不自动判断是否采纳建议。'
		)}
	</p>
	{#if loading}<p class="text-sm text-gray-500" role="status">{$i18n.t('Loading...')}</p>{/if}
	{#if error}<p class="text-sm text-red-600" role="alert">{error}</p>
		<EduButton size="sm" on:click={ensureCatalog}>{$i18n.t('Retry')}</EduButton>{/if}
	{#if catalog}
		{#if catalog.round_no > 1}<p class="mb-3 text-xs text-gray-500">
				{$i18n.t('中间保存版本来自本轮；更早的详细过程请切换提交轮次查看。')}
			</p>{/if}
		{#if state.mode === 'compare'}
			<div class="grid gap-3 sm:grid-cols-2">
				<label class="text-xs text-gray-500"
					>{$i18n.t('起点稿件')}<select
						aria-label={$i18n.t('起点稿件')}
						class="mt-1 w-full {EDU_FILTER_FIELD_CLASS}"
						bind:value={state.beforeId}
						on:change={compare}
						>{#each snapshots as snapshot}<option value={snapshot.id}
								>{snapshotLabel(snapshot, t)}{snapshot.created_at
									? ` · ${formatEpochTime(snapshot.created_at)}`
									: ''}</option
							>{/each}</select
					></label
				>
				<label class="text-xs text-gray-500"
					>{$i18n.t('终点稿件')}<select
						aria-label={$i18n.t('终点稿件')}
						class="mt-1 w-full {EDU_FILTER_FIELD_CLASS}"
						bind:value={state.afterId}
						on:change={compare}
						>{#each snapshots as snapshot}<option value={snapshot.id}
								>{snapshotLabel(snapshot, t)}{snapshot.created_at
									? ` · ${formatEpochTime(snapshot.created_at)}`
									: ''}</option
							>{/each}</select
					></label
				>
			</div>
			<div class="my-3 flex flex-wrap gap-2">
				<EduButton size="sm" on:click={showOverall}>{$i18n.t('从起点到提交')}</EduButton>
				<EduButton
					size="sm"
					disabled={snapshots.findIndex((s) => s.id === state.afterId) <= 0}
					on:click={() => step(-1)}>{$i18n.t('上一次修改')}</EduButton
				>
				<EduButton
					size="sm"
					disabled={snapshots.findIndex((s) => s.id === state.afterId) >= snapshots.length - 1}
					on:click={() => step(1)}>{$i18n.t('下一次修改')}</EduButton
				>
			</div>
			<EduButton
				size="sm"
				on:click={() =>
					(state = {
						...state,
						mode: 'process',
						filter: 'conversation',
						range: { beforeId: state.beforeId, afterId: state.afterId }
					})}>{$i18n.t('看这期间的交流')}</EduButton
			>
		{:else}
			<div class="mb-3 flex flex-wrap gap-2">
				{#each [{ key: 'all', label: '全部' }, { key: 'conversation', label: '只看对话' }, { key: 'changes', label: '只看修改' }] as filter}<button
						type="button"
						class="rounded-full px-3 py-1 text-xs {state.filter === filter.key
							? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
							: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'}"
						aria-pressed={state.filter === filter.key}
						on:click={() =>
							(state = {
								...state,
								filter: filter.key as ProcessViewState['filter'],
								range: filter.key === 'conversation' ? state.range : null
							})}>{$i18n.t(filter.label)}</button
					>{/each}
			</div>
			{#if state.range}<p class="mb-3 text-xs text-gray-500">
					{$i18n.t('已按所选稿件的时间范围筛选交流。')}
					<button
						class="underline"
						type="button"
						on:click={() => (state = { ...state, range: null })}>{$i18n.t('查看全部过程')}</button
					>
				</p>{/if}
		{/if}
		{#if hiddenCount > 0}<label class="my-3 flex items-center gap-2 text-xs text-gray-500"
				><input type="checkbox" bind:checked={state.showAutosaves} />{$i18n.t(
					'显示中间自动保存版本'
				)}（{hiddenCount}）</label
			>{/if}
		{#if state.mode === 'process'}
			<div class="space-y-3" role="list">
				{#each rows as row (row.key)}
					<article
						role="listitem"
						class="rounded-xl border p-3 text-sm {state.selectedKey === row.key
							? 'border-sky-400 bg-sky-50 dark:bg-sky-950/30'
							: 'border-gray-200 dark:border-gray-700'}"
					>
						{#if row.event}
							<div class="mb-2 flex items-center justify-between gap-2 text-xs text-gray-500">
								<strong>{row.event.meta}</strong><span>{formatEpochTime(row.time)}</span>
							</div>
							{#if row.event.role === 'assistant' && row.event.thinking_level}<p
									class="mb-2 text-xs text-gray-500"
								>
									{$i18n.t('Thinking: {{level}}', {
										level: $i18n.t(
											THINKING_SETTING_TEXT[row.event.thinking_level] ?? row.event.thinking_level
										)
									})}
								</p>{/if}
							<div
								class="prose prose-sm max-w-none break-words dark:prose-invert {row.event.label
									.length <= 180 || state.expanded.includes(row.key)
									? ''
									: 'line-clamp-3'}"
							>
								{@html html(row.event.label)}
							</div>
							<div class="mt-2 flex flex-wrap gap-3 text-xs">
								{#if catalog.event_snapshots[row.key]}<button
										type="button"
										class="underline underline-offset-4"
										aria-label={`${$i18n.t('查看稿件：')}${row.event.meta}`}
										on:click={() => selectEvent(row.event!)}>{$i18n.t('查看对应稿件')}</button
									>{/if}
								{#if row.event.label.length > 180}<button
										type="button"
										class="text-gray-500 underline"
										on:click={() => toggle(row.key)}
										>{$i18n.t(
											state.expanded.includes(row.key) ? 'Collapse' : 'Expand full text'
										)}</button
									>{/if}
							</div>
						{:else if row.snapshot}
							<button
								type="button"
								class="w-full text-left"
								data-testid={`process-snapshot-${row.snapshot.id}`}
								on:click={() => selectChange(row.snapshot!.id)}
							>
								<span class="font-medium">{snapshotLabel(row.snapshot, t)}</span>
								<span class="ml-2 text-xs text-gray-500"
									>{row.time ? formatEpochTime(row.time) : ''}</span
								>
								<span class="mt-1 block text-xs text-gray-500"
									>{row.snapshot.used_by_ai
										? $i18n.t('曾提供给 AI 阅读')
										: $i18n.t('查看这一步的变化')}</span
								>
							</button>
						{/if}
					</article>
				{/each}
				{#if rows.length === 0}<p class="text-xs text-gray-500">
						{$i18n.t('该范围没有已记录的交流或修改。')}
					</p>{/if}
			</div>
			{#if state.filter !== 'conversation' && editingEvents.length > 0}<details
					class="mt-4 text-xs text-gray-500"
				>
					<summary class="cursor-pointer"
						>{$i18n.t('详细编辑记录')}（{editingEvents.length}）</summary
					>{#each editingEvents as event}<div
							class="mt-2 border-t border-gray-200 pt-2 dark:border-gray-700"
						>
							<p>{formatEpochTime(event.created_at)} · {event.meta} · {event.label}</p>
							{#if event.run?.inserted_text}<p class="whitespace-pre-wrap text-emerald-700">
									+ {event.run.inserted_text}
								</p>{/if}{#if event.run?.deleted_text}<p class="whitespace-pre-wrap text-rose-700">
									− {event.run.deleted_text}
								</p>{/if}
						</div>{/each}
				</details>{/if}
		{/if}
	{/if}
</section>
