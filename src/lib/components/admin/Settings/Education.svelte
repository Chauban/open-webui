<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getEducationConfig, setEducationConfig } from '$lib/apis/configs';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';

	const i18n = getContext('i18n');

	type TierKey = 'socratic' | 'balanced' | 'hands_off';

	const tiers: Array<{ key: TierKey; title: string; hint: string }> = [
		{
			key: 'socratic',
			title: 'Socratic',
			hint: 'Questions first; no ready-to-paste prose.'
		},
		{
			key: 'balanced',
			title: 'Balanced',
			hint: 'Clarify intent first, then coach with outlines, examples and demonstrated edits.'
		},
		{
			key: 'hands_off',
			title: 'Hands-off',
			hint: 'Help as asked, with one round of clarification before writing.'
		}
	];

	let loading = true;
	let saving = false;
	let loadFailed = false;

	// 提示词平时只读展示，点铅笔才进入编辑；draft 是编辑中的副本，取消就丢掉。
	let prompts: Record<TierKey, string> = { socratic: '', balanced: '', hands_off: '' };
	// 存过的值会永久盖过代码里的内置默认，所以带上默认值供「恢复默认」用。
	let defaults: Record<TierKey, string> = { socratic: '', balanced: '', hands_off: '' };
	let editing: TierKey | null = null;
	let draft = '';

	const readTiers = (source): Record<TierKey, string> => ({
		socratic: source?.socratic ?? '',
		balanced: source?.balanced ?? '',
		hands_off: source?.hands_off ?? ''
	});

	const load = async () => {
		loading = true;
		loadFailed = false;
		try {
			const config = await getEducationConfig(localStorage.token);
			prompts = readTiers(config?.EDUCATION_COACHING_PROMPTS);
			defaults = readTiers(config?.EDUCATION_COACHING_PROMPT_DEFAULTS);
		} catch (error) {
			loadFailed = true;
			toast.error(`${error}`);
		} finally {
			loading = false;
		}
	};

	onMount(load);

	const startEditing = (key: TierKey) => {
		editing = key;
		draft = prompts[key];
	};

	const cancelEditing = () => {
		editing = null;
		draft = '';
	};

	const persist = async (next: Record<TierKey, string>) => {
		saving = true;
		try {
			const config = await setEducationConfig(localStorage.token, {
				EDUCATION_COACHING_PROMPTS: next
			});
			prompts = readTiers(config?.EDUCATION_COACHING_PROMPTS ?? next);
			defaults = readTiers(config?.EDUCATION_COACHING_PROMPT_DEFAULTS ?? defaults);
			editing = null;
			draft = '';
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			saving = false;
		}
	};

	const save = () => persist(editing ? { ...prompts, [editing]: draft } : prompts);

	const restoreDefault = (key: TierKey) => persist({ ...prompts, [key]: defaults[key] });
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
			<div class="flex flex-col gap-4">
				<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t(
						'Teachers pick one of these coaching styles per assignment. The text below is appended to the assignment context in the student writing workspace.'
					)}
				</p>

				{#each tiers as tier}
					<div class="rounded-xl border border-gray-100/50 dark:border-white/[0.04]">
						<div class="flex items-start justify-between gap-2 px-3 pt-2.5">
							<div class="min-w-0">
								<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t(tier.title)}</div>
								<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
									{$i18n.t(tier.hint)}
								</p>
							</div>
							{#if editing !== tier.key}
								<div class="flex shrink-0 items-center gap-1">
									{#if prompts[tier.key] !== defaults[tier.key]}
										<button
											class="rounded-full px-2 py-0.5 text-[0.6875rem] text-gray-400 transition-colors hover:text-gray-700 disabled:opacity-50 dark:hover:text-gray-300"
											type="button"
											disabled={saving}
											on:click={() => restoreDefault(tier.key)}
										>
											{$i18n.t('Restore default')}
										</button>
									{/if}
									<button
										class="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-700 dark:hover:bg-white/[0.05] dark:hover:text-gray-300"
										type="button"
										title={$i18n.t('Edit')}
										aria-label={$i18n.t('Edit')}
										on:click={() => startEditing(tier.key)}
									>
										<Pencil className="size-3.5" />
									</button>
								</div>
							{/if}
						</div>

						{#if editing === tier.key}
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
						{:else if prompts[tier.key]}
							<pre
								class="mx-3 mb-3 mt-2 whitespace-pre-wrap break-words rounded-lg bg-gray-50/40 px-2 py-1.5 font-sans text-xs leading-6 text-gray-600 dark:bg-white/[0.03] dark:text-gray-400">{prompts[
									tier.key
								]}</pre>
						{:else}
							<div
								class="mx-3 mb-3 mt-2 rounded-lg bg-gray-50/40 px-2 py-1.5 text-xs text-gray-400 dark:bg-white/[0.03] dark:text-gray-600"
							>
								{$i18n.t('Empty — this style adds no coaching instructions.')}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
