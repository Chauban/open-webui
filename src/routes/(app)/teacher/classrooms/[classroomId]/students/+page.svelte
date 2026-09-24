<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';
	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';

	import {
		bulkImportClassroomMembers,
		bulkRemoveClassroomMembers,
		addClassroomMember,
		getClassroomMembers,
		getTeacherClassroom,
		getTeacherClassrooms,
		removeClassroomMember,
		transferClassroomMembers
	} from '$lib/apis/education';
	import { searchUsers } from '$lib/apis/users';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import EduActionMenu from '$lib/components/education/EduActionMenu.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import { classroomTabs } from '$lib/components/education/teacher-nav';
	import { formatEpoch, getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';

	// 名单放第一位,每人带上「交了几份、有几份待批、平均分、最近一次提交」,
	// 老师一眼看出谁掉队了;添加/批量导入是低频操作,收进弹窗。

	dayjs.extend(relativeTime);

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	const classroomId = $page.params.classroomId;

	let classroom = null;
	let members = [];
	let otherClassrooms = [];
	let loading = true;
	let loadError = '';
	let selectedIds = new Set<string>();
	let transferTargetId = '';
	let pendingRemoveId = '';
	let showRemoveConfirm = false;
	let showBulkRemoveConfirm = false;
	let showTransferConfirm = false;

	let showAdd = false;
	let addMode: 'search' | 'import' = 'search';
	let memberQuery = '';
	let searchResults = [];
	let searched = false;
	let searching = false;
	let addingStudentId = '';
	let bulkImportInput = '';
	let bulkImportResult = null;
	let importing = false;

	type SortKey = 'name' | 'submitted' | 'pending' | 'score' | 'latest';
	let sortKey: SortKey = 'name';
	let sortDesc = false;

	const COLUMNS: Array<{ key: SortKey; label: string; align: string }> = [
		{ key: 'name', label: 'Student', align: '' },
		{ key: 'submitted', label: 'Submitted', align: 'text-right' },
		{ key: 'pending', label: 'To Review', align: 'text-right' },
		{ key: 'score', label: 'Average Score (%)', align: 'text-right' },
		{ key: 'latest', label: 'Latest Submission', align: '' }
	];

	const sortValue = (item, key: SortKey) => {
		switch (key) {
			case 'submitted':
				return item.submitted_count;
			case 'pending':
				return item.pending_review_count;
			case 'score':
				return item.average_score_percent ?? -1;
			case 'latest':
				return item.latest_submitted_at ?? 0;
			default:
				return item.user_name ?? '';
		}
	};

	const setSort = (key: SortKey) => {
		if (sortKey === key) {
			sortDesc = !sortDesc;
		} else {
			sortKey = key;
			sortDesc = key !== 'name';
		}
	};

	$: sortedMembers = [...members].sort((a, b) => {
		const left = sortValue(a, sortKey);
		const right = sortValue(b, sortKey);
		const order =
			typeof left === 'string' ? left.localeCompare(right as string) : (left as number) - (right as number);
		return sortDesc ? -order : order;
	});
	$: allSelected = members.length > 0 && selectedIds.size === members.length;

	const reloadMembers = async () => {
		members = await getClassroomMembers(localStorage.token, classroomId);
		const ids = new Set(members.map((item) => item.member.user_id));
		selectedIds = new Set([...selectedIds].filter((id) => ids.has(id)));
	};

	const toggleSelected = (userId: string) => {
		const next = new Set(selectedIds);
		if (next.has(userId)) next.delete(userId);
		else next.add(userId);
		selectedIds = next;
	};

	const toggleSelectAll = () => {
		selectedIds = allSelected ? new Set() : new Set(members.map((item) => item.member.user_id));
	};

	const searchStudents = async () => {
		const query = memberQuery.trim();
		if (!query) {
			searchResults = [];
			searched = false;
			return;
		}
		if (searching) return;

		searching = true;
		try {
			const result = await searchUsers(localStorage.token, query, 'name', 'asc', 1);
			const existingMemberIds = new Set(members.map((item) => item.member.user_id));
			searchResults = (result?.users ?? []).filter(
				(item) =>
					item?.role !== 'pending' &&
					item?.role !== 'admin' &&
					item?.education_role === 'student' &&
					!existingMemberIds.has(item.id)
			);
			searched = true;
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			searching = false;
		}
	};

	const addStudent = async (studentId: string) => {
		if (addingStudentId) return;

		addingStudentId = studentId;
		try {
			await addClassroomMember(localStorage.token, classroomId, {
				user_id: studentId,
				member_role: 'student'
			});
			searchResults = searchResults.filter((item) => item.id !== studentId);
			await reloadMembers();
			toast.success(t('Student added.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			addingStudentId = '';
		}
	};

	const bulkImportStudents = async () => {
		const lines = bulkImportInput
			.split(/\r?\n/)
			.map((item) => item.trim())
			.filter(Boolean);
		if (!lines.length) {
			toast.error(t('Please enter at least one student email or ID.'));
			return;
		}
		if (importing) return;

		importing = true;
		try {
			const result = await bulkImportClassroomMembers(localStorage.token, classroomId, {
				emails: lines.filter((item) => item.includes('@')),
				user_ids: lines.filter((item) => !item.includes('@'))
			});
			bulkImportResult = result;
			await reloadMembers();
			bulkImportInput = '';
			toast.success(
				t('Bulk import summary: {{added}} added, {{skipped}} skipped, {{failed}} failed.', {
					added: result.added_count,
					skipped: result.skipped_count,
					failed: result.failed_count
				})
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			importing = false;
		}
	};

	const requestRemoveStudent = (studentId: string) => {
		pendingRemoveId = studentId;
		showRemoveConfirm = true;
	};

	const removeStudent = async () => {
		if (!pendingRemoveId) return;
		try {
			await removeClassroomMember(localStorage.token, classroomId, pendingRemoveId);
			await reloadMembers();
			toast.success(t('Student removed.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			pendingRemoveId = '';
		}
	};

	const bulkRemoveSelected = async () => {
		try {
			const result = await bulkRemoveClassroomMembers(localStorage.token, classroomId, {
				user_ids: [...selectedIds]
			});
			toast.success(t('{{count}} students removed.', { count: result.affected_count }));
			selectedIds = new Set();
			await reloadMembers();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const transferSelected = async () => {
		if (!transferTargetId) return;
		try {
			const result = await transferClassroomMembers(localStorage.token, classroomId, {
				user_ids: [...selectedIds],
				target_classroom_id: transferTargetId
			});
			toast.success(t('{{count}} students transferred.', { count: result.affected_count }));
			selectedIds = new Set();
			await reloadMembers();
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	};

	const openAdd = (mode: 'search' | 'import') => {
		addMode = mode;
		bulkImportResult = null;
		showAdd = true;
	};

	onMount(async () => {
		try {
			const [classroomResponse] = await Promise.all([
				getTeacherClassroom(localStorage.token, classroomId),
				reloadMembers()
			]);
			classroom = classroomResponse.classroom;
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
			toast.error(loadError);
		} finally {
			loading = false;
		}
		getTeacherClassrooms(localStorage.token)
			.then((res) => {
				otherClassrooms = (res ?? []).filter((item) => item.classroom.id !== classroomId);
				transferTargetId = otherClassrooms[0]?.classroom?.id ?? '';
			})
			.catch(() => {});
	});
</script>

<TeacherPageShell
	crumbs={[{ label: $i18n.t('Classrooms'), href: '/teacher/classrooms' }]}
	title={classroom ? getClassroomDisplayName(classroom.name, t) : ''}
	tabs={classroomTabs(classroomId)}
>
	<svelte:fragment slot="nav-actions">
		{#if classroom}
			<EduButton variant="primary" size="sm" on:click={() => openAdd('search')}>
				{$i18n.t('Add Student')}
			</EduButton>
		{/if}
	</svelte:fragment>

	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loading}
			<EduStateCard>{$i18n.t('Loading students...')}</EduStateCard>
		{:else if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if members.length === 0}
			<EduCard class="text-center">
				<div class="text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('No students in this classroom yet.')}
				</div>
				<div class="mt-4 flex justify-center gap-2">
					<EduButton variant="primary" on:click={() => openAdd('search')}>
						{$i18n.t('Add Student')}
					</EduButton>
					<EduButton on:click={() => openAdd('import')}>{$i18n.t('Bulk Import Students')}</EduButton>
				</div>
			</EduCard>
		{:else}
			{#if selectedIds.size > 0}
				<div
					class="mb-3 flex flex-wrap items-center gap-2 rounded-2xl bg-gray-900 px-4 py-2.5 text-sm text-white dark:bg-gray-100 dark:text-gray-900"
				>
					<span class="mr-auto">{$i18n.t('{{count}} selected', { count: selectedIds.size })}</span>
					{#if otherClassrooms.length > 0}
						<select
							class="rounded-full border border-white/30 bg-transparent px-3 py-1 text-xs outline-none dark:border-gray-900/30"
							aria-label={$i18n.t('Transfer Selected')}
							bind:value={transferTargetId}
						>
							{#each otherClassrooms as item}
								<option value={item.classroom.id} class="text-gray-900">
									{getClassroomDisplayName(item.classroom.name, t)}
								</option>
							{/each}
						</select>
						<button
							type="button"
							class="rounded-full border border-white/30 px-3 py-1 text-xs hover:bg-white/10 dark:border-gray-900/30"
							on:click={() => (showTransferConfirm = true)}
						>
							{$i18n.t('Transfer Selected')}
						</button>
					{/if}
					<button
						type="button"
						class="rounded-full bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700"
						on:click={() => (showBulkRemoveConfirm = true)}
					>
						{$i18n.t('Remove Selected')}
					</button>
					<button
						type="button"
						class="px-2 py-1 text-xs opacity-70 hover:opacity-100"
						on:click={() => (selectedIds = new Set())}
					>
						{$i18n.t('Cancel')}
					</button>
				</div>
			{/if}

			<EduCard padding="none">
				<div class="overflow-x-auto">
					<table class="w-full min-w-[44rem] text-sm">
						<thead class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
							<tr>
								<th class="w-10 pl-4">
									<input
										type="checkbox"
										class="accent-black dark:accent-white"
										aria-label={$i18n.t('Select All')}
										checked={allSelected}
										on:change={toggleSelectAll}
									/>
								</th>
								{#each COLUMNS as column}
									<th
										class="px-4 py-2.5 font-medium {column.align}"
										aria-sort={sortKey === column.key
											? sortDesc
												? 'descending'
												: 'ascending'
											: 'none'}
									>
										<button
											type="button"
											class="inline-flex items-center gap-1 hover:text-gray-900 dark:hover:text-gray-100"
											on:click={() => setSort(column.key)}
										>
											{$i18n.t(column.label)}
											{#if sortKey === column.key}
												<span aria-hidden="true">{sortDesc ? '↓' : '↑'}</span>
											{/if}
										</button>
									</th>
								{/each}
								<th class="w-12"></th>
							</tr>
						</thead>
						<tbody>
							{#each sortedMembers as member (member.member.user_id)}
								{@const profileHref = `/teacher/classrooms/${classroomId}/students/${member.member.user_id}`}
								<tr
									class="cursor-pointer border-t border-gray-100 transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
									on:click={() => goto(profileHref)}
								>
									<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
									<td class="pl-4" on:click|stopPropagation>
										<input
											type="checkbox"
											class="accent-black dark:accent-white"
											aria-label={member.user_name}
											checked={selectedIds.has(member.member.user_id)}
											on:change={() => toggleSelected(member.member.user_id)}
										/>
									</td>
									<td class="px-4 py-3">
										<a
											href={profileHref}
											class="font-medium text-gray-900 hover:underline dark:text-gray-100"
											on:click|stopPropagation
										>
											{member.user_name}
										</a>
										<div class="truncate text-xs text-gray-500 dark:text-gray-400">
											{member.user_email ?? ''}
										</div>
									</td>
									<td
										class="px-4 py-3 text-right tabular-nums {member.submitted_count < member.assignment_count
											? 'text-rose-600 dark:text-rose-400'
											: ''}"
									>
										{member.submitted_count}/{member.assignment_count}
									</td>
									<td class="px-4 py-3 text-right tabular-nums">
										{#if member.pending_review_count > 0}
											<span class="font-semibold text-amber-600 dark:text-amber-400">
												{member.pending_review_count}
											</span>
										{:else}
											<span class="text-gray-300 dark:text-gray-600">0</span>
										{/if}
									</td>
									<td class="px-4 py-3 text-right tabular-nums">
										{member.average_score_percent !== null && member.average_score_percent !== undefined
											? `${member.average_score_percent}%`
											: '—'}
									</td>
									<td
										class="whitespace-nowrap px-4 py-3 text-gray-600 dark:text-gray-300"
										title={member.latest_submitted_at ? formatEpoch(member.latest_submitted_at) : ''}
									>
										{member.latest_submitted_at
											? dayjs(member.latest_submitted_at * 1000)
													.locale($i18n.language)
													.fromNow()
											: '—'}
									</td>
									<td class="px-2 py-3 text-right">
										<EduActionMenu
											items={[
												{ label: 'Growth Profile', onClick: () => goto(profileHref) },
												{
													label: 'Remove from Classroom',
													danger: true,
													onClick: () => requestRemoveStudent(member.member.user_id)
												}
											]}
										/>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</EduCard>
			<div class="mt-3 text-xs text-gray-400">
				{$i18n.t(
					'Each student can be in only one classroom. A student already in another classroom must be removed there first; you can transfer students between your own classrooms, and an administrator can transfer across teachers.'
				)}
			</div>
		{/if}
	</div>

	<Modal bind:show={showAdd} size="sm">
		<div class="p-6">
			<div class="text-lg font-semibold">{$i18n.t('Add Student')}</div>
			<div class="mt-4 flex gap-2">
				<button class={eduSegmentClass(addMode === 'search')} on:click={() => (addMode = 'search')}>
					{$i18n.t('Search')}
				</button>
				<button class={eduSegmentClass(addMode === 'import')} on:click={() => (addMode = 'import')}>
					{$i18n.t('Bulk Import Students')}
				</button>
			</div>

			{#if addMode === 'search'}
				<form class="mt-4 flex gap-2" on:submit|preventDefault={searchStudents}>
					<!-- svelte-ignore a11y-autofocus -->
					<input
						bind:value={memberQuery}
						autofocus
						class="min-w-0 flex-1 {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Search by student name or email')}
					/>
					<EduButton variant="primary" type="submit" disabled={searching}>
						{searching ? $i18n.t('Searching...') : $i18n.t('Search')}
					</EduButton>
				</form>
				{#if searchResults.length > 0}
					<div class="mt-3 max-h-72 space-y-2 overflow-y-auto">
						{#each searchResults as candidate}
							<EduTile class="flex items-center justify-between gap-3">
								<div class="min-w-0">
									<div class="truncate font-medium">{candidate.name}</div>
									<div class="truncate text-xs text-gray-500 dark:text-gray-400">{candidate.email}</div>
								</div>
								<EduButton
									size="sm"
									disabled={addingStudentId !== ''}
									on:click={() => addStudent(candidate.id)}
								>
									{addingStudentId === candidate.id ? $i18n.t('Adding...') : $i18n.t('Add')}
								</EduButton>
							</EduTile>
						{/each}
					</div>
				{:else if searched}
					<div class="mt-3 text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('No matching students who can be added.')}
					</div>
				{/if}
			{:else}
				<textarea
					bind:value={bulkImportInput}
					class="mt-4 min-h-32 w-full {EDU_FIELD_CLASS}"
					placeholder={$i18n.t('Enter one student email or user ID per line')}
				></textarea>
				<div class="mt-3 flex justify-end">
					<EduButton variant="primary" disabled={importing} on:click={bulkImportStudents}>
						{importing ? $i18n.t('Importing...') : $i18n.t('Import')}
					</EduButton>
				</div>
				{#if bulkImportResult && (bulkImportResult.failed_users?.length || bulkImportResult.skipped_users?.length)}
					<div class="mt-4 max-h-60 space-y-3 overflow-y-auto">
						{#if bulkImportResult.failed_users?.length}
							<EduTile tone="rose">
								<div
									class="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-rose-600 dark:text-rose-400"
								>
									{$i18n.t('Failed')} ({bulkImportResult.failed_users.length})
								</div>
								<div class="space-y-1 text-sm text-rose-700 dark:text-rose-300">
									{#each bulkImportResult.failed_users as failure}
										<div>{failure.value} — {$i18n.t(failure.reason)}</div>
									{/each}
								</div>
							</EduTile>
						{/if}
						{#if bulkImportResult.skipped_users?.length}
							<EduTile tone="amber">
								<div
									class="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-600 dark:text-amber-400"
								>
									{$i18n.t('Skipped (already in this classroom)')} ({bulkImportResult.skipped_users.length})
								</div>
								<div class="space-y-1 text-sm text-amber-700 dark:text-amber-300">
									{#each bulkImportResult.skipped_users as skipped}
										<div>{skipped}</div>
									{/each}
								</div>
							</EduTile>
						{/if}
					</div>
				{/if}
			{/if}

			<div class="mt-6 flex justify-end">
				<EduButton on:click={() => (showAdd = false)}>{$i18n.t('Done')}</EduButton>
			</div>
		</div>
	</Modal>

	<ConfirmDialog
		bind:show={showRemoveConfirm}
		title={$i18n.t('Remove Student')}
		message={$i18n.t(
			'Remove this student from the classroom? Their submissions stay with this classroom and remain visible to you; their growth profile moves with them.'
		)}
		on:confirm={removeStudent}
	/>

	<ConfirmDialog
		bind:show={showBulkRemoveConfirm}
		title={$i18n.t('Remove Selected Students')}
		message={$i18n.t(
			'Remove {{count}} selected students from the classroom? Their submissions stay with this classroom and remain visible to you; their growth profiles move with them.',
			{ count: selectedIds.size }
		)}
		on:confirm={bulkRemoveSelected}
	/>

	<ConfirmDialog
		bind:show={showTransferConfirm}
		title={$i18n.t('Transfer Selected Students')}
		message={$i18n.t(
			'Transfer {{count}} selected students to the chosen classroom? Their submissions stay with this classroom and remain visible to you; their growth profiles move with them.',
			{ count: selectedIds.size }
		)}
		on:confirm={transferSelected}
	/>
</TeacherPageShell>
