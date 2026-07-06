<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		bulkImportClassroomMembers,
		addClassroomMember,
		getClassroomMembers,
		getTeacherClassrooms,
		removeClassroomMember
	} from '$lib/apis/education';
	import { searchUsers } from '$lib/apis/users';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	let classroom = null;
	let members = [];
	let searchResults = [];
	let memberQuery = '';
	let bulkImportInput = '';
	let loading = true;
	let loadError = '';

	const classroomId = () => $page.params.classroomId;

	const loadData = async () => {
		loading = true;
		loadError = '';
		try {
			const classrooms = await getTeacherClassrooms(localStorage.token);
			classroom = classrooms.find((item) => item.classroom.id === classroomId())?.classroom ?? null;
			if (!classroom) {
				throw new Error('Classroom not found');
			}
			members = await getClassroomMembers(localStorage.token, classroomId());
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	const searchStudents = async () => {
		const query = memberQuery.trim();
		if (!query) {
			searchResults = [];
			return;
		}

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
		}
	};

	const addStudent = async (studentId: string) => {
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
		}
	};

	const removeStudent = async (studentId: string) => {
		try {
			await removeClassroomMember(localStorage.token, classroomId(), studentId);
			members = await getClassroomMembers(localStorage.token, classroomId());
			toast.success(t('Student removed.'));
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

		try {
			const result = await bulkImportClassroomMembers(localStorage.token, classroomId(), {
				emails: lines.filter((item) => item.includes('@')),
				user_ids: lines.filter((item) => !item.includes('@'))
			});
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
		}
	};

	onMount(loadData);
</script>

<TeacherPageShell title="Classrooms">
	{#if loading}
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500">{$i18n.t('Loading students...')}</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
			<div>
				<div class="mb-2 text-sm text-gray-500">
					{$i18n.t('Teaching')} / {$i18n.t('Classrooms')} / {getClassroomDisplayName(classroom.name)}
				</div>
				<h1 class="text-3xl font-semibold">{$i18n.t('Manage Students')}</h1>
			</div>
			<button
				class="rounded-full border border-gray-300 px-4 py-2 text-sm"
				on:click={() => goto(`/teacher/classrooms/${classroom.id}`)}
			>
				{$i18n.t('Back to Classroom')}
			</button>
		</div>

		<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Add Student')}</div>
			<div class="flex gap-2">
				<input
					bind:value={memberQuery}
					class="flex-1 rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
					placeholder={$i18n.t('Search by student name or email')}
				/>
				<button class="rounded-full bg-black px-4 py-2 text-sm text-white" on:click={searchStudents}>
					{$i18n.t('Search')}
				</button>
			</div>

			{#if searchResults.length > 0}
				<div class="mt-3 space-y-2">
					{#each searchResults as candidate}
						<div class="flex items-center justify-between rounded-2xl border border-gray-200 px-3 py-3 text-sm">
							<div>
								<div class="font-medium">{candidate.name}</div>
								<div class="text-xs text-gray-500">{candidate.email}</div>
							</div>
							<button
								class="rounded-full border border-gray-300 px-3 py-1.5 text-sm"
								on:click={() => addStudent(candidate.id)}
							>
								{$i18n.t('Add')}
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Bulk Import Students')}</div>
			<textarea
				bind:value={bulkImportInput}
				class="min-h-28 w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
				placeholder={$i18n.t('Enter one student email or user ID per line')}
			></textarea>
			<div class="mt-3 flex justify-end">
				<button class="rounded-full bg-black px-4 py-2 text-sm text-white" on:click={bulkImportStudents}>
					{$i18n.t('Import')}
				</button>
			</div>
		</div>

		<div class="rounded-3xl border border-gray-200 bg-white p-5">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Current Students')}</div>
			{#if members.length === 0}
				<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
					{$i18n.t('No students in this classroom yet.')}
				</div>
			{:else}
				<div class="space-y-2">
					{#each members as member}
						<div class="flex items-center justify-between rounded-2xl border border-gray-200 px-4 py-3 text-sm">
							<div>
								<div class="font-medium">{member.user_name}</div>
								<div class="text-xs text-gray-500">{member.user_email}</div>
							</div>
							<button
								class="rounded-full border border-red-300 px-3 py-1.5 text-sm text-red-600"
								on:click={() => removeStudent(member.member.user_id)}
							>
								{$i18n.t('Remove')}
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
		</div>
	{/if}
</TeacherPageShell>
