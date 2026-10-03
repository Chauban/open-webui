<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getEducationConfig, setEducationConfig } from '$lib/apis/configs';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';

	const i18n = getContext('i18n');

	// 两组提示词:按作业形式追加的任务说明(拼在作业信息之后),和三档辅导风格(再往后)。
	// 任务说明管「这次对话从哪里开始」,辅导风格管「AI 帮多少」。
	type SectionKey = 'task' | 'coaching';
	type Section = {
		key: SectionKey;
		configKey: string;
		defaultsKey: string;
		title: string;
		description: string;
		emptyText: string;
		items: Array<{ key: string; title: string; hint: string }>;
	};

	const sections: Section[] = [
		{
			key: 'task',
			configKey: 'EDUCATION_TASK_PROMPTS',
			defaultsKey: 'EDUCATION_TASK_PROMPT_DEFAULTS',
			title: 'Assignment type instructions',
			description:
				'Added after the assignment context and before the coaching style, according to the assignment type the teacher picked.',
			emptyText: 'Empty — this assignment type adds no instructions.',
			items: [
				{
					key: 'from_scratch',
					title: 'Write from scratch',
					hint: 'Students start from a blank page.'
				},
				{
					key: 'revise_draft',
					title: 'Revise a draft',
					hint: 'Students submit a first draft written outside class, then revise it with the AI.'
				}
			]
		},
		{
			key: 'coaching',
			configKey: 'EDUCATION_COACHING_PROMPTS',
			defaultsKey: 'EDUCATION_COACHING_PROMPT_DEFAULTS',
			title: 'Coaching styles',
			description:
				'Teachers pick one of these coaching styles per assignment. The text below is appended to the assignment context in the student writing workspace.',
			emptyText: 'Empty — this style adds no coaching instructions.',
			items: [
				{
					key: 'socratic',
					title: 'Socratic',
					hint: 'Questions first; no ready-to-paste prose.'
				},
				{
					key: 'balanced',
					title: 'Balanced',
					hint: 'Coach with outlines, examples and demonstrated edits.'
				},
				{
					key: 'hands_off',
					title: 'Hands-off',
					hint: 'Help as asked, including rewriting on request.'
				}
			]
		}
	];

	// 新建作业表单的初始值，按实例设定，教师仍可逐个作业改选。选项直接取自下面两组提示词。
	type AssignmentDefaultKey = 'EDUCATION_DEFAULT_TASK_MODE' | 'EDUCATION_DEFAULT_COACHING_STYLE';
	const assignmentDefaultFields: Array<{
		configKey: AssignmentDefaultKey;
		title: string;
		section: Section;
	}> = [
		{
			configKey: 'EDUCATION_DEFAULT_TASK_MODE',
			title: 'Default assignment type for new assignments',
			section: sections.find((section) => section.key === 'task')!
		},
		{
			configKey: 'EDUCATION_DEFAULT_COACHING_STYLE',
			title: 'Default coaching style for new assignments',
			section: sections.find((section) => section.key === 'coaching')!
		}
	];

	type Prompts = Record<SectionKey, Record<string, string>>;

	let loading = true;
	let saving = false;
	let loadFailed = false;

	// 提示词平时只读展示，点铅笔才进入编辑；draft 是编辑中的副本，取消就丢掉。
	let prompts: Prompts = { task: {}, coaching: {} };
	// 存过的值会永久盖过代码里的内置默认，所以带上默认值供「恢复默认」用。
	let defaults: Prompts = { task: {}, coaching: {} };
	let assignmentDefaults: Record<AssignmentDefaultKey, string> = {
		EDUCATION_DEFAULT_TASK_MODE: 'from_scratch',
		EDUCATION_DEFAULT_COACHING_STYLE: 'balanced'
	};
	// 教师能否把作业退回重写;关掉后批改页不出现「退回重写」，后端也拒绝退回。
	let enableReturn = false;
	// 作业能否选辅导风格;关掉后作业表单不显示档位,对话也不附档位提示词。
	let enableCoachingStyles = true;
	let editing: { section: SectionKey; key: string } | null = null;
	let draft = '';

	// 新建作业预填的评分维度，按作业形式各一份；空列表表示用内置的「观点 / 结构 / 论据」。
	// 修订初稿的第一次通读按作业的评分维度逐项下结论，所以这一份要和任务说明里的标准同名。
	type RubricRow = { label: string; max_score: number };
	type RubricMode = 'from_scratch' | 'revise_draft';
	const RUBRIC_LIMIT = 8;
	let defaultRubrics: Record<RubricMode, RubricRow[]> = { from_scratch: [], revise_draft: [] };
	let rubricEditing: RubricMode | null = null;
	let rubricDraft: Array<{ label: string; max_score: string }> = [];

	const readRubrics = (config): Record<RubricMode, RubricRow[]> => ({
		from_scratch: config?.EDUCATION_DEFAULT_RUBRICS?.from_scratch ?? [],
		revise_draft: config?.EDUCATION_DEFAULT_RUBRICS?.revise_draft ?? []
	});

	const builtinRubric = (): RubricRow[] => [
		{ label: $i18n.t('Ideas'), max_score: 34 },
		{ label: $i18n.t('Structure'), max_score: 33 },
		{ label: $i18n.t('Evidence'), max_score: 33 }
	];

	const startRubricEditing = (mode: RubricMode) => {
		rubricEditing = mode;
		const rows = defaultRubrics[mode].length ? defaultRubrics[mode] : builtinRubric();
		rubricDraft = rows.map((row) => ({ label: row.label, max_score: String(row.max_score) }));
	};

	$: rubricDraftTotal = rubricDraft.reduce((sum, row) => sum + (Number(row.max_score) || 0), 0);

	const saveRubric = () => {
		if (!rubricEditing) return;
		const rows = rubricDraft.map((row) => ({
			label: row.label.trim(),
			max_score: Number(row.max_score)
		}));
		if (
			rows.length === 0 ||
			rows.some((row) => !row.label || !Number.isInteger(row.max_score) || row.max_score <= 0)
		) {
			toast.error(
				$i18n.t('Every rubric criterion needs a name and a positive whole-number maximum.')
			);
			return;
		}
		persist(prompts, assignmentDefaults, { ...defaultRubrics, [rubricEditing]: rows });
	};

	const read = (config, field: 'configKey' | 'defaultsKey'): Prompts =>
		Object.fromEntries(
			sections.map((section) => [
				section.key,
				Object.fromEntries(
					section.items.map((item) => [item.key, config?.[section[field]]?.[item.key] ?? ''])
				)
			])
		) as Prompts;

	const load = async () => {
		loading = true;
		loadFailed = false;
		try {
			const config = await getEducationConfig(localStorage.token);
			prompts = read(config, 'configKey');
			defaults = read(config, 'defaultsKey');
			assignmentDefaults = readAssignmentDefaults(config);
			defaultRubrics = readRubrics(config);
			enableReturn = config.EDUCATION_ENABLE_RETURN;
			enableCoachingStyles = config.EDUCATION_ENABLE_COACHING_STYLES;
		} catch (error) {
			loadFailed = true;
			toast.error(`${error}`);
		} finally {
			loading = false;
		}
	};

	onMount(load);

	const startEditing = (section: SectionKey, key: string) => {
		editing = { section, key };
		draft = prompts[section][key];
	};

	const cancelEditing = () => {
		editing = null;
		draft = '';
	};

	const withValue = (section: SectionKey, key: string, value: string): Prompts => ({
		...prompts,
		[section]: { ...prompts[section], [key]: value }
	});

	const readAssignmentDefaults = (config) =>
		Object.fromEntries(
			assignmentDefaultFields.map((field) => [field.configKey, config[field.configKey]])
		) as Record<AssignmentDefaultKey, string>;

	const persist = async (
		next: Prompts,
		nextAssignmentDefaults = assignmentDefaults,
		nextRubrics = defaultRubrics
	) => {
		saving = true;
		try {
			const config = await setEducationConfig(localStorage.token, {
				...Object.fromEntries(sections.map((section) => [section.configKey, next[section.key]])),
				...nextAssignmentDefaults,
				EDUCATION_DEFAULT_RUBRICS: nextRubrics,
				EDUCATION_ENABLE_RETURN: enableReturn,
				EDUCATION_ENABLE_COACHING_STYLES: enableCoachingStyles
			});
			prompts = read(config, 'configKey');
			defaults = read(config, 'defaultsKey');
			assignmentDefaults = readAssignmentDefaults(config);
			defaultRubrics = readRubrics(config);
			enableReturn = config.EDUCATION_ENABLE_RETURN;
			enableCoachingStyles = config.EDUCATION_ENABLE_COACHING_STYLES;
			editing = null;
			rubricEditing = null;
			draft = '';
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			saving = false;
		}
	};

	const save = () =>
		persist(editing ? withValue(editing.section, editing.key, draft) : prompts);

	const restoreDefault = (section: SectionKey, key: string) =>
		persist(withValue(section, key, defaults[section][key]));
</script>

<div class="flex h-full flex-col justify-between text-sm">
	<h2 class="mb-4 text-sm font-medium text-gray-900 dark:text-white">
		{$i18n.t('Writing Coaching')}
	</h2>

	<div class="scrollbar-hover min-h-0 flex-1 overflow-y-auto pr-1.5">
		{#if loading}
			<div class="flex justify-center py-8"><Spinner className="size-6" /></div>
		{:else if loadFailed}
			<div
				class="rounded-xl bg-gray-50 px-4 py-6 text-center text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
			>
				<div>{$i18n.t('Could not load the coaching prompts.')}</div>
				<button class="mt-2 text-xs text-gray-700 underline dark:text-gray-300" on:click={load}>
					{$i18n.t('Retry')}
				</button>
			</div>
		{:else}
			<div class="flex flex-col gap-6">
				<div class="flex flex-col gap-3">
					{#each assignmentDefaultFields as field}
						<div class="flex items-start justify-between gap-4">
							<div class="min-w-0">
								<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
									{$i18n.t(field.title)}
								</div>
								<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
									{$i18n.t(
										'Pre-selected when a teacher creates an assignment. Teachers can still change it per assignment.'
									)}
								</p>
							</div>
							<select
								class="shrink-0 rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300"
								value={assignmentDefaults[field.configKey]}
								disabled={saving}
								on:change={(event) =>
									persist(prompts, {
										...assignmentDefaults,
										[field.configKey]: event.currentTarget.value
									})}
							>
								{#each field.section.items as item}
									<option value={item.key}>{$i18n.t(item.title)}</option>
								{/each}
							</select>
						</div>
					{/each}

					<div class="flex flex-col gap-2">
						<div class="min-w-0">
							<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Default rubric for new assignments')}
							</div>
							<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t(
									'Pre-filled when a teacher creates an assignment of this type; teachers can still edit it. For revision assignments the first read-through gives one conclusion per rubric criterion, so name them after the standards in the task instructions.'
								)}
							</p>
						</div>
						{#each sections[0].items as item}
							{@const mode = item.key}
							<div class="rounded-xl border border-gray-100/50 px-3 py-2.5 dark:border-white/[0.04]">
								<div class="flex items-start justify-between gap-2">
									<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t(item.title)}</div>
									{#if rubricEditing !== mode}
										<div class="flex shrink-0 items-center gap-1">
											{#if defaultRubrics[mode].length}
												<button
													class="rounded-full px-2 py-0.5 text-[0.6875rem] text-gray-400 transition-colors hover:text-gray-700 disabled:opacity-50 dark:hover:text-gray-300"
													type="button"
													disabled={saving}
													on:click={() =>
														persist(prompts, assignmentDefaults, { ...defaultRubrics, [mode]: [] })}
												>
													{$i18n.t('Restore default')}
												</button>
											{/if}
											<button
												class="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-700 dark:hover:bg-white/[0.05] dark:hover:text-gray-300"
												type="button"
												title={$i18n.t('Edit')}
												aria-label={$i18n.t('Edit')}
												on:click={() => startRubricEditing(mode)}
											>
												<Pencil className="size-3.5" />
											</button>
										</div>
									{/if}
								</div>
								{#if rubricEditing === mode}
									<div class="mt-2 flex flex-col gap-1.5">
										{#each rubricDraft as row, index}
											<div class="flex items-center gap-2">
												<span class="w-4 text-right text-[0.6875rem] text-gray-400">{index + 1}</span>
												<input
													class="min-w-0 flex-1 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1 text-xs text-gray-700 outline-hidden focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300"
													placeholder={$i18n.t('Criterion name')}
													bind:value={row.label}
												/>
												<input
													class="w-14 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1 text-right text-xs text-gray-700 outline-hidden focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300"
													type="number"
													min="1"
													bind:value={row.max_score}
												/>
												<button
													class="px-1 text-xs text-gray-400 hover:text-red-500"
													type="button"
													aria-label={$i18n.t('Remove')}
													on:click={() => (rubricDraft = rubricDraft.filter((_, i) => i !== index))}
												>
													×
												</button>
											</div>
										{/each}
										<div class="mt-1 flex items-center justify-between gap-2">
											<div class="flex items-center gap-3 text-[0.6875rem] text-gray-400">
												{#if rubricDraft.length < RUBRIC_LIMIT}
													<button
														class="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
														type="button"
														on:click={() => (rubricDraft = [...rubricDraft, { label: '', max_score: '' }])}
													>
														+ {$i18n.t('Add criterion')}
													</button>
												{/if}
												<span>{$i18n.t('Total {{total}}', { total: rubricDraftTotal })}</span>
											</div>
											<div class="flex items-center gap-2">
												<button
													class="rounded-full px-3 py-1 text-xs text-gray-500 transition hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
													type="button"
													disabled={saving}
													on:click={() => (rubricEditing = null)}
												>
													{$i18n.t('Cancel')}
												</button>
												<button
													class="rounded-full bg-black px-3.5 py-1.5 text-xs font-normal text-white transition hover:bg-gray-900 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-100"
													type="button"
													disabled={saving}
													on:click={saveRubric}
												>
													{$i18n.t('Save')}
												</button>
											</div>
										</div>
									</div>
								{:else}
									<div class="mt-1 text-[0.6875rem] leading-5 text-gray-500 dark:text-gray-400">
										{(defaultRubrics[mode].length ? defaultRubrics[mode] : builtinRubric())
											.map((row) => `${row.label} ${row.max_score}`)
											.join(' · ')}
										{#if !defaultRubrics[mode].length}
											<span class="text-gray-400">{$i18n.t('(built-in)')}</span>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>

					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0">
							<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Allow teachers to return work for revision')}
							</div>
							<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t(
									'When off, grading ends a submission and students see the result. Teachers cannot send it back for another round.'
								)}
							</p>
						</div>
						<Switch bind:state={enableReturn} on:change={() => persist(prompts)} />
					</div>

					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0">
							<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t('Let assignments choose a coaching style')}
							</div>
							<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t(
									'When off, the assignment form has no coaching style and the chat gets no style prompt: how the AI coaches is written entirely in the task instructions below.'
								)}
							</p>
						</div>
						<Switch bind:state={enableCoachingStyles} on:change={() => persist(prompts)} />
					</div>
				</div>

				{#each sections as section}
					<div class="flex flex-col gap-4">
						<div>
							<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
								{$i18n.t(section.title)}
							</div>
							<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t(section.description)}
							</p>
						</div>

						{#each section.items as item}
							<div class="rounded-xl border border-gray-100/50 dark:border-white/[0.04]">
								<div class="flex items-start justify-between gap-2 px-3 pt-2.5">
									<div class="min-w-0">
										<div class="text-xs text-gray-700 dark:text-gray-300">
											{$i18n.t(item.title)}
										</div>
										<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
											{$i18n.t(item.hint)}
										</p>
									</div>
									{#if !(editing?.section === section.key && editing?.key === item.key)}
										<div class="flex shrink-0 items-center gap-1">
											{#if prompts[section.key][item.key] !== defaults[section.key][item.key]}
												<button
													class="rounded-full px-2 py-0.5 text-[0.6875rem] text-gray-400 transition-colors hover:text-gray-700 disabled:opacity-50 dark:hover:text-gray-300"
													type="button"
													disabled={saving}
													on:click={() => restoreDefault(section.key, item.key)}
												>
													{$i18n.t('Restore default')}
												</button>
											{/if}
											<button
												class="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-700 dark:hover:bg-white/[0.05] dark:hover:text-gray-300"
												type="button"
												title={$i18n.t('Edit')}
												aria-label={$i18n.t('Edit')}
												on:click={() => startEditing(section.key, item.key)}
											>
												<Pencil className="size-3.5" />
											</button>
										</div>
									{/if}
								</div>

								{#if editing?.section === section.key && editing?.key === item.key}
									<div class="px-3 pb-3 pt-2">
										<textarea
											bind:value={draft}
											rows="9"
											class="w-full resize-y rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 py-1.5 font-mono text-xs leading-6 text-gray-700 outline-hidden transition-colors focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:focus:border-blue-500"
										></textarea>
										<div class="mt-2 flex items-center justify-end gap-2">
											<button
												class="rounded-full px-3 py-1 text-xs text-gray-500 transition hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
												type="button"
												disabled={saving}
												on:click={cancelEditing}
											>
												{$i18n.t('Cancel')}
											</button>
											<button
												class="rounded-full bg-black px-3.5 py-1.5 text-xs font-normal text-white transition hover:bg-gray-900 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-100"
												type="button"
												disabled={saving}
												on:click={save}
											>
												{$i18n.t('Save')}
											</button>
										</div>
									</div>
								{:else if prompts[section.key][item.key]}
									<pre
										class="mx-3 mb-3 mt-2 whitespace-pre-wrap break-words rounded-lg bg-gray-50/40 px-2 py-1.5 font-sans text-xs leading-6 text-gray-600 dark:bg-white/[0.03] dark:text-gray-400">{prompts[
											section.key
										][item.key]}</pre>
								{:else}
									<div
										class="mx-3 mb-3 mt-2 rounded-lg bg-gray-50/40 px-2 py-1.5 text-xs text-gray-400 dark:bg-white/[0.03] dark:text-gray-600"
									>
										{$i18n.t(section.emptyText)}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
