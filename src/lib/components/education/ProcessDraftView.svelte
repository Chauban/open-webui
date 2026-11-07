<script lang="ts">
	import { getContext } from 'svelte';
	import { get, type Writable } from 'svelte/store';
	import type { i18n as I18nType } from 'i18next';
	import type { ProcessInspection } from '$lib/utils/process-review';
	import type { SourceSnapshot } from '$lib/utils/teacher-writing-process';
	import { snapshotLabel } from '$lib/utils/process-review';
	import { formatEpoch } from '$lib/utils/education';
	import TextDiffBlocks from './TextDiffBlocks.svelte';
	export let inspection: ProcessInspection | null = null;
	export let source: SourceSnapshot | null = null;
	const i18n = getContext<Writable<I18nType>>('i18n');
	const t = (s: string, o?: Record<string, unknown>) => get(i18n).t(s, o);
</script>

{#if inspection?.loading}<p role="status" class="text-sm text-gray-500">{$i18n.t('Loading...')}</p>
{:else if inspection?.error}<p role="alert" class="text-sm text-red-600">{inspection.error}</p>
{:else if inspection?.comparison}
	{@const result = inspection.comparison}
	<h3 class="text-sm font-semibold">
		{inspection.mode === 'snapshot'
			? snapshotLabel(result.after, t)
			: `${snapshotLabel(result.before, t)} → ${snapshotLabel(result.after, t)}`}
	</h3>
	<p class="mt-1 mb-4 text-xs text-gray-500">
		{$i18n.t('本次提交保留的只读记录')} · {formatEpoch(result.after.created_at)}
	</p>
	{#if inspection.mode === 'snapshot'}
		{#if source?.descriptionVersion != null}<p class="mb-3 text-xs text-gray-500">
				{$i18n.t('当时的要求版本')}
				{source.descriptionVersion}
			</p>{/if}
		<p class="whitespace-pre-wrap break-words text-sm leading-7">
			{result.after.text || $i18n.t('当时正文为空。')}
		</p>
	{:else}
		<p class="text-xs text-gray-500">
			{$i18n.t('绿色表示新增，红色划线表示删除；只呈现文字差异。')}
		</p>
		{#if result.unchanged}<p class="mt-3 text-sm text-gray-500">
				{$i18n.t('两份稿件文字相同。')}
			</p>{/if}
		<TextDiffBlocks blocks={result.blocks} />
		<details class="mt-4 text-sm">
			<summary class="cursor-pointer text-gray-500">{$i18n.t('查看两份完整稿件')}</summary>
			<div class="mt-3 grid gap-4 xl:grid-cols-2">
				<section>
					<h4 class="mb-2 font-medium">{snapshotLabel(result.before, t)}</h4>
					<p class="whitespace-pre-wrap break-words leading-7">
						{result.before.text || $i18n.t('当时正文为空。')}
					</p>
				</section>
				<section>
					<h4 class="mb-2 font-medium">{snapshotLabel(result.after, t)}</h4>
					<p class="whitespace-pre-wrap break-words leading-7">
						{result.after.text || $i18n.t('当时正文为空。')}
					</p>
				</section>
			</div>
		</details>
	{/if}
{:else}<p class="text-sm text-gray-500">{$i18n.t('从右侧选择一条交流或修改记录。')}</p>{/if}
