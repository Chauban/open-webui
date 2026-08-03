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
		regenerateClassroomInviteCode
	} from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EduBadge from '$lib/components/education/EduBadge.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduEmpty from '$lib/components/education/EduEmpty.svelte';
	import EduStatCard from '$lib/components/education/EduStatCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { getClassroomDisplayName } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classroom = null;
	let assignments = [];
	let members = [];
	let progress = null;
	let loading = true;
	let loadError = '';
	let showRegenerateConfirm = false;

	const classroomId = () => $page.params.classroomId;

	const copyText = async (text: string, successMessage: string) => {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(successMessage);
		} catch {
			toast.error(t('Failed to copy.'));
		}
	};

	const copyInviteCode = () => copyText(classroom.invite_code, t('Invite code copied.'));
	const copyInviteLink = () =>
		copyText(
			`${window.location.origin}/join?code=${encodeURIComponent(classroom.invite_code)}`,
			t('Invite link copied.')
		);

	const regenerateCode = async () => {
		try {
			const response = await regenerateClassroomInviteCode(localStorage.token, classroomId());
			classroom = response.classroom;
			toast.success(t('Invite code regenerated.'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		}
	};

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
		[members, assignments, progress] = await Promise.all([
			getClassroomMembers(localStorage.token, classroomId()),
			getTeacherClassroomAssignments(localStorage.token, classroomId()),
			getClassroomProgress(localStorage.token, classroomId())
		]);
		classroom = progress?.classroom ?? null;
		if (!classroom) {
			throw new Error('Classroom not found');
		}
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
			<EduStateCard tone="error">{loadError}</EduStateCard>
		</div>
	{:else}
		<div class="mx-auto max-w-6xl px-4 py-8">
			<TeacherSectionNav />

		<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
			<div>
				<div class="mb-2 text-sm text-gray-500">{$i18n.t('Teaching')} / {$i18n.t('Classrooms')}</div>
				<h1 class="text-3xl font-semibold">{getClassroomDisplayName(classroom.name, t)}</h1>
			</div>
			<div class="flex flex-wrap gap-2">
				<EduButton on:click={() => goto('/teacher/classrooms')}>
					{$i18n.t('Back to Classrooms')}
				</EduButton>
				<EduButton on:click={() => (showRegenerateConfirm = true)}>
					{$i18n.t('Regenerate Code')}
				</EduButton>
				<EduButton on:click={downloadProgress}>{$i18n.t('Export')}</EduButton>
			</div>
		</div>

		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<EduCard class="md:col-span-2">
				<div class="text-xs uppercase tracking-[0.16em] text-gray-500">{$i18n.t('Invite Code')}</div>
				<div class="mt-2 flex flex-wrap items-center gap-3">
					<div class="font-mono text-3xl font-semibold">{classroom.invite_code}</div>
					<div class="flex gap-2">
						<EduButton size="sm" on:click={copyInviteCode}>{$i18n.t('Copy Code')}</EduButton>
						<EduButton size="sm" on:click={copyInviteLink}>{$i18n.t('Copy Invite Link')}</EduButton>
					</div>
				</div>
			</EduCard>
			<EduStatCard label="Students" value={members.length} />
			<EduStatCard label="Assignments" value={assignments.length} />
		</div>

		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<EduStatCard label="Submitted" value={progress?.submitted_count ?? 0} />
			<EduStatCard label="Unsubmitted" value={progress?.unsubmitted_count ?? 0} />
			<EduStatCard label="Reviewed" value={progress?.reviewed_count ?? 0} />
			<EduStatCard label="To Review" value={progress?.pending_review_count ?? 0} />
		</div>
		<div class="mb-8 grid gap-4 md:grid-cols-4">
			<EduStatCard
				tone="rose"
				label="Suspected Unmarked Imports"
				value={progress?.risk_summary?.suspected_unmarked_import_count ?? 0}
			/>
			<EduStatCard
				tone="amber"
				label="Large Bursts"
				value={progress?.risk_summary?.burst_count ?? 0}
			/>
			<EduStatCard
				tone="sky"
				label="AI pasted"
				value={progress?.risk_summary?.ai_pasted_chars ?? 0}
			/>
			<EduStatCard label="AI inserted" value={progress?.risk_summary?.ai_inserted_chars ?? 0} />
		</div>

		<div class="mb-8 grid gap-4 lg:grid-cols-3">
			<EduCard interactive on:click={() => goto(`/teacher/classrooms/${classroom.id}/students`)}>
				<div class="text-lg font-semibold">{$i18n.t('Manage Students')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Search for students, add them to this classroom, or remove them from the roster.')}
				</div>
			</EduCard>
			<EduCard interactive on:click={() => goto(`/teacher/classrooms/${classroom.id}/assignments`)}>
				<div class="text-lg font-semibold">{$i18n.t('Classroom Assignments')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Review only the assignments that belong to this classroom.')}
				</div>
			</EduCard>
			<EduCard
				interactive
				on:click={() => goto(`/teacher/assignments/new?classroomId=${classroom.id}`)}
			>
				<div class="text-lg font-semibold">{$i18n.t('Create Assignment')}</div>
				<div class="mt-2 text-sm text-gray-500">
					{$i18n.t('Start a new writing task for this classroom.')}
				</div>
			</EduCard>
		</div>

		<EduCard class="mb-8">
			<div class="mb-4 text-sm font-semibold">{$i18n.t('Assignment Progress')}</div>
			{#if !progress?.assignments?.length}
				<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
			{:else}
				<div class="space-y-3">
					{#each progress.assignments as item}
						<EduTile>
							<div class="font-medium text-gray-900">{item.assignment.title}</div>
							<div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
								<div>{$i18n.t('Submitted')}: {item.submitted_count}</div>
								<div>{$i18n.t('Unsubmitted')}: {item.unsubmitted_count}</div>
								<div>{$i18n.t('Reviewed')}: {item.reviewed_count}</div>
								<div>{$i18n.t('To Review')}: {item.pending_review_count}</div>
							</div>
							<div class="mt-3 flex flex-wrap gap-2 text-xs">
								<EduBadge tone="rose">
									{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
										?.suspected_unmarked_import_count ?? 0}
								</EduBadge>
								<EduBadge tone="amber">
									{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
								</EduBadge>
							</div>
						</EduTile>
					{/each}
				</div>
			{/if}
		</EduCard>

		<EduCard>
			<div class="mb-4 flex items-center justify-between">
				<div class="text-sm font-semibold">{$i18n.t('Recent Assignments')}</div>
				<EduButton
					variant="link"
					on:click={() => goto(`/teacher/classrooms/${classroom.id}/assignments`)}
				>
					{$i18n.t('View all')}
				</EduButton>
			</div>
			{#if assignments.length === 0}
				<EduEmpty>{$i18n.t('No assignments yet.')}</EduEmpty>
			{:else}
				<div class="space-y-3">
					{#each assignments.slice(0, 5) as item}
						<EduTile class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
							<div>
								<div class="font-medium text-gray-900">{item.assignment.title}</div>
								<div class="mt-1 text-gray-500">
									{item.assignment.description || $i18n.t('No description')}
								</div>
								<div class="mt-3 flex flex-wrap gap-2 text-xs">
									<EduBadge tone="rose">
										{$i18n.t('Suspected Unmarked Imports')}: {item.risk_summary
											?.suspected_unmarked_import_count ?? 0}
									</EduBadge>
									<EduBadge tone="amber">
										{$i18n.t('Large Bursts')}: {item.risk_summary?.burst_count ?? 0}
									</EduBadge>
								</div>
							</div>
							<div class="flex flex-wrap gap-2">
								<EduButton on:click={() => goto(`/teacher/assignments/${item.assignment.id}`)}>
									{$i18n.t('Open')}
								</EduButton>
								<EduButton
									on:click={() => goto(`/teacher/assignments/${item.assignment.id}/submissions`)}
								>
									{$i18n.t('Submissions')}
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
		bind:show={showRegenerateConfirm}
		title={$i18n.t('Regenerate Invite Code')}
		message={$i18n.t(
			'The current invite code stops working immediately and any shared invite links become invalid. Continue?'
		)}
		on:confirm={regenerateCode}
	/>
</TeacherPageShell>
