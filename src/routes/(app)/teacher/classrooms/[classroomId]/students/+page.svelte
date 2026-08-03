<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

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
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { getClassroomDisplayName } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classroom = null;
	let members = [];
	let otherClassrooms = [];
	let searchResults = [];
	let memberQuery = '';
	let bulkImportInput = '';
	let bulkImportResult = null;
	let loading = true;
	let loadError = '';
	let selectedIds = new Set();
	let transferTargetId = '';
	let pendingRemoveId = '';
	let searching = false;
	let addingStudentId = '';
	let importing = false;
	let showRemoveConfirm = false;
	let showBulkRemoveConfirm = false;
	let showTransferConfirm = false;

	const classroomId = () => $page.params.classroomId;

	const loadData = async () => {
		loading = true;
		loadError = '';
		try {
			const [classroomResponse, memberList] = await Promise.all([
				getTeacherClassroom(localStorage.token, classroomId()),
				getClassroomMembers(localStorage.token, classroomId())
			]);
			classroom = classroomResponse.classroom;
			members = memberList;
			selectedIds = new Set();
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	const toggleSelected = (userId: string) => {
		const next = new Set(selectedIds);
		if (next.has(userId)) {
			next.delete(userId);
		} else {
			next.add(userId);
		}
		selectedIds = next;
	};

	const toggleSelectAll = () => {
		if (selectedIds.size === members.length) {
			selectedIds = new Set();
		} else {
			selectedIds = new Set(members.map((item) => item.member.user_id));
		}
	};

	const searchStudents = async () => {
		const query = memberQuery.trim();
		if (!query) {
			searchResults = [];
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
					item?.info?.education_role === 'student' &&
					!existingMemberIds.has(item.id)
			);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			searching = false;
		}
	};

	const addStudent = async (studentId: string) => {
		if (addingStudentId) return;

		addingStudentId = studentId;
		try {
			await addClassroomMember(localStorage.token, classroomId(), {
				user_id: studentId,
				member_role: 'student'
			});
			memberQuery = '';
			searchResults = [];
			members = await getClassroomMembers(localStorage.token, classroomId());
			toast.success(t('Student added.'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			addingStudentId = '';
		}
	};

	const requestRemoveStudent = (studentId: string) => {
		pendingRemoveId = studentId;
		showRemoveConfirm = true;
	};

	const removeStudent = async () => {
		if (!pendingRemoveId) return;
		try {
			await removeClassroomMember(localStorage.token, classroomId(), pendingRemoveId);
			members = await getClassroomMembers(localStorage.token, classroomId());
			selectedIds = new Set([...selectedIds].filter((id) => id !== pendingRemoveId));
			toast.success(t('Student removed.'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			pendingRemoveId = '';
		}
	};

	const bulkRemoveSelected = async () => {
		try {
			const result = await bulkRemoveClassroomMembers(localStorage.token, classroomId(), {
				user_ids: [...selectedIds]
			});
			toast.success(t('{{count}} students removed.', { count: result.affected_count }));
			await loadData();
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const transferSelected = async () => {
		if (!transferTargetId) return;
		try {
			const result = await transferClassroomMembers(localStorage.token, classroomId(), {
				user_ids: [...selectedIds],
				target_classroom_id: transferTargetId
			});
			toast.success(t('{{count}} students transferred.', { count: result.affected_count }));
			await loadData();
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
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
			const result = await bulkImportClassroomMembers(localStorage.token, classroomId(), {
				emails: lines.filter((item) => item.includes('@')),
				user_ids: lines.filter((item) => !item.includes('@'))
			});
			bulkImportResult = result;
			members = await getClassroomMembers(localStorage.token, classroomId());
			bulkImportInput = '';
			toast.success(
				t('Bulk import summary: {{added}} added, {{skipped}} skipped, {{failed}} failed.', {
					added: result.added_count,
					skipped: result.skipped_count,
					failed: result.failed_count
				})
			);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			importing = false;
		}
	};

	onMount(async () => {
		await loadData();
		getTeacherClassrooms(localStorage.token)
			.then((res) => {
				otherClassrooms = (res ?? []).filter((item) => item.classroom.id !== classroomId());
				transferTargetId = otherClassrooms[0]?.classroom?.id ?? '';
			})
			.catch(() => {});
	});
</script>

<TeacherPageShell title="Classrooms">
	{#if loading}
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('Loading students...')}</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
			<div>
				<div class="mb-2 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Teaching')} / {$i18n.t('Classrooms')} / {getClassroomDisplayName(classroom.name, t)}
				</div>
				<h1 class="text-3xl font-semibold">{$i18n.t('Manage Students')}</h1>
			</div>
			<EduButton on:click={() => goto(`/teacher/classrooms/${classroom.id}`)}>
				{$i18n.t('Back to Classroom')}
			</EduButton>
		</div>

		<EduCard class="mb-8">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Add Student')}</div>
			<div class="flex gap-2">
				<input
					bind:value={memberQuery}
					class="flex-1 {EDU_FIELD_CLASS}"
					placeholder={$i18n.t('Search by student name or email')}
				/>
				<EduButton variant="primary" disabled={searching} on:click={searchStudents}>
					{searching ? $i18n.t('Searching...') : $i18n.t('Search')}
				</EduButton>
			</div>

			{#if searchResults.length > 0}
				<div class="mt-3 space-y-2">
					{#each searchResults as candidate}
						<EduTile class="flex items-center justify-between">
							<div>
								<div class="font-medium">{candidate.name}</div>
								<div class="text-xs text-gray-500 dark:text-gray-400">{candidate.email}</div>
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
			{/if}
		</EduCard>

		<EduCard class="mb-8">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Bulk Import Students')}</div>
			<textarea
				bind:value={bulkImportInput}
				class="min-h-28 w-full {EDU_FIELD_CLASS}"
				placeholder={$i18n.t('Enter one student email or user ID per line')}
			></textarea>
			<div class="mt-3 flex justify-end">
				<EduButton variant="primary" disabled={importing} on:click={bulkImportStudents}>
					{importing ? $i18n.t('Importing...') : $i18n.t('Import')}
				</EduButton>
			</div>
			{#if bulkImportResult && (bulkImportResult.failed_users?.length || bulkImportResult.skipped_users?.length)}
				<div class="mt-4 space-y-3">
					{#if bulkImportResult.failed_users?.length}
						<EduTile tone="rose">
							<div class="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-rose-600 dark:text-rose-400">
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
							<div class="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-600 dark:text-amber-400">
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
		</EduCard>

		<EduCard>
			<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
				<div class="text-sm font-semibold">{$i18n.t('Current Students')} ({members.length})</div>
				{#if members.length > 0}
					<div class="flex flex-wrap items-center gap-2">
						<EduButton size="sm" on:click={toggleSelectAll}>
							{selectedIds.size === members.length ? $i18n.t('Deselect All') : $i18n.t('Select All')}
						</EduButton>
						{#if selectedIds.size > 0}
							<EduButton
								variant="danger"
								size="sm"
								on:click={() => (showBulkRemoveConfirm = true)}
							>
								{$i18n.t('Remove Selected')} ({selectedIds.size})
							</EduButton>
							{#if otherClassrooms.length > 0}
								<select
									class="rounded-full border border-gray-300 dark:border-gray-700 px-3 py-1.5 text-xs outline-none"
									bind:value={transferTargetId}
								>
									{#each otherClassrooms as item}
										<option value={item.classroom.id}>
											{getClassroomDisplayName(item.classroom.name, t)}
										</option>
									{/each}
								</select>
								<EduButton size="sm" on:click={() => (showTransferConfirm = true)}>
									{$i18n.t('Transfer Selected')} ({selectedIds.size})
								</EduButton>
							{/if}
						{/if}
					</div>
				{/if}
			</div>
			{#if members.length === 0}
				<EduEmpty>{$i18n.t('No students in this classroom yet.')}</EduEmpty>
			{:else}
				<div class="space-y-2">
					{#each members as member}
						<EduTile class="flex items-center justify-between gap-3">
							<label class="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
								<input
									type="checkbox"
									class="accent-black dark:accent-white"
									checked={selectedIds.has(member.member.user_id)}
									on:change={() => toggleSelected(member.member.user_id)}
								/>
								<div class="min-w-0">
									<div class="truncate font-medium">{member.user_name}</div>
									<div class="truncate text-xs text-gray-500 dark:text-gray-400">{member.user_email}</div>
								</div>
							</label>
							<div class="flex shrink-0 gap-2">
								<EduButton
									size="sm"
									on:click={() =>
										goto(`/teacher/classrooms/${classroom.id}/students/${member.member.user_id}`)}
								>
									{$i18n.t('Performance')}
								</EduButton>
								<EduButton
									variant="danger"
									size="sm"
									on:click={() => requestRemoveStudent(member.member.user_id)}
								>
									{$i18n.t('Remove')}
								</EduButton>
							</div>
						</EduTile>
					{/each}
				</div>
			{/if}
		</EduCard>
		</div>
	{/if}

	<ConfirmDialog
		bind:show={showRemoveConfirm}
		title={$i18n.t('Remove Student')}
		message={$i18n.t('Remove this student from the classroom? Their submissions are kept.')}
		on:confirm={removeStudent}
	/>

	<ConfirmDialog
		bind:show={showBulkRemoveConfirm}
		title={$i18n.t('Remove Selected Students')}
		message={$i18n.t(
			'Remove {{count}} selected students from the classroom? Their submissions are kept.',
			{ count: selectedIds.size }
		)}
		on:confirm={bulkRemoveSelected}
	/>

	<ConfirmDialog
		bind:show={showTransferConfirm}
		title={$i18n.t('Transfer Selected Students')}
		message={$i18n.t('Transfer {{count}} selected students to the chosen classroom?', {
			count: selectedIds.size
		})}
		on:confirm={transferSelected}
	/>
</TeacherPageShell>
