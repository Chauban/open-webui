<script lang="ts">
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { createClassroom, getTeacherClassrooms } from '$lib/apis/education';
	import Modal from '$lib/components/common/Modal.svelte';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import EduActionMenu from '$lib/components/education/EduActionMenu.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduStateCard from '$lib/components/education/EduStateCard.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { getClassroomDisplayName, resolveErrorMessage } from '$lib/utils/education';

	// 建班一学期只做几次,不该常驻在列表上方;改成顶栏按钮 + 弹窗,列表放第一位。

	const i18n = getContext<Writable<i18nType>>('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classrooms = [];
	let loading = true;
	let loadError = '';
	let showCreate = false;
	let classroomName = '';
	let creating = false;

	const copyText = async (text: string, successMessage: string) => {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(successMessage);
		} catch {
			toast.error(t('Failed to copy.'));
		}
	};

	const loadClassrooms = async () => {
		loading = true;
		loadError = '';
		try {
			classrooms = await getTeacherClassrooms(localStorage.token);
		} catch (error) {
			loadError = resolveErrorMessage(error, t);
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
			const response = await createClassroom(localStorage.token, { name: trimmedName });
			classroomName = '';
			showCreate = false;
			toast.success(t('Classroom created.'));
			goto(`/teacher/classrooms/${response.classroom.id}`);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			creating = false;
		}
	};

	const menuItems = (classroom) => [
		{
			label: 'Copy Code',
			onClick: () => copyText(classroom.invite_code, t('Invite code copied.'))
		},
		{
			label: 'Copy Invite Link',
			onClick: () =>
				copyText(
					`${window.location.origin}/join?code=${encodeURIComponent(classroom.invite_code)}`,
					t('Invite link copied.')
				)
		},
		{ label: 'Students', onClick: () => goto(`/teacher/classrooms/${classroom.id}/students`) },
		{
			label: 'Create Assignment',
			onClick: () => goto(`/teacher/assignments/new?classroomId=${classroom.id}`)
		}
	];

	onMount(loadClassrooms);
</script>

<TeacherPageShell title={$i18n.t('Classrooms')}>
	<svelte:fragment slot="nav-actions">
		<EduButton variant="primary" size="sm" on:click={() => (showCreate = true)}>
			{$i18n.t('Create Classroom')}
		</EduButton>
	</svelte:fragment>

	<div class="mx-auto max-w-6xl px-4 py-6">
		{#if loadError}
			<EduStateCard tone="error">{loadError}</EduStateCard>
		{:else if loading}
			<EduStateCard>{$i18n.t('Loading classrooms...')}</EduStateCard>
		{:else if classrooms.length === 0}
			<EduCard class="text-center">
				<div class="text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Create a classroom, then share its invite code with your students.')}
				</div>
				<EduButton variant="primary" class="mt-4" on:click={() => (showCreate = true)}>
					{$i18n.t('Create Classroom')}
				</EduButton>
			</EduCard>
		{:else}
			<EduCard padding="none">
				<div class="overflow-x-auto">
					<table class="w-full min-w-[36rem] text-sm">
						<thead class="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400">
							<tr>
								<th class="px-4 py-2.5 font-medium">{$i18n.t('Classroom')}</th>
								<th class="px-4 py-2.5 font-medium">{$i18n.t('Invite Code')}</th>
								<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('Students')}</th>
								<th class="px-4 py-2.5 text-right font-medium">{$i18n.t('Assignments')}</th>
								<th class="w-12"></th>
							</tr>
						</thead>
						<tbody>
							{#each classrooms as item (item.classroom.id)}
								<tr
									class="cursor-pointer border-t border-gray-100 transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
									on:click={() => goto(`/teacher/classrooms/${item.classroom.id}`)}
								>
									<td class="px-4 py-3">
										<a
											href={`/teacher/classrooms/${item.classroom.id}`}
											class="font-medium text-gray-900 hover:underline dark:text-gray-100"
											on:click|stopPropagation
										>
											{getClassroomDisplayName(item.classroom.name, t)}
										</a>
									</td>
									<td class="px-4 py-3">
										<button
											type="button"
											class="rounded-lg px-1.5 py-0.5 font-mono text-gray-700 transition hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
											title={$i18n.t('Copy Code')}
											on:click|stopPropagation={() =>
												copyText(item.classroom.invite_code, t('Invite code copied.'))}
										>
											{item.classroom.invite_code}
										</button>
									</td>
									<td class="px-4 py-3 text-right tabular-nums">{item.student_count}</td>
									<td class="px-4 py-3 text-right tabular-nums">{item.assignment_count}</td>
									<td class="px-2 py-3 text-right">
										<EduActionMenu items={menuItems(item.classroom)} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</EduCard>
		{/if}
	</div>

	<Modal bind:show={showCreate} size="sm">
		<form class="p-6" on:submit|preventDefault={submitCreateClassroom}>
			<div class="text-lg font-semibold">{$i18n.t('Create Classroom')}</div>
			<label class="mt-4 block">
				<span class="mb-2 block text-sm font-medium">{$i18n.t('Classroom name')}</span>
				<!-- svelte-ignore a11y-autofocus -->
				<input
					bind:value={classroomName}
					autofocus
					class="w-full {EDU_FIELD_CLASS}"
					placeholder={$i18n.t('Example: Writing and Communication, 2025 Section 2')}
				/>
			</label>
			<div class="mt-6 flex justify-end gap-2">
				<EduButton on:click={() => (showCreate = false)}>{$i18n.t('Cancel')}</EduButton>
				<EduButton variant="primary" type="submit" disabled={creating}>
					{creating ? $i18n.t('Creating...') : $i18n.t('Create Classroom')}
				</EduButton>
			</div>
		</form>
	</Modal>
</TeacherPageShell>
