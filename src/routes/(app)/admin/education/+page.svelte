<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { toast } from 'svelte-sonner';

	import { exportResearchDataset } from '$lib/apis/education';
	import { getAdminClassrooms } from '$lib/apis/users';
	import { resolveErrorMessage } from '$lib/utils/education';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import EduCard from '$lib/components/education/EduCard.svelte';
	import EduTile from '$lib/components/education/EduTile.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => get(i18n).t(key, options);

	let classrooms: Array<{ id: string; name: string }> = [];
	let classroomId = '';
	let startLocal = '';
	let endLocal = '';
	let includeText = false;
	let exporting = false;

	onMount(async () => {
		try {
			classrooms = await getAdminClassrooms(localStorage.token);
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		}
	});

	const toEpoch = (value: string) =>
		value ? Math.floor(new Date(value).getTime() / 1000) : undefined;

	const runExport = async () => {
		const startAt = toEpoch(startLocal);
		const endAt = toEpoch(endLocal);
		if (startAt != null && endAt != null && startAt > endAt) {
			toast.error(t('The start date must not be later than the end date.'));
			return;
		}
		exporting = true;
		try {
			const { blob, filename } = await exportResearchDataset(localStorage.token, {
				classroom_id: classroomId || undefined,
				start_at: startAt,
				end_at: endAt,
				include_text: includeText
			});
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = filename;
			anchor.click();
			URL.revokeObjectURL(url);
			toast.success(t('Research dataset exported.'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, t));
		} finally {
			exporting = false;
		}
	};
</script>

<div class="mx-auto w-full max-w-3xl px-4 py-8">
	<h1 class="text-2xl font-semibold">{$i18n.t('Education')}</h1>
	<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
		{$i18n.t('Export writing-process data for teaching research and pre/post analysis.')}
	</p>

	<EduCard padding="lg" class="mt-6">
		<h2 class="text-base font-semibold">{$i18n.t('Research Data Export')}</h2>

		<div class="mt-5 grid gap-4 sm:grid-cols-2">
			<div>
				<label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300" for="research-classroom">
					{$i18n.t('Classroom')}
				</label>
				<select id="research-classroom" bind:value={classroomId} class="w-full {EDU_FIELD_CLASS}">
					<option value="">{$i18n.t('All classrooms')}</option>
					{#each classrooms as classroom}
						<option value={classroom.id}>{classroom.name}</option>
					{/each}
				</select>
			</div>
			<div class="flex items-end">
				<label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
					<input type="checkbox" bind:checked={includeText} class="size-4" />
					{$i18n.t('Include reflection text')}
				</label>
			</div>
			<div>
				<label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300" for="research-start">
					{$i18n.t('Submitted after')}
				</label>
				<input
					id="research-start"
					type="datetime-local"
					bind:value={startLocal}
					class="w-full {EDU_FIELD_CLASS}"
				/>
			</div>
			<div>
				<label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300" for="research-end">
					{$i18n.t('Submitted before')}
				</label>
				<input
					id="research-end"
					type="datetime-local"
					bind:value={endLocal}
					class="w-full {EDU_FIELD_CLASS}"
				/>
			</div>
		</div>

		<EduTile class="mt-5 text-gray-600 dark:text-gray-400">
			<p>
				{$i18n.t(
					'The archive contains submissions.csv, round_progress.csv and reflections.csv, plus a README stating the metric version and algorithm checksum. Student identity is replaced by a stable one-way pseudonym.'
				)}
			</p>
			<p class="mt-2">
				{$i18n.t(
					'Rows carrying different metric versions came from different algorithm releases and are not directly comparable.'
				)}
			</p>
		</EduTile>

		<EduButton variant="primary" class="mt-5" disabled={exporting} on:click={runExport}>
			{exporting ? $i18n.t('Exporting...') : $i18n.t('Export Dataset')}
		</EduButton>
	</EduCard>
</div>
