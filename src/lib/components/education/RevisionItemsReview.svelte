<script lang="ts">
	// 批改页:这一轮的第一次通读结论和学生的处理。每个评分维度一行,和评分用的是同一张表:
	// 通读给了什么结论、学生怎么处理、为什么。数据是提交时冻存的,之后学生再改不影响这一轮。
	//
	// 「原句一字未动」:学生说改了(或改了一部分),那句原句却原样留在终稿里。
	// 只说明动没动,不判断改得好不好,也可能是学生在别处做了等效修改,由老师判断。
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext } from 'svelte';

	import type { RevisionDecision, RevisionStatus } from '$lib/apis/education';

	type SheetItem = {
		item_no: number;
		criterion_key: string;
		status: RevisionStatus;
		finding: string | null;
		quoted_span: string | null;
		decision: RevisionDecision | null;
		reason: string | null;
		is_blocking: boolean;
		follow_up_at: number | null;
		quote_unchanged: boolean;
	};

	export let sheet: { status: 'ready' | 'missing'; items: SheetItem[] } | null = null;
	export let criteriaLabels: Record<string, string> = {};

	const i18n = getContext<Writable<i18nType>>('i18n');

	const STATUS_LABELS: Record<RevisionStatus, string> = {
		problem: 'Needs changing',
		minor: 'Could be better',
		ok: 'Meets the standard',
		deferred: 'Not looked at yet'
	};
	const STATUS_TONES: Record<RevisionStatus, string> = {
		problem: 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300',
		minor: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300',
		ok: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
		deferred: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
	};
	const DECISION_LABELS: Record<RevisionDecision, string> = {
		revised: 'Changed it',
		partly: 'Changed part of it',
		kept: 'Left it as is'
	};
</script>

{#if sheet}
	<div>
		<div class="mb-2 text-sm font-semibold text-gray-950 dark:text-gray-100">
			{$i18n.t('First read-through')}
		</div>
		{#if sheet.status === 'missing'}
			<div
				class="rounded-2xl bg-gray-50 px-4 py-3 text-sm text-gray-500 dark:bg-gray-800 dark:text-gray-400"
			>
				{$i18n.t(
					'This round has no first read-through: it did not finish before the student submitted.'
				)}
			</div>
		{:else}
			<p class="mb-2 text-xs text-gray-400">
				{$i18n.t(
					'What the first read-through concluded for each rubric criterion, and how the student handled it.'
				)}
			</p>
			<ol class="space-y-2">
				{#each sheet.items as item (item.item_no)}
					<li class="rounded-2xl bg-gray-50 px-4 py-3 text-sm dark:bg-gray-800">
						<div class="flex flex-wrap items-center gap-1.5">
							<span class="text-xs font-medium text-gray-700 dark:text-gray-300">
								{criteriaLabels[item.criterion_key] ?? item.criterion_key}
							</span>
							<span class="rounded-full px-2 py-0.5 text-[11px] {STATUS_TONES[item.status]}">
								{$i18n.t(STATUS_LABELS[item.status])}
							</span>
							{#if item.follow_up_at && item.is_blocking}
								<span
									class="rounded-full bg-sky-50 px-1.5 py-px text-[10px] font-normal text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
									>{$i18n.t('Fixed, confirmed on follow-up')}</span
								>
							{:else if item.follow_up_at}
								<span
									class="rounded-full bg-sky-50 px-1.5 py-px text-[10px] font-normal text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
									>{$i18n.t('Follow-up read')}</span
								>
							{/if}
							{#if item.decision}
								<span
									class="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
								>
									{$i18n.t('Student')}: {$i18n.t(DECISION_LABELS[item.decision])}
								</span>
							{:else if item.status === 'problem'}
								<span class="text-[11px] text-gray-400"
									>{$i18n.t('No answer from the student')}</span
								>
							{/if}
							{#if item.decision && item.decision !== 'kept' && item.quote_unchanged}
								<span
									class="rounded-full bg-rose-50 px-2 py-0.5 text-[11px] text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
								>
									{$i18n.t('Quoted sentence unchanged')}
								</span>
							{/if}
						</div>
						{#if item.finding}
							<div class="mt-1.5 text-gray-800 dark:text-gray-200">{item.finding}</div>
						{/if}
						{#if item.quoted_span}
							<div
								class="mt-1.5 border-l-2 border-gray-300 pl-2 text-xs leading-relaxed text-gray-500 dark:border-gray-700 dark:text-gray-400"
							>
								{item.quoted_span}
							</div>
						{/if}
						{#if item.reason}
							<div class="mt-1.5 text-xs leading-relaxed text-gray-600 dark:text-gray-300">
								<span class="text-gray-400">{$i18n.t('Student says')}</span>
								{item.reason}
							</div>
						{/if}
					</li>
				{/each}
			</ol>
		{/if}
	</div>
{/if}
