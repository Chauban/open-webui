<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { createAssignment, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	let classrooms = [];
	let classroomId = '';
	let title = '';
	let description = '';
	let dueAt = '';
	let loading = true;
	let saving = false;
	let loadError = '';

	onMount(async () => {
		try {
			classrooms = await getTeacherClassrooms(localStorage.token);
			classroomId = get(page).url.searchParams.get('classroomId') || classrooms[0]?.classroom?.id || '';
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	});

	const submit = async () => {
		if (!title.trim()) {
			toast.error(t('Assignment title is required.'));
			return;
		}
		if (!classroomId) {
			toast.error(t('Classroom is required.'));
			return;
		}
		if (!dueAt) {
			toast.error(t('Assignment due time is required.'));
			return;
		}

		saving = true;
		try {
			const assignment = await createAssignment(localStorage.token, {
				title: title.trim(),
				description: description.trim() || undefined,
				classroom_id: classroomId,
				due_at: Math.floor(new Date(dueAt).getTime() / 1000)
			});
			toast.success(t('Assignment created.'));
			goto(`/teacher/assignments/${assignment.id}`);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			saving = false;
		}
	};
</script>

<TeacherPageShell title="Assignments">
	<div class="mx-auto max-w-4xl px-4 py-8">
		<TeacherSectionNav />

	<div class="mb-6 flex flex-wrap items-end justify-between gap-3">
		<div>
			<div class="mb-2 text-sm text-gray-500">{$i18n.t('Teaching')} / {$i18n.t('Assignments')}</div>
			<h1 class="text-3xl font-semibold">{$i18n.t('Create Assignment')}</h1>
		</div>
		<button
			class="rounded-full border border-gray-300 px-4 py-2 text-sm"
			on:click={() => goto('/teacher/assignments')}
		>
			{$i18n.t('Back to Assignments')}
		</button>
	</div>

	{#if loadError}
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	{:else if loading}
		<div class="rounded-3xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
			{$i18n.t('Loading classrooms...')}
		</div>
	{:else}
		<div class="rounded-3xl border border-gray-200 bg-white p-6">
			<div class="grid gap-4">
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Classroom')}</div>
					<select
						class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						bind:value={classroomId}
					>
						{#each classrooms as item}
							<option value={item.classroom.id}>{getClassroomDisplayName(item.classroom.name)}</option>
						{/each}
					</select>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Assignment title')}</div>
					<input
						bind:value={title}
						class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder={$i18n.t('Argument Essay 1')}
					/>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Assignment description')}</div>
					<textarea
						bind:value={description}
						class="min-h-32 w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
						placeholder={$i18n.t('Write a short argument essay.')}
					></textarea>
				</div>
				<div>
					<div class="mb-2 text-sm font-semibold">{$i18n.t('Due At')}</div>
					<input
						bind:value={dueAt}
						type="datetime-local"
						required
						class="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm outline-none"
					/>
				</div>
				<div class="flex justify-end">
					<button
						class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
						on:click={submit}
						disabled={saving}
					>
						{saving ? $i18n.t('Creating...') : $i18n.t('Create Assignment')}
					</button>
				</div>
			</div>
		</div>
	{/if}
	</div>
</TeacherPageShell>
