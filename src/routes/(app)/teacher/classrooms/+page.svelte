<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { createClassroom, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { getClassroomDisplayName } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

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

		<EduCard class="mb-8">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Create Classroom')}</div>
			<div class="grid gap-3 md:grid-cols-[1fr_auto]">
				<input
					bind:value={classroomName}
					class={EDU_FIELD_CLASS}
					placeholder={$i18n.t('Example: Grade 8 Writing')}
				/>
				<EduButton variant="primary" on:click={submitCreateClassroom} disabled={creating}>
					{creating ? $i18n.t('Creating...') : $i18n.t('Create Classroom')}
				</EduButton>
			</div>
		</EduCard>

		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading classrooms...')}</EduStateCard>
		{:else if classrooms.length === 0}
			<EduStateCard>{$i18n.t('No classrooms yet.')}</EduStateCard>
		{:else}
			<div class="grid gap-4">
				{#each classrooms as item}
					<EduCard>
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div>
								<div class="text-lg font-semibold text-gray-900">
									{getClassroomDisplayName(item.classroom.name, t)}
								</div>
								<div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-gray-500">
									<div>{$i18n.t('Invite Code')}: {item.classroom.invite_code}</div>
									<EduButton size="sm" on:click={() => copyInviteCode(item.classroom.invite_code)}>
										{$i18n.t('Copy Code')}
									</EduButton>
									<div>{$i18n.t('Students')}: {item.student_count}</div>
									<div>{$i18n.t('Assignments')}: {item.assignment_count}</div>
								</div>
							</div>

							<div class="flex flex-wrap gap-2">
								<EduButton on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}>
									{$i18n.t('Open Classroom')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/classrooms/${item.classroom.id}/students`)}
								>
									{$i18n.t('Students')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/classrooms/${item.classroom.id}/assignments`)}
								>
									{$i18n.t('Assignments')}
								</EduButton>
							</div>
						</div>
					</EduCard>
				{/each}
			</div>
		{/if}
	</div>
</TeacherPageShell>
