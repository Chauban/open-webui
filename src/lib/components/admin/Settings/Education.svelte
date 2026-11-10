<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { getBackendConfig } from '$lib/apis';
	import { getEducationConfig, setEducationConfig } from '$lib/apis/configs';
	import { config as appConfig, models } from '$lib/stores';
	import type { AiStepPolicy, AutoRetryPolicy, CoachingStyle } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import TeachingTypes from './TeachingTypes.svelte';
	import TeachingSearch from './TeachingSearch.svelte';
	import EducationAiStepSettings from './EducationAiStepSettings.svelte';
	import EducationAutoRetrySettings from './EducationAutoRetrySettings.svelte';
	import EducationStudentLimits from './EducationStudentLimits.svelte';
	import EducationPersonalWritingSettings from './EducationPersonalWritingSettings.svelte';

	const i18n = getContext('i18n');
	const styles: Array<{ key: CoachingStyle; label: string }> = [
		{ key: 'socratic', label: 'Socratic' },
		{ key: 'balanced', label: 'Balanced' },
		{ key: 'hands_off', label: 'Hands-off' }
	];
	let values: Awaited<ReturnType<typeof getEducationConfig>> | null = null;
	let loading = true;
	let saving = false;
	let loadError = '';
	const load = async () => {
		loading = true;
		try {
			values = await getEducationConfig(localStorage.token);
			loadError = '';
		} catch (error) {
			loadError = resolveErrorMessage(error, (key) => $i18n.t(key));
		} finally {
			loading = false;
		}
	};
	onMount(load);

	const save = async (
		policy?: AiStepPolicy,
		retries?: AutoRetryPolicy,
		personal?: { student: boolean; teacher: boolean }
	) => {
		if (!values || saving) return;
		saving = true;
		try {
			values = await setEducationConfig(localStorage.token, {
				EDUCATION_COACHING_PROMPTS: values.EDUCATION_COACHING_PROMPTS,
				EDUCATION_DEFAULT_COACHING_STYLE: values.EDUCATION_DEFAULT_COACHING_STYLE,
				EDUCATION_ENABLE_RETURN: values.EDUCATION_ENABLE_RETURN,
				EDUCATION_ENABLE_COACHING_STYLES: values.EDUCATION_ENABLE_COACHING_STYLES,
				EDUCATION_AI_STEP_SETTINGS: policy ?? values.EDUCATION_AI_STEP_SETTINGS,
				EDUCATION_AUTO_RETRY: retries ?? values.EDUCATION_AUTO_RETRY,
				EDUCATION_PERSONAL_WRITING_STUDENT:
					personal?.student ?? values.EDUCATION_PERSONAL_WRITING_STUDENT,
				EDUCATION_PERSONAL_WRITING_TEACHER:
					personal?.teacher ?? values.EDUCATION_PERSONAL_WRITING_TEACHER
			});
			await appConfig.set(await getBackendConfig());
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(resolveErrorMessage(error, (key) => $i18n.t(key)));
		} finally {
			saving = false;
		}
	};
</script>

<div class="h-full overflow-y-auto space-y-6 px-2 pb-8">
	{#if loading}<div class="flex justify-center p-6"><Spinner /></div>
	{:else if loadError}<p role="alert">{loadError}</p>
		<button type="button" on:click={load}>{$i18n.t('Retry')}</button>
	{:else if values}
		<TeachingTypes />
		<TeachingSearch />
		<EducationPersonalWritingSettings
			student={values.EDUCATION_PERSONAL_WRITING_STUDENT}
			teacher={values.EDUCATION_PERSONAL_WRITING_TEACHER}
			disabled={saving}
			onSave={(student, teacher) => save(undefined, undefined, { student, teacher })}
		/>
		<section class="space-y-4 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
			<div class="flex items-center justify-between gap-4">
				<div>
					<h3 class="text-sm font-medium">
						{$i18n.t('Allow teachers to return work for revision')}
					</h3>
					<p class="text-xs text-gray-500">
						{$i18n.t(
							'When off, grading ends a submission and students see the result. Teachers cannot send it back for another round.'
						)}
					</p>
				</div>
				<Switch bind:state={values.EDUCATION_ENABLE_RETURN} on:change={() => save()} />
			</div>
			<div class="flex items-center justify-between gap-4">
				<div>
					<h3 class="text-sm font-medium">{$i18n.t('从零写作的辅导档位')}</h3>
					<p class="text-xs text-gray-500">
						{$i18n.t('两类修订使用完整教学提示词，不叠加通用辅导档位。')}
					</p>
				</div>
				<Switch bind:state={values.EDUCATION_ENABLE_COACHING_STYLES} on:change={() => save()} />
			</div>
			<label class="block text-sm"
				>{$i18n.t('Default coaching style for new assignments')}
				<select
					class="ml-3 rounded-lg dark:bg-gray-800"
					bind:value={values.EDUCATION_DEFAULT_COACHING_STYLE}
					>{#each styles as style}<option value={style.key}>{$i18n.t(style.label)}</option
						>{/each}</select
				>
			</label>
			{#each styles as style}
				<details>
					<summary class="cursor-pointer text-sm">{$i18n.t(style.label)}</summary>
					<textarea
						class="mt-2 min-h-40 w-full rounded-lg text-sm dark:bg-gray-800"
						bind:value={values.EDUCATION_COACHING_PROMPTS[style.key]}
					></textarea>
					<button
						type="button"
						class="text-xs underline"
						on:click={() =>
							(values.EDUCATION_COACHING_PROMPTS[style.key] =
								values.EDUCATION_COACHING_PROMPT_DEFAULTS[style.key])}
						>{$i18n.t('Restore default')}</button
					>
				</details>
			{/each}
			<button
				type="button"
				class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-black"
				disabled={saving}
				on:click={() => save()}>{$i18n.t('Save')}</button
			>
		</section>
		<EducationAiStepSettings
			policy={values.EDUCATION_AI_STEP_SETTINGS}
			steps={values.EDUCATION_AI_STEPS}
			views={values.EDUCATION_AI_STEP_VIEWS}
			modelDefaultMeaning={values.EDUCATION_MODEL_DEFAULT_MEANING}
			models={$models ?? []}
			disabled={saving}
			onChange={(next) => save(next)}
		/>
		<EducationAutoRetrySettings
			scopes={values.EDUCATION_RETRY_SCOPES}
			policy={values.EDUCATION_AUTO_RETRY}
			onChange={(next) => save(undefined, next)}
		/>
		<EducationStudentLimits overrides={values.EDUCATION_STUDENT_CHAT_OVERRIDES} />
	{/if}
</div>
