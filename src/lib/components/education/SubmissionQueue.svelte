<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import {
		getEducationNotificationSummary,
		getTeacherAssignments,
		getTeacherClassrooms,
		getTeacherReview,
		markEducationNotificationsRead
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import EduBadge from './EduBadge.svelte';
	import EduButton from './EduButton.svelte';
	import EduCard from './EduCard.svelte';
	import EduRiskBadges from './EduRiskBadges.svelte';
	import EduStateCard from './EduStateCard.svelte';
	import { eduFilterClass, eduSegmentClass } from './styles';
	import {
		formatEpoch,
		getClassroomDisplayName,
		getReviewStatusLabel,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 批改队列与「某份作业的提交」是同一份列表:此前一个是卡片、一个是表格,
	// 状态标签的顺序和默认值不同,作业页还缺「已退回」,两边露出的信号也不一样
	// (一边只有过程风险,一边只有学生自述)。现在合成一个组件,作业页只是固定了 assignmentId。

	/** 固定到某份作业:隐藏作业/班级列与对应筛选。 */
	export let assignmentId = '';
	export let status: 'pending' | 'returned' | 'reviewed' | 'all' | 'unsubmitted' = 'pending';
	/** 传数字才显示「未提交」标签;其内容由调用方用 unsubmitted 插槽提供。 */
	export let unsubmittedCount: number | null = null;
	export let initialClassroomId = '';
	export let initialAssignmentId = '';

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	$: formatRelative = (timestamp: number) =>
		dayjs(timestamp * 1000)
			.locale($i18n.language)
			.fromNow();

	const PAGE_SIZE = 50;
	const STATUS_TABS = [
		{ value: 'pending', label: 'To Review' },
		{ value: 'returned', label: 'Returned' },
		{ value: 'reviewed', label: 'Reviewed' },
		{ value: 'all', label: 'All' }
	] as const;
	const STATUS_TONES = { pending: 'amber', reviewed: 'emerald', returned: 'sky' };

	let items = [];
	let total = 0;
	let loading = true;
	let loadingMore = false;
	let loadError = '';
	let selectedClassroom = initialClassroomId || 'all';
	let selectedAssignment = initialAssignmentId || 'all';
	let onlySuspected = false;
	let onlyBursts = false;
	let sortBy = 'latest';
	let classrooms = [];
	let assignments = [];
	let loadSeq = 0;
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	$: scoped = Boolean(assignmentId);
	// 作业下拉跟着班级走,选了班级就只列那个班的作业。
	$: assignmentOptions = assignments.filter(
		(item) => selectedClassroom === 'all' || item.classroom?.id === selectedClassroom
	);

	const buildQueryParams = (offset: number) => ({
		review_status: status === 'all' || status === 'unsubmitted' ? undefined : status,
		classroom_id: scoped || selectedClassroom === 'all' ? undefined : selectedClassroom,
		assignment_id: scoped
			? assignmentId
			: selectedAssignment === 'all'
				? undefined
				: selectedAssignment,
		sort: sortBy,
		only_suspected: onlySuspected ? true : undefined,
		only_bursts: onlyBursts ? true : undefined,
		limit: PAGE_SIZE,
		offset
	});

	export const reload = async () => {
		if (status === 'unsubmitted') return;
		const seq = ++loadSeq;
		loading = true;
		try {
			const res = await getTeacherReview(localStorage.token, buildQueryParams(0));
			if (seq !== loadSeq) return;
			items = res.items ?? [];
			total = res.total ?? items.length;
			loadError = '';
		} catch (error) {
			if (seq !== loadSeq) return;
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			if (seq === loadSeq) loading = false;
		}
	};

	const loadMore = async () => {
		const seq = loadSeq;
		loadingMore = true;
		try {
			const res = await getTeacherReview(localStorage.token, buildQueryParams(items.length));
			if (seq !== loadSeq) return;
			items = [...items, ...(res.items ?? [])];
			total = res.total ?? total;
		} catch (error) {
			if (seq !== loadSeq) return;
			toast.error(resolveErrorMessage(error, t));
		} finally {
			if (seq === loadSeq) loadingMore = false;
		}
	};

	const selectStatus = (value: typeof status) => {
		if (status === value) return;
		status = value;
		reload();
	};

	const selectClassroom = () => {
		if (
			selectedAssignment !== 'all' &&
			!assignmentOptions.some((item) => item.assignment.id === selectedAssignment)
		) {
			selectedAssignment = 'all';
		}
		reload();
	};

	const clearSubmissionNotifications = async () => {
		try {
			await markEducationNotificationsRead(localStorage.token, {
				...(scoped ? { assignment_id: assignmentId } : {}),
				types: ['submission_created']
			});
			educationNotificationSummary.set(
				await getEducationNotificationSummary(localStorage.token).catch(() => null)
			);
		} catch (error) {
			console.error('Failed to mark education notifications as read:', error);
		}
	};

	const openSubmission = (submissionId: string) => goto(`/teacher/submissions/${submissionId}`);

	onMount(async () => {
		await reload();
		if (!scoped) {
			getTeacherClassrooms(localStorage.token)
				.then((res) => (classrooms = res ?? []))
				.catch(() => {});
			getTeacherAssignments(localStorage.token)
				.then((res) => (assignments = res ?? []))
				.catch(() => {});
		}
		await clearSubmissionNotifications();

		// 新提交通知到达时自动刷新;summary 里没有未读提交就跳过,避免 mark-read 回写触发循环
		unsubscribeNotifications = educationNotificationSummary.subscribe((summary) => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			if ((summary?.by_type?.submission_created ?? 0) === 0) return;
			reload();
			clearSubmissionNotifications();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});
</script>

<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
	<div class="flex flex-wrap gap-2">
		{#each STATUS_TABS as tab}
			<button class={eduSegmentClass(status === tab.value)} on:click={() => selectStatus(tab.value)}>
				{$i18n.t(tab.label)}
			</button>
		{/each}
		{#if unsubmittedCount !== null}
			<button
				class={eduSegmentClass(status === 'unsubmitted')}
				on:click={() => selectStatus('unsubmitted')}
			>
				{$i18n.t('Unsubmitted')} ({unsubmittedCount})
			</button>
		{/if}
	</div>

	{#if status !== 'unsubmitted'}
		<div class="flex flex-wrap items-center gap-2 text-sm">
			{#if !scoped}
				<select
					class="rounded-full border border-gray-300 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-850"
					aria-label={$i18n.t('Classroom')}
					bind:value={selectedClassroom}
					on:change={selectClassroom}
				>
					<option value="all">{$i18n.t('All Classrooms')}</option>
					{#each classrooms as item}
						<option value={item.classroom.id}>{getClassroomDisplayName(item.classroom.name, t)}</option>
					{/each}
				</select>
				<select
					class="max-w-56 rounded-full border border-gray-300 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-850"
					aria-label={$i18n.t('Assignment')}
					bind:value={selectedAssignment}
					on:change={() => reload()}
				>
					<option value="all">{$i18n.t('All Assignments')}</option>
					{#each assignmentOptions as item}
						<option value={item.assignment.id}>{item.assignment.title}</option>
					{/each}
				</select>
			{/if}
			<select
				class="rounded-full border border-gray-300 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-850"
				aria-label={$i18n.t('Sort')}
				bind:value={sortBy}
				on:change={() => reload()}
			>
				<option value="latest">{$i18n.t('Sort by Latest')}</option>
				<option value="suspected">{$i18n.t('Sort by Suspected Imports')}</option>
				<option value="burst">{$i18n.t('Sort by Large Bursts')}</option>
			</select>
			<button
				class={eduFilterClass(onlySuspected, 'rose')}
				aria-pressed={onlySuspected}
				on:click={() => {
					onlySuspected = !onlySuspected;
					reload();
				}}
			>
				{$i18n.t('Only Suspected Imports')}
			</button>
			<button
				class={eduFilterClass(onlyBursts, 'amber')}
				aria-pressed={onlyBursts}
				on:click={() => {
					onlyBursts = !onlyBursts;
					reload();
				}}
			>
				{$i18n.t('Only Large Bursts')}
			</button>
		</div>
	{/if}
</div>

{#if status === 'unsubmitted'}
	<slot name="unsubmitted" />
{:else if loadError}
	<EduStateCard tone="error">{loadError}</EduStateCard>
{:else if loading}
	<EduStateCard>{$i18n.t('Loading review queue...')}</EduStateCard>
{:else if items.length === 0}
	<EduStateCard>
		{status === 'pending'
			? $i18n.t('Nothing waiting for review.')
			: $i18n.t('No submissions match the current filters.')}
	</EduStateCard>
{:else}
	<div class="mb-2 text-xs text-gray-500 dark:text-gray-400">
		{$i18n.t('{{count}} submissions', { count: total })}
	</div>
	<EduCard padding="none">
		<div class="overflow-x-auto">
			<table class="w-full min-w-[44rem] text-sm">
				<thead class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
					<tr>
						<th class="px-4 py-2.5 font-medium">{$i18n.t('Student')}</th>
						<th class="px-4 py-2.5 font-medium">{$i18n.t('Submitted At')}</th>
						<th class="px-4 py-2.5 font-medium">{$i18n.t('Status')}</th>
						<th class="px-4 py-2.5 font-medium">{$i18n.t('Process Signals')}</th>
						<th class="px-4 py-2.5 font-medium">{$i18n.t('AI Use')}</th>
						<th class="w-8"></th>
					</tr>
				</thead>
				<tbody>
					{#each items as item (item.submission.id)}
						<tr
							class="cursor-pointer border-t border-gray-100 transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
							on:click={() => openSubmission(item.submission.id)}
						>
							<td class="px-4 py-3">
								<a
									href={`/teacher/submissions/${item.submission.id}`}
									class="font-medium text-gray-900 hover:underline dark:text-gray-100"
									on:click|stopPropagation
								>
									{item.student_name}
								</a>
								{#if item.submission.round_no > 1}
									<EduBadge soft tone="sky" class="ml-1.5">
										{$i18n.t('Round {{round}}', { round: item.submission.round_no })}
									</EduBadge>
								{/if}
								{#if !scoped}
									<div class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">
										{item.assignment.title}
										{#if item.classroom}
											· {getClassroomDisplayName(item.classroom.name, t)}
										{/if}
									</div>
								{/if}
							</td>
							<td
								class="whitespace-nowrap px-4 py-3 text-gray-600 dark:text-gray-300"
								title={formatEpoch(item.submission.submitted_at)}
							>
								{formatRelative(item.submission.submitted_at)}
							</td>
							<td class="whitespace-nowrap px-4 py-3">
								<EduBadge soft tone={STATUS_TONES[item.review_status] ?? 'gray'}>
									{getReviewStatusLabel(item.review_status, t)}
								</EduBadge>
								{#if item.review_status === 'reviewed' && item.score !== null && item.score !== undefined}
									<span class="ml-1.5 tabular-nums text-gray-700 dark:text-gray-200">
										{item.score}/{item.assignment.score_max}
									</span>
								{/if}
							</td>
							<td class="px-4 py-3">
								<EduRiskBadges summary={item.risk_summary} />
								{#if !(item.risk_summary?.suspected_unmarked_import_count || item.risk_summary?.burst_count || item.risk_summary?.ai_pasted_chars)}
									<span class="text-gray-300 dark:text-gray-600">—</span>
								{/if}
							</td>
							<td class="whitespace-nowrap px-4 py-3 text-gray-600 dark:text-gray-300">
								{item.reflection
									? item.reflection.ai_used
										? $i18n.t('Used AI')
										: $i18n.t('Did not use AI')
									: '—'}
							</td>
							<td class="pr-4 text-gray-300 dark:text-gray-600" aria-hidden="true">&rsaquo;</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</EduCard>

	{#if items.length < total}
		<div class="mt-6 flex justify-center">
			<EduButton disabled={loadingMore} on:click={loadMore}>
				{loadingMore ? $i18n.t('Loading...') : $i18n.t('Load More')}
				({items.length}/{total})
			</EduButton>
		</div>
	{/if}
{/if}
