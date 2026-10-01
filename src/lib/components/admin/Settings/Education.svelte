<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getEducationConfig, setEducationConfig } from '$lib/apis/configs';
	import Spinner from '$lib/components/common/Spinner.svelte';
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

	const coachingSection = sections.find((section) => section.key === 'coaching')!;

	type Prompts = Record<SectionKey, Record<string, string>>;

	let loading = true;
	let saving = false;
	let loadFailed = false;

	// 提示词平时只读展示，点铅笔才进入编辑；draft 是编辑中的副本，取消就丢掉。
	let prompts: Prompts = { task: {}, coaching: {} };
	// 存过的值会永久盖过代码里的内置默认，所以带上默认值供「恢复默认」用。
	let defaults: Prompts = { task: {}, coaching: {} };
	// 新建作业时辅导档位的初始值，教师仍可改选。
	let defaultCoachingStyle = 'balanced';
	let editing: { section: SectionKey; key: string } | null = null;
	let draft = '';

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
			defaultCoachingStyle = config.EDUCATION_DEFAULT_COACHING_STYLE;
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

	const persist = async (next: Prompts, nextDefaultCoachingStyle = defaultCoachingStyle) => {
		saving = true;
		try {
			const config = await setEducationConfig(localStorage.token, {
				...Object.fromEntries(sections.map((section) => [section.configKey, next[section.key]])),
				EDUCATION_DEFAULT_COACHING_STYLE: nextDefaultCoachingStyle
			});
			prompts = read(config, 'configKey');
			defaults = read(config, 'defaultsKey');
			defaultCoachingStyle = config.EDUCATION_DEFAULT_COACHING_STYLE;
			editing = null;
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
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0">
						<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
							{$i18n.t('Default coaching style for new assignments')}
						</div>
						<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
							{$i18n.t(
								'Pre-selected when a teacher creates an assignment. Teachers can still change it per assignment.'
							)}
						</p>
					</div>
					<select
						class="shrink-0 rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300"
						value={defaultCoachingStyle}
						disabled={saving}
						on:change={(event) => persist(prompts, event.currentTarget.value)}
					>
						{#each coachingSection.items as item}
							<option value={item.key}>{$i18n.t(item.title)}</option>
						{/each}
					</select>
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
