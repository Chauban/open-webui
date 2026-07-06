<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import {
		exportClassroomProgress,
		getClassroomMembers,
		getClassroomProgress,
		getTeacherClassroomAssignments,
		getTeacherClassrooms,
		regenerateClassroomInviteCode
	} from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	let classroom = null;
	let assignments = [];
	let members = [];
	let progress = null;
	let loading = true;
	let loadError = '';

	const classroomId = () => $page.params.classroomId;

	const downloadProgress = async () => {
		try {
			const csv = await exportClassroomProgress(localStorage.token, classroomId());
			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `${classroom?.name || 'classroom'}-progress.csv`;
			link.click();
			URL.revokeObjectURL(url);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

	const loadData = async () => {
		const classrooms = await getTeacherClassrooms(localStorage.token);
		classroom = classrooms.find((item) => item.classroom.id === classroomId())?.classroom ?? null;
		if (!classroom) {
			throw new Error('Classroom not found');
		}
		[members, assignments, progress] = await Promise.all([
			getClassroomMembers(localStorage.token, classroomId()),
			getTeacherClassroomAssignments(localStorage.token, classroomId()),
			getClassroomProgress(localStorage.token, classroomId())
		]);
	};

	onMount(async () => {
		try {
			await loadData();
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});
</script>

<TeacherPageShell title="Classrooms">
	{#if loading}
		<div class="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500">{$i18n.t('Loading classroom...')}</div>
	{:else if loadError}
		<div class="mx-auto max-w-3xl px-4 py-16">
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
			<div>
				<div class="mb-2 text-sm text-gray-500">{$i18n.t('Teaching')} / {$i18n.t('Classrooms')}</div>
				<h1 class="text-3xl font-semibold">{getClassroomDisplayName(classroom.name)}</h1>
			</div>
			<div class="flex flex-wrap gap-2">
				<button class="rounded-full border border-gray-300 px-4 py-2 text-sm" on:click={() => goto('/teacher/classrooms')}>
					{$i18n.t('Back to Classrooms')}
				</button>
				<button
					class="rounded-full border border-gray-300 px-4 py-2 text-sm"
					on:click={async () => {
						try {
							const response = await regenerateClassroomInviteCode(localStorage.token, classroomId());
							classroom = response.classroom;
							toast.success(t('Invite code regenerated.'));
						} catch (error) {
							toast.error(`${error?.detail ?? error}`);
						}
					}}
				>
					{$i18n.t('Regenerate Code')}
				</button>
				<button class="rounded-full border border-gray-300 px-4 py-2 text-sm" on:click={downloadProgress}>
					{$i18n.t('Export')}
				</button>
			</div>
		</div>

		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<div class="rounded-3xl border border-gray-200 bg-white p-5 md:col-span-2">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Invite Code')}</div>
				<div class="mt-2 font-mono text-3xl font-semibold">{classroom.invite_code}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Students')}</div>
				<div class="mt-2 text-3xl font-semibold">{members.length}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Assignments')}</div>
				<div class="mt-2 text-3xl font-semibold">{assignments.length}</div>
			</div>
		</div>

		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Submitted')}</div>
				<div class="mt-2 text-3xl font-semibold">{progress?.submitted_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Unsubmitted')}</div>
				<div class="mt-2 text-3xl font-semibold">{progress?.unsubmitted_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Reviewed')}</div>
				<div class="mt-2 text-3xl font-semibold">{progress?.reviewed_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-white p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('To Review')}</div>
				<div class="mt-2 text-3xl font-semibold">{progress?.pending_review_count ?? 0}</div>
			</div>
		</div>
		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<div class="rounded-3xl border border-rose-200 bg-rose-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-rose-600">{$i18n.t('Suspected Unmarked Imports')}</div>
				<div class="mt-2 text-3xl font-semibold text-rose-700">{progress?.risk_summary?.suspected_unmarked_import_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-amber-200 bg-amber-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-amber-600">{$i18n.t('Large Bursts')}</div>
				<div class="mt-2 text-3xl font-semibold text-amber-700">{progress?.risk_summary?.burst_count ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-sky-200 bg-sky-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-sky-600">{$i18n.t('AI pasted')}</div>
				<div class="mt-2 text-3xl font-semibold text-sky-700">{progress?.risk_summary?.ai_pasted_chars ?? 0}</div>
			</div>
			<div class="rounded-3xl border border-gray-200 bg-gray-50 p-5">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('AI inserted')}</div>
				<div class="mt-2 text-3xl font-semibold text-gray-800">{progress?.risk_summary?.ai_inserted_chars ?? 0}</div>
			</div>
		</div>

		<div class="mb-8 grid gap-4 lg:grid-cols-3">
			<button class="rounded-3xl border border-gray-200 bg-white p-5 text-left transition hover:border-gray-300" on:click={() => goto(`/teacher/classrooms/${classroom.id}/students`)}>
				<div class="text-lg font-semibold">{$i18n.t('Manage Students')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Search for students, add them to this classroom, or remove them from the roster.')}
				</div>
			</button>
			<button class="rounded-3xl border border-gray-200 bg-white p-5 text-left transition hover:border-gray-300" on:click={() => goto(`/teacher/classrooms/${classroom.id}/assignments`)}>
				<div class="text-lg font-semibold">{$i18n.t('Classroom Assignments')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Review only the assignments that belong to this classroom.')}
				</div>
			</button>
			<button class="rounded-3xl border border-gray-200 bg-white p-5 text-left transition hover:border-gray-300" on:click={() => goto(`/teacher/assignments/new?classroomId=${classroom.id}`)}>
				<div class="text-lg font-semibold">{$i18n.t('Create Assignment')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Start a new writing task for this classroom.')}
				</div>
			</button>
		</div>

		<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment Progress')}</div>
			{#if !progress?.assignments?.length}
				<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
					{$i18n.t('No assignments yet.')}
				</div>
			{:else}
				<div class="space-y-3">
					{#each progress.assignments as item}
						<div class="rounded-2xl border border-gray-200 px-4 py-4 text-sm">
							<div class="font-medium text-gray-900">{item.assignment.title}</div>
							<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
								<div>{$i18n.t('Submitted')}: {item.submitted_count}</div>
								<div>{$i18n.t('Unsubmitted')}: {item.unsubmitted_count}</div>
								<div>{$i18n.t('Reviewed')}: {item.reviewed_count}</div>
								<div>{$i18n.t('To Review')}: {item.pending_review_count}</div>
							</div>
							<div class="mt-3 flex flex-wrap gap-2 text-xs">
								<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
									{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
								</div>
								<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
									{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<div class="rounded-3xl border border-gray-200 bg-white p-5">
			<div class="mb-4 flex items-center justify-between">
				<div class="text-sm font-semibold">{$i18n.t('Recent Assignments')}</div>
				<button class="text-sm text-gray-500" on:click={() => goto(`/teacher/classrooms/${classroom.id}/assignments`)}>
					{$i18n.t('View all')}
				</button>
			</div>
			{#if assignments.length === 0}
				<div class="rounded-2xl border border-dashed border-gray-300 px-4 py-5 text-sm text-gray-500">
					{$i18n.t('No assignments yet.')}
				</div>
			{:else}
				<div class="space-y-3">
					{#each assignments.slice(0, 5) as item}
						<div class="flex flex-col gap-4 rounded-2xl border border-gray-200 px-4 py-4 text-sm md:flex-row md:items-center md:justify-between">
							<div>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.assignment.description || $i18n.t('No description')}
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<div class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary?.suspected_unmarked_import_count ?? 0}
									</div>
									<div class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</div>
								</div>
							</div>
							<div class="flex flex-wrap gap-2">
								<button class="rounded-full border border-gray-300 px-3 py-2 text-sm" on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}>
									{$i18n.t('Open')}
								</button>
								<button class="rounded-full border border-gray-300 px-3 py-2 text-sm" on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}>
									{$i18n.t('Submissions')}
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
		</div>
	{/if}
</TeacherPageShell>
