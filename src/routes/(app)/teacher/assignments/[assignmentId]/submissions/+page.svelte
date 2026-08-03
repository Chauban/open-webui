<script lang="ts">
	// @ts-nocheck
	import { getContext, onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		getAssignmentUnsubmittedStudents,
		getTeacherSubmissions,
		getEducationNotificationSummary,
		markEducationNotificationsRead,
		remindUnsubmittedStudents
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { eduSegmentClass } from '$lib/components/education/styles';
	import { getAiHelpTypeLabel, getReviewStatusLabel } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let items = [];
	let unsubmitted = [];
	let loaded = false;
	let loadError = '';
	let selectedStatus = 'all';
	let remindingAll = false;
	let remindingIds = new Set();
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	$: filteredItems = items.filter((item) =>
		selectedStatus === 'all' ? true : item.review_status === selectedStatus
	);

	const loadData = async () => {
		try {
			[items, unsubmitted] = await Promise.all([
				getTeacherSubmissions(localStorage.token, $page.params.assignmentId),
				getAssignmentUnsubmittedStudents(localStorage.token, $page.params.assignmentId).catch(
					() => []
				)
			]);
			loadError = '';
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loaded = true;
		}
	};

	const remindAll = async () => {
		remindingAll = true;
		try {
			const result = await remindUnsubmittedStudents(
				localStorage.token,
				$page.params.assignmentId
			);
			toast.success(t('Reminder sent to {{count}} students.', { count: result.reminded_count }));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			remindingAll = false;
		}
	};

	const remindOne = async (userId: string) => {
		remindingIds = new Set([...remindingIds, userId]);
		try {
			await remindUnsubmittedStudents(localStorage.token, $page.params.assignmentId, {
				user_ids: [userId]
			});
			toast.success(t('Reminder sent.'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			remindingIds = new Set([...remindingIds].filter((id) => id !== userId));
		}
	};

	onMount(async () => {
		await loadData();

		try {
			await markEducationNotificationsRead(localStorage.token, {
				assignment_id: $page.params.assignmentId,
				types: ['submission_created']
			});
			educationNotificationSummary.set(
				await getEducationNotificationSummary(localStorage.token).catch(() => null)
			);
		} catch (error) {
			console.error('Failed to mark education notifications as read:', error);
		}

		// 新提交到达时自动刷新列表;仅在存在未读提交通知时触发,避免 mark-read 回写循环
		unsubscribeNotifications = educationNotificationSummary.subscribe((summary) => {
			if (!notificationsInitialized) {
				notificationsInitialized = true;
				return;
			}
			if ((summary?.by_type?.submission_created ?? 0) === 0) {
				return;
			}
			loadData();
			markEducationNotificationsRead(localStorage.token, {
				assignment_id: $page.params.assignmentId,
				types: ['submission_created']
			})
				.then(async () => {
					educationNotificationSummary.set(
						await getEducationNotificationSummary(localStorage.token).catch(() => null)
					);
				})
				.catch(() => {});
		});
	});

	onDestroy(() => {
		unsubscribeNotifications?.();
	});
</script>

<TeacherPageShell title="Assignments">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<TeacherSectionNav />

	<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
		<div>
			<div class="text-xs uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400">{$i18n.t('Teacher Review')}</div>
			<h1 class="text-2xl font-semibold">{$i18n.t('Submissions')}</h1>
		</div>
		<div class="flex gap-2">
			<EduButton on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}`)}>
				{$i18n.t('Assignment')}
			</EduButton>
			<EduButton
				on:click={() => goto(`/teacher/assignments/${$page.params.assignmentId}/dashboard`)}
			>
				{$i18n.t('Dashboard')}
			</EduButton>
		</div>
	</div>

	<div class="mb-6 flex flex-wrap gap-2">
		<button class={eduSegmentClass(selectedStatus === 'all')} on:click={() => (selectedStatus = 'all')}>
			{$i18n.t('All')}
		</button>
		<button
			class={eduSegmentClass(selectedStatus === 'pending')}
			on:click={() => (selectedStatus = 'pending')}
		>
			{$i18n.t('To Review')}
		</button>
		<button
			class={eduSegmentClass(selectedStatus === 'reviewed')}
			on:click={() => (selectedStatus = 'reviewed')}
		>
			{$i18n.t('Reviewed')}
		</button>
		<button
			class={eduSegmentClass(selectedStatus === 'unsubmitted')}
			on:click={() => (selectedStatus = 'unsubmitted')}
		>
			{$i18n.t('Unsubmitted')} ({unsubmitted.length})
		</button>
	</div>

	{#if loaded && !loadError}
		{#if selectedStatus === 'unsubmitted'}
			<EduCard padding="none">
				<div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 dark:border-gray-800 px-4 py-3">
					<div class="text-sm text-gray-600 dark:text-gray-400">
						{$i18n.t('{{count}} students have not submitted yet.', { count: unsubmitted.length })}
					</div>
					{#if unsubmitted.length > 0}
						<EduButton variant="primary" disabled={remindingAll} on:click={remindAll}>
							{remindingAll ? $i18n.t('Sending...') : $i18n.t('Remind All')}
						</EduButton>
					{/if}
				</div>
				{#if unsubmitted.length === 0}
					<div class="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('Everyone has submitted. Nice!')}
					</div>
				{:else}
					<table class="w-full table-fixed">
						<thead class="bg-gray-50 dark:bg-gray-800 text-left text-sm text-gray-600 dark:text-gray-400">
							<tr>
								<th class="px-4 py-3">{$i18n.t('Student')}</th>
								<th class="px-4 py-3">{$i18n.t('Email')}</th>
								<th class="px-4 py-3">{$i18n.t('Actions')}</th>
							</tr>
						</thead>
						<tbody>
							{#each unsubmitted as student}
								<tr class="border-t border-gray-100 dark:border-gray-800 text-sm">
									<td class="px-4 py-4">{student.user_name}</td>
									<td class="truncate px-4 py-4 text-gray-500 dark:text-gray-400">{student.user_email ?? '-'}</td>
									<td class="px-4 py-4">
										<EduButton
											size="sm"
											disabled={remindingIds.has(student.user_id)}
											on:click={() => remindOne(student.user_id)}
										>
											{remindingIds.has(student.user_id)
												? $i18n.t('Sending...')
												: $i18n.t('Remind')}
										</EduButton>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</EduCard>
		{:else if filteredItems.length === 0}
			<EduStateCard>{$i18n.t('No submissions match the current filters.')}</EduStateCard>
		{:else}
			<EduCard padding="none">
				<table class="w-full table-fixed">
					<thead class="bg-gray-50 dark:bg-gray-800 text-left text-sm text-gray-600 dark:text-gray-400">
						<tr>
							<th class="px-4 py-3">{$i18n.t('Student')}</th>
							<th class="px-4 py-3">{$i18n.t('Submitted At')}</th>
							<th class="px-4 py-3">{$i18n.t('AI Help')}</th>
							<th class="px-4 py-3">{$i18n.t('Status')}</th>
							<th class="px-4 py-3">{$i18n.t('Open')}</th>
						</tr>
					</thead>
					<tbody>
						{#each filteredItems as item}
							<tr class="border-t border-gray-100 dark:border-gray-800 text-sm">
								<td class="px-4 py-4">{item.student_name}</td>
								<td class="px-4 py-4">{new Date(item.submission.submitted_at * 1000).toLocaleString()}</td>
								<td class="px-4 py-4">
									{item.reflection?.ai_help_types?.length
										? item.reflection.ai_help_types.map(getAiHelpTypeLabel).join(' / ')
										: '-'}
								</td>
								<td class="px-4 py-4">{getReviewStatusLabel(item.review_status, t)}</td>
								<td class="px-4 py-4">
									<EduButton
										variant="primary"
										size="sm"
										on:click={() => goto(`/teacher/submissions/${item.submission.id}`)}
									>
										{$i18n.t('View')}
									</EduButton>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</EduCard>
		{/if}
	{:else if loaded && loadError}
		<EduStateCard tone="error">{loadError}</EduStateCard>
	{/if}
	</div>
</TeacherPageShell>
