<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import { getTeacherOverview } from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduRiskBadges from '$lib/components/education/EduRiskBadges.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import {
		formatEpoch,
		getClassroomDisplayName,
		getReviewStatusLabel,
		resolveErrorMessage
	} from '$lib/utils/education';

	dayjs.extend(relativeTime);

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	// 相对时间跟随界面语言：dayjs 默认只有英文，中文界面里会渲染成 "2 hours ago"。
	// 语言包里没有的地区变体 dayjs 会自己降为基础语种（en-US → en）。
	$: formatRelative = (timestamp: number) =>
		dayjs(timestamp * 1000)
			.locale($i18n.language)
			.fromNow();

	const DAY_MS = 24 * 60 * 60 * 1000;

	const REVIEW_STATUS_TONES = {
		pending: 'amber',
		reviewed: 'emerald',
		returned: 'sky'
	};

	let overview = null;
	let loading = true;
	let loadError = '';
	let unsubscribeNotifications;
	let notificationsInitialized = false;

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

<TeacherPageShell title="Overview">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-8 text-sm text-gray-500 dark:text-gray-400">
			{$i18n.t('Track classroom activity, assignments, and recent submissions from one place.')}
		</div>

		<TeacherSectionNav />

		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading teaching overview...')}</EduStateCard>
		{:else}
			<div class="mb-8 grid gap-4 md:grid-cols-4">
				<EduStatCard
					label="Classrooms"
					value={overview.classroom_count}
					hint="Classrooms you manage"
				/>
				<EduStatCard
					label="Assignments"
					value={overview.assignment_count}
					hint="Assignments you published"
				/>
				<EduStatCard
					label="To Review"
					value={overview.pending_review_count}
					hint="Submissions awaiting feedback"
				/>
				<EduStatCard
					label="Unsubmitted"
					value={overview.unsubmitted_count}
					hint="Student-assignment pairs not submitted"
				/>
			</div>

			<EduCard class="mb-8">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Recent Submissions')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/review')}>
						{$i18n.t('Open review queue')}
					</EduButton>
				</div>
				{#if overview.recent_submissions.length === 0}
					<EduEmpty>{$i18n.t('No submissions yet.')}</EduEmpty>
				{:else}
					<div class="space-y-3">
						{#each overview.recent_submissions as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
							>
								<div class="flex flex-wrap items-center gap-2">
									<span class="font-medium text-gray-900 dark:text-gray-100">
										{item.student_name}
									</span>
									<span class="text-gray-400 dark:text-gray-500">·</span>
									<span class="text-gray-500 dark:text-gray-400">{item.assignment.title}</span>
									<EduBadge soft tone={REVIEW_STATUS_TONES[item.review_status] ?? 'gray'}>
										{getReviewStatusLabel(item.review_status, t)}
									</EduBadge>
								</div>
								<div class="mt-2 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
									<div>
										{item.classroom
											? getClassroomDisplayName(item.classroom.name, t)
											: t('Unknown')}
									</div>
									<div title={formatEpoch(item.submission.submitted_at)}>
										{formatRelative(item.submission.submitted_at)}
									</div>
								</div>
								<EduRiskBadges class="mt-3" summary={item.risk_summary} showClear />
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>

			<EduCard class="mb-8">
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Assignments')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/assignments')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.recent_assignments.length === 0}
					<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.recent_assignments as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}
							>
								<div class="font-medium text-gray-900 dark:text-gray-100">
									{item.assignment.title}
								</div>
								<div class="mt-1 text-gray-500 dark:text-gray-400">
									{item.classroom
										? getClassroomDisplayName(item.classroom.name, t)
										: t('Unassigned classroom')}
								</div>
								<div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
									{#if item.assignment.due_at}
										<EduBadge
											soft
											tone={item.assignment.due_at * 1000 - Date.now() < DAY_MS ? 'amber' : 'gray'}
											title={formatEpoch(item.assignment.due_at)}
										>
											{$i18n.t('Due')}
											{formatRelative(item.assignment.due_at)}
										</EduBadge>
									{/if}
									<div class="text-gray-500 dark:text-gray-400">
										{$i18n.t('Submissions')}: {item.submission_count}/{item.student_count}
									</div>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>

			<EduCard>
				<div class="mb-4 flex items-center justify-between">
					<div class="text-sm font-semibold">{$i18n.t('Classrooms')}</div>
					<EduButton variant="link" on:click={() => goto('/teacher/classrooms')}>
						{$i18n.t('View all')}
					</EduButton>
				</div>
				{#if overview.classrooms.length === 0}
					<EduEmpty>{$i18n.t('No classrooms yet.')}</EduEmpty>
				{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
						{#each overview.classrooms as item}
							<EduTile
								interactive
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}
							>
								<div class="font-medium text-gray-900 dark:text-gray-100">
									{getClassroomDisplayName(item.classroom.name, t)}
								</div>
								<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Assignments')}: {item.assignment_count}</div>
								</div>
							</EduTile>
						{/each}
					</div>
				{/if}
			</EduCard>
		{/if}
	</div>
</TeacherPageShell>
