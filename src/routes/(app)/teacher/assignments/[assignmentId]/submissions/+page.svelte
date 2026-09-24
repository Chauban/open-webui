<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		getAssignmentUnsubmittedStudents,
		getTeacherAssignment,
		grantAssignmentExtension,
		remindUnsubmittedStudents,
		revokeAssignmentExtension
	} from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import SubmissionQueue from '$lib/components/education/SubmissionQueue.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduDateTimeField from '$lib/components/education/EduDateTimeField.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { assignmentTabs } from '$lib/components/education/teacher-nav';
	import { formatEpoch, resolveErrorMessage, toLocalDateTimeInput } from '$lib/utils/education';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const assignmentId = $page.params.assignmentId;
	const QUEUE_STATUSES = ['pending', 'returned', 'reviewed', 'all', 'unsubmitted'];
	const requestedStatus = $page.url.searchParams.get('status') ?? '';
	let status = (QUEUE_STATUSES.includes(requestedStatus) ? requestedStatus : 'pending') as
		| 'pending'
		| 'returned'
		| 'reviewed'
		| 'all'
		| 'unsubmitted';

	let assignmentItem = null;
	let unsubmitted = [];
	let remindingAll = false;
	let remindingIds = new Set();
	// 个人延期:一次只展开一行,编辑中的值不落在 unsubmitted 数组里,重载列表不会串行。
	let extendingId = '';
	let extendDueAt = '';
	let extendReason = '';
	let savingExtension = false;

	const loadUnsubmitted = async () => {
		unsubmitted = await getAssignmentUnsubmittedStudents(localStorage.token, assignmentId).catch(
			() => []
		);
	};

	const remindAll = async () => {
		remindingAll = true;
		try {
			const result = await remindUnsubmittedStudents(localStorage.token, assignmentId);
			toast.success(t('Reminder sent to {{count}} students.', { count: result.reminded_count }));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			remindingAll = false;
		}
	};

	const remindOne = async (userId: string) => {
		remindingIds = new Set([...remindingIds, userId]);
		try {
			await remindUnsubmittedStudents(localStorage.token, assignmentId, { user_ids: [userId] });
			toast.success(t('Reminder sent.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			remindingIds = new Set([...remindingIds].filter((id) => id !== userId));
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
			await grantAssignmentExtension(localStorage.token, assignmentId, userId, {
				due_at: Math.floor(new Date(extendDueAt).getTime() / 1000),
				reason: extendReason.trim() || null
			});
			toast.success(t('Extension saved.'));
			closeExtension();
			await loadUnsubmitted();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingExtension = false;
		}
	};

	const revokeExtension = async (userId: string) => {
		savingExtension = true;
		try {
			await revokeAssignmentExtension(localStorage.token, assignmentId, userId);
			toast.success(t('Extension removed.'));
			closeExtension();
			await loadUnsubmitted();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			savingExtension = false;
		}
	};

	onMount(async () => {
		const [item] = await Promise.all([
			getTeacherAssignment(localStorage.token, assignmentId).catch((error) => {
				toast.error(resolveErrorMessage(error, t));
				return null;
			}),
			loadUnsubmitted()
		]);
		assignmentItem = item;
	});
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Assignments'), href: '/teacher/assignments' }]}
	title={assignmentItem?.assignment?.title ?? ''}
	tabs={assignmentTabs(assignmentId)}
>
	<div class="mx-auto max-w-6xl px-4 py-6">
		<SubmissionQueue {assignmentId} bind:status unsubmittedCount={unsubmitted.length}>
			<EduCard slot="unsubmitted" padding="none">
				<div
					class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-4 py-3 dark:border-gray-800"
				>
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
					<div class="overflow-x-auto">
						<table class="w-full min-w-[40rem] text-sm">
							<thead
								class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
							>
								<tr>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Student')}</th>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Email')}</th>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Due')}</th>
									<th class="px-4 py-2.5 font-medium">{$i18n.t('Actions')}</th>
								</tr>
							</thead>
							<tbody>
								{#each unsubmitted as student}
									<tr class="border-t border-gray-100 dark:border-gray-800">
										<td class="px-4 py-3 font-medium">{student.user_name}</td>
										<td class="truncate px-4 py-3 text-gray-500 dark:text-gray-400">
											{student.user_email ?? '—'}
										</td>
										<td class="px-4 py-3">
											<div
												class={student.extension
													? 'text-emerald-700 dark:text-emerald-300'
													: 'text-gray-500 dark:text-gray-400'}
											>
												{formatEpoch(student.effective_due_at) || '—'}
											</div>
											{#if student.extension}
												<div class="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400">
													{$i18n.t('Extended')}{student.extension.reason
														? ` · ${student.extension.reason}`
														: ''}
												</div>
											{/if}
										</td>
										<td class="px-4 py-3">
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
										<tr class="bg-gray-50 dark:bg-gray-800/60">
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
													{$i18n.t('Only this student is affected. The class due time stays unchanged.')}
												</div>
											</td>
										</tr>
									{/if}
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</EduCard>
		</SubmissionQueue>
	</div>
</TeacherPageShell>
