<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import { getTeacherOverview } from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduRiskBadges from '$lib/components/education/EduRiskBadges.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import {
		formatEpoch,
		getClassroomDisplayName,
		getReviewStatusLabel,
		resolveErrorMessage
	} from '$lib/utils/education';

	// 总览回答「今天要做什么」,不是「我有什么」:每个数都能点进对应的待办列表,
	// 下面是需要跟进的作业(快截止的、截止了还有人没交或没批的)和最新提交。

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	// 相对时间跟随界面语言：dayjs 默认只有英文，中文界面里会渲染成 "2 hours ago"。
	$: formatRelative = (timestamp: number) =>
		dayjs(timestamp * 1000)
			.locale($i18n.language)
			.fromNow();

	const REVIEW_STATUS_TONES = { pending: 'amber', reviewed: 'emerald', returned: 'sky' };

	let overview = null;
	let loading = true;
	let loadError = '';
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	const isPastDue = (item) => item.assignment.due_at * 1000 < Date.now();

	const loadOverview = async () => {
		try {
			overview = await getTeacherOverview(localStorage.token);
			loadError = '';
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	onMount(async () => {
		await loadOverview();
		// 与学生端首页同一模式:收到教学通知(store 刷新)时后台重拉;跳过订阅触发的初始值
		unsubscribeNotifications = educationNotificationSummary.subscribe(() => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			loadOverview();
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});
</script>

<TeacherPageShell title={$i18n.t('Overview')}>
	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading teaching overview...')}</EduStateCard>
		{:else if overview.classroom_count === 0}
			<EduCard class="text-center">
				<div class="text-base font-semibold">{$i18n.t('Start by creating a classroom')}</div>
				<div class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Students join with its invite code; then you can publish assignments to it.')}
				</div>
				<EduButton variant="primary" class="mt-4" on:click={() => goto('/teacher/classrooms')}>
					{$i18n.t('Create Classroom')}
				</EduButton>
			</EduCard>
		{:else}
			<div class="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
				<EduStatCard
					label="To Review"
					value={overview.pending_review_count}
					tone={overview.pending_review_count > 0 ? 'amber' : 'default'}
					hint="Submissions awaiting feedback"
					href="/teacher/review?status=pending"
				/>
				<EduStatCard
					label="Returned"
					value={overview.returned_count}
					hint="Waiting for the student to resubmit"
					href="/teacher/review?status=returned"
				/>
				<EduStatCard
					label="Due Within 48 Hours"
					value={overview.due_soon_count}
					hint="Ongoing assignments closing soon"
				/>
				<EduStatCard
					label="Missing After Deadline"
					value={overview.overdue_unsubmitted_count}
					tone={overview.overdue_unsubmitted_count > 0 ? 'rose' : 'default'}
					hint="Students who have not submitted past-due work"
				/>
			</div>

			<EduCard padding="none" class="mb-6">
				<div class="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
					<h2 class="text-sm font-semibold">{$i18n.t('Assignments to Follow Up')}</h2>
					<EduButton variant="link" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.followup_assignments.length === 0}
					<div class="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('Nothing to follow up on right now.')}
					</div>
				{:else}
					<div class="divide-y divide-gray-100 dark:divide-gray-800">
						{#each overview.followup_assignments as item (item.assignment.id)}
							{@const unsubmitted = Math.max(item.student_count - item.submission_count, 0)}
							<div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-sm">
								<a href={`/teacher/assignments/${item.assignment.id}`} class="min-w-0 flex-1 hover:underline">
									<div class="truncate font-medium text-gray-900 dark:text-gray-100">
										{item.assignment.title}
									</div>
									<div class="truncate text-xs text-gray-500 dark:text-gray-400">
										{item.classroom ? getClassroomDisplayName(item.classroom.name, t) : ''}
									</div>
								</a>
								<EduBadge
									soft
									tone={isPastDue(item)
										? 'rose'
										: item.assignment.due_at * 1000 - Date.now() < 48 * 3600 * 1000
											? 'amber'
											: 'gray'}
									title={formatEpoch(item.assignment.due_at)}
								>
									{isPastDue(item) ? $i18n.t('Past Due') : $i18n.t('Due')}
									{formatRelative(item.assignment.due_at)}
								</EduBadge>
								<span class="w-16 text-right tabular-nums text-gray-600 dark:text-gray-300">
									{item.submission_count}/{item.student_count}
								</span>
								<div class="flex w-56 justify-end gap-2">
									{#if item.pending_review_count > 0}
										<EduButton
											size="sm"
											on:click={() =>
												goto(`/teacher/assignments/${item.assignment.id}/submissions?status=pending`)}
										>
											{$i18n.t('Review {{count}}', { count: item.pending_review_count })}
										</EduButton>
									{/if}
									{#if unsubmitted > 0}
										<EduButton
											size="sm"
											on:click={() =>
												goto(`/teacher/assignments/${item.assignment.id}/submissions?status=unsubmitted`)}
										>
											{$i18n.t('{{count}} missing', { count: unsubmitted })}
										</EduButton>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</EduCard>

			<EduCard padding="none">
				<div class="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
					<h2 class="text-sm font-semibold">{$i18n.t('Recent Submissions')}</h2>
					<EduButton variant="link" on:click={() => goto('/teacher/review?status=all')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.recent_submissions.length === 0}
					<div class="px-4 py-6"><EduEmpty>{$i18n.t('No submissions yet.')}</EduEmpty></div>
				{:else}
					<div class="divide-y divide-gray-100 dark:divide-gray-800">
						{#each overview.recent_submissions as item (item.submission.id)}
							<a
								href={`/teacher/submissions/${item.submission.id}`}
								class="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm transition hover:bg-gray-50 dark:hover:bg-gray-800/60"
							>
								<div class="min-w-0 flex-1">
									<span class="font-medium text-gray-900 dark:text-gray-100">{item.student_name}</span>
									<span class="text-gray-400">·</span>
									<span class="text-gray-500 dark:text-gray-400">{item.assignment.title}</span>
								</div>
								<EduRiskBadges summary={item.risk_summary} />
								<EduBadge soft tone={REVIEW_STATUS_TONES[item.review_status] ?? 'gray'}>
									{getReviewStatusLabel(item.review_status, t)}
								</EduBadge>
								<span
									class="w-24 text-right text-xs text-gray-500 dark:text-gray-400"
									title={formatEpoch(item.submission.submitted_at)}
								>
									{formatRelative(item.submission.submitted_at)}
								</span>
							</a>
						{/each}
					</div>
				{/if}
			</EduCard>
		{/if}
	</div>
</TeacherPageShell>
