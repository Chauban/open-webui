<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		getAssignmentUnsubmittedStudents,
		getTeacherSubmissions,
		getEducationNotificationSummary,
		grantAssignmentExtension,
		markEducationNotificationsRead,
		remindUnsubmittedStudents,
		revokeAssignmentExtension
	} from '$lib/apis/education';
	import { educationNotificationSummary } from '$lib/stores';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduDateTimeField from '$lib/components/education/EduDateTimeField.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import {
		formatDateTimeInput,
		formatEpoch,
		getAiHelpTypeLabel,
		getReviewStatusLabel,
		resolveErrorMessage,
		toLocalDateTimeInput
	} from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let items = [];
	let unsubmitted = [];
	let loaded = false;
	let loadError = '';
	let selectedStatus = 'all';
	let remindingAll = false;
	let remindingIds = new Set();
	// 个人延期:一次只展开一行,编辑中的值不落在 unsubmitted 数组里,重载列表不会串行。
	let extendingId = '';
	let extendDueAt = '';
	let extendReason = '';
	let savingExtension = false;
	let unsubscribeNotifications;
	let notificationsInitialized = false;

	$: filteredItems = items.filter((item) =>
		selectedStatus === 'all' ? true : item.review_status === selectedStatus
	);
	// 提交列表接口不单独回作业信息;有提交时用提交带回来的标题,一份都没有时退回通名。
	$: assignmentTitle = items[0]?.assignment?.title ?? t('Assignment');

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
			loadError = resolveErrorMessage(error, t);
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
			toast.error(resolveErrorMessage(error, t));
		} finally {
			remindingAll = false;
		}
	};

	const openExtension = (student) => {
		extendingId = student.user_id;
		extendDueAt = student.extension?.due_at ? toLocalDateTimeInput(student.extension.due_at) : '';
		extendReason = student.extension?.reason ?? '';
	};

	const closeExtension = () => {
		extendingId = '';
		extendDueAt = '';
		extendReason = '';
	};

	const saveExtension = async (userId: string) => {
		if (!extendDueAt) {
			toast.error(t('Please choose a new due time.'));
			return;
		}
		savingExtension = true;
		try {
			await grantAssignmentExtension(localStorage.token, $page.params.assignmentId, userId, {
				due_at: Math.floor(new Date(extendDueAt).getTime() / 1000),
				reason: extendReason.trim() || null
			});
			toast.success(t('Extension saved.'));
			closeExtension();
			await loadData();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingExtension = false;
		}
	};

	const revokeExtension = async (userId: string) => {
		savingExtension = true;
		try {
			await revokeAssignmentExtension(localStorage.token, $page.params.assignmentId, userId);
			toast.success(t('Extension removed.'));
			closeExtension();
			await loadData();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingExtension = false;
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
			toast.error(resolveErrorMessage(error, t));
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

<TeacherPageShell
	crumbs={[
		{ label: $i18n.t('Teaching') },
		{ label: $i18n.t('Assignments'), href: '/teacher/assignments' },
		{
			label: assignmentTitle,
			href: `/teacher/assignments/${$page.params.assignmentId}`
		}
	]}
	title={$i18n.t('Submissions')}
>
	<div class="mx-auto max-w-6xl px-4 py-8">
		<TeacherSectionNav />

	<div class="mb-6 flex flex-wrap items-center justify-end gap-3">
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
								<th class="px-4 py-3">{$i18n.t('Due')}</th>
								<th class="px-4 py-3 w-64">{$i18n.t('Actions')}</th>
							</tr>
						</thead>
						<tbody>
							{#each unsubmitted as student}
								<tr class="border-t border-gray-100 dark:border-gray-800 text-sm">
									<td class="px-4 py-4">{student.user_name}</td>
									<td class="truncate px-4 py-4 text-gray-500 dark:text-gray-400">{student.user_email ?? '-'}</td>
									<td class="px-4 py-4">
										<div class={student.extension ? 'text-emerald-700 dark:text-emerald-300' : 'text-gray-500 dark:text-gray-400'}>
											{formatEpoch(student.effective_due_at) || '-'}
										</div>
										{#if student.extension}
											<div class="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400">
												{$i18n.t('Extended')}{student.extension.reason
													? ` · ${student.extension.reason}`
													: ''}
											</div>
										{/if}
									</td>
									<td class="px-4 py-4">
										<div class="flex flex-wrap gap-2">
											<EduButton
												size="sm"
												disabled={remindingIds.has(student.user_id)}
												on:click={() => remindOne(student.user_id)}
											>
												{remindingIds.has(student.user_id)
													? $i18n.t('Sending...')
													: $i18n.t('Remind')}
											</EduButton>
											<EduButton
												size="sm"
												on:click={() =>
													extendingId === student.user_id
														? closeExtension()
														: openExtension(student)}
											>
												{student.extension ? $i18n.t('Change Due Time') : $i18n.t('Extend')}
											</EduButton>
										</div>
									</td>
								</tr>
								{#if extendingId === student.user_id}
									<tr class="bg-gray-50 dark:bg-gray-800/60 text-sm">
										<td colspan="4" class="px-4 py-4">
											<div class="flex flex-wrap items-end gap-3">
												<div class="min-w-56">
													<div class="mb-1 text-xs text-gray-500 dark:text-gray-400">
														{$i18n.t('New due time for this student')}
													</div>
													<EduDateTimeField
														bind:value={extendDueAt}
														className="w-full {EDU_FIELD_CLASS}"
													/>
													{#if formatDateTimeInput(extendDueAt)}
														<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
															{formatDateTimeInput(extendDueAt)}
														</div>
													{/if}
												</div>
												<div class="min-w-56 flex-1">
													<div class="mb-1 text-xs text-gray-500 dark:text-gray-400">
														{$i18n.t('Reason (optional)')}
													</div>
													<input
														bind:value={extendReason}
														maxlength="200"
														class="w-full {EDU_FIELD_CLASS}"
														placeholder={$i18n.t('Sick leave, device failure, ...')}
													/>
												</div>
												<div class="flex gap-2">
													<EduButton
														variant="primary"
														size="sm"
														disabled={savingExtension}
														on:click={() => saveExtension(student.user_id)}
													>
														{savingExtension ? $i18n.t('Saving...') : $i18n.t('Save')}
													</EduButton>
													{#if student.extension}
														<EduButton
															size="sm"
															disabled={savingExtension}
															on:click={() => revokeExtension(student.user_id)}
														>
															{$i18n.t('Remove Extension')}
														</EduButton>
													{/if}
													<EduButton size="sm" disabled={savingExtension} on:click={closeExtension}>
														{$i18n.t('Cancel')}
													</EduButton>
												</div>
											</div>
											<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
												{$i18n.t(
													'Only this student is affected. The class due time stays unchanged.'
												)}
											</div>
										</td>
									</tr>
								{/if}
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
								<td class="px-4 py-4">{formatEpoch(item.submission.submitted_at)}</td>
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
