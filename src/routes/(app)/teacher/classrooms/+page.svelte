<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { createClassroom, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	const copyInviteCode = async (inviteCode: string) => {
		try {
			await navigator.clipboard.writeText(inviteCode);
			toast.success(t('Invite code copied.'));
		} catch {
			toast.error(t('Failed to copy.'));
		}
	};

	let classrooms = [];
	let loading = true;
	let loadError = '';
	let classroomName = '';
	let creating = false;

	const loadClassrooms = async () => {
		loading = true;
		loadError = '';
		try {
			classrooms = await getTeacherClassrooms(localStorage.token);
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	const submitCreateClassroom = async () => {
		const trimmedName = classroomName.trim();
		if (!trimmedName) {
			toast.error(t('Classroom name is required.'));
			return;
		}

		creating = true;
		try {
			const response = await createClassroom(localStorage.token, {
				name: trimmedName
			});
			classroomName = '';
			await loadClassrooms();
			toast.success(t('Classroom created.'));
			goto(`/teacher/classrooms/${response.classroom.id}`);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			creating = false;
		}
	};

	onMount(async () => {
		await loadClassrooms();
	});
</script>

<TeacherPageShell title="Classrooms">
	<div class="mx-auto max-w-6xl px-4 py-8">
		<div class="mb-8 text-sm text-gray-500">
			{$i18n.t('Create classrooms, share invite codes, and manage student rosters.')}
		</div>

		<TeacherSectionNav />

		<div class="mb-8 rounded-3xl border border-gray-200 bg-white p-5">
		<div class="mb-4 text-sm font-semibold">{$i18n.t('Create Classroom')}</div>
		<div class="grid gap-3 md:grid-cols-[1fr_auto]">
			<input
				bind:value={classroomName}
				class="rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
				placeholder={$i18n.t('Example: Grade 8 Writing')}
			/>
			<button
				class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
				on:click={submitCreateClassroom}
				disabled={creating}
			>
				{creating ? $i18n.t('Creating...') : $i18n.t('Create Classroom')}
			</button>
		</div>
	</div>

		{#if loadError}
			<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
				{loadError}
			</div>
		{:else if loading}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('Loading classrooms...')}
			</div>
		{:else if classrooms.length === 0}
			<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
				{$i18n.t('No classrooms yet.')}
			</div>
		{:else}
			<div class="grid gap-4">
			{#each classrooms as item}
				<div class="rounded-3xl border border-gray-200 bg-white p-5">
					<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
						<div>
							<div class="text-lg font-semibold text-gray-900">
								{getClassroomDisplayName(item.classroom.name)}
							</div>
							<div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-gray-500">
								<div>{$i18n.t('Invite Code')}: {item.classroom.invite_code}</div>
								<button
									class="rounded-full border border-gray-300 px-2.5 py-1 text-xs"
									on:click={() => copyInviteCode(item.classroom.invite_code)}
								>
									{$i18n.t('Copy Code')}
								</button>
								<div>{$i18n.t('Students')}: {item.student_count}</div>
								<div>{$i18n.t('Assignments')}: {item.assignment_count}</div>
							</div>
						</div>

						<div class="flex flex-wrap gap-2">
							<button
								class="rounded-full border border-gray-300 px-3 py-2 text-sm"
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}
							>
								{$i18n.t('Open Classroom')}
							</button>
							<button
								class="rounded-full border border-gray-300 px-3 py-2 text-sm"
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}/students`)}
							>
								{$i18n.t('Students')}
							</button>
							<button
								class="rounded-full border border-gray-300 px-3 py-2 text-sm"
								on:click={() => goto(`/teacher/classrooms/${item.classroom.id}/assignments`)}
							>
								{$i18n.t('Assignments')}
							</button>
						</div>
					</div>
				</div>
			{/each}
			</div>
		{/if}
	</div>
</TeacherPageShell>
