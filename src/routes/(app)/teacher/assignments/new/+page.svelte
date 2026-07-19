<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { createAssignment, getTeacherAssignment, getTeacherClassrooms } from '$lib/apis/education';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import TeacherSectionNav from '$lib/components/education/TeacherSectionNav.svelte';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);
	const getClassroomDisplayName = (name: string) =>
		name?.trim() === 'Default Classroom' ? t('Default Classroom') : name;

	let classrooms = [];
	let selectedClassroomIds = new Set();
	let title = '';
	let description = '';
	let dueAt = '';
	let loading = true;
	let saving = false;
	let loadError = '';

	const toggleClassroom = (id: string) => {
		const next = new Set(selectedClassroomIds);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		selectedClassroomIds = next;
	};

	onMount(async () => {
		try {
			classrooms = await getTeacherClassrooms(localStorage.token);
			const params = get(page).url.searchParams;
			const presetClassroomId = params.get('classroomId');
			const duplicateFromId = params.get('from');

			if (duplicateFromId) {
				try {
					const source = await getTeacherAssignment(localStorage.token, duplicateFromId);
					title = source.assignment.title ?? '';
					description = source.assignment.description ?? '';
					if (source.assignment.classroom_id) {
						selectedClassroomIds = new Set([source.assignment.classroom_id]);
					}
				} catch (error) {
					toast.error(`${error?.detail ?? error}`);
				}
			}

			if (selectedClassroomIds.size === 0) {
				const initial = presetClassroomId || classrooms[0]?.classroom?.id;
				if (initial) {
					selectedClassroomIds = new Set([initial]);
				}
			}
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
		if (selectedClassroomIds.size === 0) {
			toast.error(t('Classroom is required.'));
			return;
		}
		if (!dueAt) {
			toast.error(t('Assignment due time is required.'));
			return;
		}

		saving = true;
		try {
			const assignments = await createAssignment(localStorage.token, {
				title: title.trim(),
				description: description.trim() || undefined,
				classroom_ids: [...selectedClassroomIds],
				due_at: Math.floor(new Date(dueAt).getTime() / 1000)
			});
			toast.success(
				assignments.length > 1
					? t('Assignment published to {{count}} classrooms.', { count: assignments.length })
					: t('Assignment created.')
			);
			if (assignments.length === 1) {
				goto(`/teacher/assignments/${assignments[0].id}`);
			} else {
				goto('/teacher/assignments');
			}
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
					<div class="mb-2 flex items-center justify-between">
						<div class="text-sm font-semibold">{$i18n.t('Classrooms')}</div>
						<div class="text-xs text-gray-400">
							{$i18n.t('{{count}} selected', { count: selectedClassroomIds.size })}
						</div>
					</div>
					<div class="flex flex-wrap gap-2">
						{#each classrooms as item}
							<button
								type="button"
								class={`rounded-full border px-4 py-2 text-sm transition ${
									selectedClassroomIds.has(item.classroom.id)
										? 'border-black bg-black text-white'
										: 'border-gray-300 bg-white text-gray-700 hover:border-gray-400'
								}`}
								on:click={() => toggleClassroom(item.classroom.id)}
							>
								{getClassroomDisplayName(item.classroom.name)}
							</button>
						{/each}
					</div>
					<div class="mt-2 text-xs text-gray-400">
						{$i18n.t('Select one or more classrooms; the assignment is published to each.')}
					</div>
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
