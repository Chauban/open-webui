<script lang="ts">
	// 提交前反思的出题器：新建作业页与作业详情页共用。
	//
	// 不同作业要问的反思不一样，所以题目归教师定。为了不让教师每次从零写：
	// - 第一次出题预填推荐的默认题组，删改即可；
	// - 以后新建作业由页面预填上一次用过的那套，也可以从以往任意一份作业导入；
	// - 推荐题库随时可以单题加回来，删错了不用重写。
	// 「这次用了 AI 吗」是系统固定题，不在这里编辑，只在顶部说明和预览里出现。
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import type {
		ReflectionQuestion,
		ReflectionQuestionKind,
		ReflectionQuestionSet,
		ReflectionShowWhen
	} from '$lib/apis/education/types';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import EduButton from './EduButton.svelte';
	import ReflectionAnswerForm from './ReflectionAnswerForm.svelte';
	import { EDU_FIELD_CLASS, eduSegmentClass } from './styles';
	import {
		REFLECTION_MAX_OPTIONS,
		REFLECTION_MAX_QUESTIONS,
		cloneReflectionQuestions,
		createReflectionQuestion,
		getDefaultReflectionQuestions,
		getRecommendedReflectionQuestions,
		newReflectionQuestionId,
		normalizeReflectionQuestions,
		reflectionQuestionsFingerprint,
		type AiUsage,
		type ReflectionAnswerDrafts
	} from '$lib/utils/reflection-questions';
	import { formatEpochDate } from '$lib/utils/education';

	const i18n = getContext('i18n');
	const t = (key: string, options?: Record<string, unknown>) => $i18n.t(key, options);

	export let questions: ReflectionQuestion[] = [];
	/** 以往作业用过的题组，供导入。 */
	export let questionSets: ReflectionQuestionSet[] = [];
	/** 当前作业自己不出现在导入列表里。 */
	export let currentAssignmentId = '';
	/** 页面给的一句来源说明，例如「已沿用上一份作业的题目」。 */
	export let notice = '';
	export let hasSubmissions = false;

	const KINDS: Array<{ key: ReflectionQuestionKind; label: string }> = [
		{ key: 'single_choice', label: 'Single choice' },
		{ key: 'multi_choice', label: 'Multiple choice' },
		{ key: 'text', label: 'Short answer' }
	];
	const SHOW_WHEN: Array<{ key: ReflectionShowWhen; label: string }> = [
		{ key: 'always', label: 'All students' },
		{ key: 'ai_used', label: 'Only students who used AI' },
		{ key: 'ai_not_used', label: 'Only students who did not use AI' }
	];

	let showPreview = false;
	let previewAiUsage: AiUsage = null;
	let previewDrafts: ReflectionAnswerDrafts = {};
	let showRecommended = false;
	let importValue = '';
	let showReplaceConfirm = false;
	let pendingReplacement: { questions: ReflectionQuestion[]; message: string } | null = null;

	$: importableSets = questionSets.filter((set) => set.assignment_id !== currentAssignmentId);
	$: atLimit = questions.length >= REFLECTION_MAX_QUESTIONS;
	$: currentPrompts = new Set(questions.map((question) => question.prompt.trim()));
	$: recommended = getRecommendedReflectionQuestions(t).filter(
		(item) => !currentPrompts.has(item.question.prompt)
	);
	$: previewQuestions = normalizeReflectionQuestions(questions).filter(
		(question) => question.prompt
	);

	const update = (index: number, patch: Partial<ReflectionQuestion>) => {
		questions = questions.map((question, itemIndex) =>
			itemIndex === index ? { ...question, ...patch } : question
		);
	};

	const setKind = (index: number, kind: ReflectionQuestionKind) => {
		const question = questions[index];
		// 从填空切到选择题时给两个空选项占位，切回来时选项留在内存里，保存时才丢。
		const options = kind !== 'text' && question.options.length === 0 ? ['', ''] : question.options;
		update(index, { kind, options });
	};

	const addQuestion = (kind: ReflectionQuestionKind) => {
		if (atLimit) return;
		questions = [...questions, createReflectionQuestion(kind)];
	};

	const addRecommended = (question: ReflectionQuestion) => {
		if (atLimit) return;
		questions = [...questions, { ...question, id: newReflectionQuestionId() }];
	};

	const move = (index: number, offset: number) => {
		const target = index + offset;
		if (target < 0 || target >= questions.length) return;
		const next = [...questions];
		[next[index], next[target]] = [next[target], next[index]];
		questions = next;
	};

	const duplicate = (index: number) => {
		if (atLimit) return;
		const [copy] = cloneReflectionQuestions([questions[index]]);
		questions = [...questions.slice(0, index + 1), copy, ...questions.slice(index + 1)];
	};

	const remove = (index: number) => {
		questions = questions.filter((_, itemIndex) => itemIndex !== index);
	};

	const updateOption = (index: number, optionIndex: number, value: string) => {
		const options = [...questions[index].options];
		options[optionIndex] = value;
		update(index, { options });
	};

	const addOption = async (index: number) => {
		if (questions[index].options.length >= REFLECTION_MAX_OPTIONS) return;
		update(index, { options: [...questions[index].options, ''] });
		// 等 DOM 出来再把光标放进新选项，教师可以一路回车连续录入。
		await Promise.resolve();
		requestAnimationFrame(() => {
			const inputs = document.querySelectorAll<HTMLInputElement>(
				`[data-option-of="${questions[index]?.id}"]`
			);
			inputs[inputs.length - 1]?.focus();
		});
	};

	const removeOption = (index: number, optionIndex: number) => {
		update(index, {
			options: questions[index].options.filter((_, itemIndex) => itemIndex !== optionIndex)
		});
	};

	// 整套替换会冲掉教师手上的改动，有内容且确实不同才确认一次。
	const replaceWith = (next: ReflectionQuestion[], message: string) => {
		const unchanged =
			reflectionQuestionsFingerprint(normalizeReflectionQuestions(questions)) ===
			reflectionQuestionsFingerprint(normalizeReflectionQuestions(next));
		if (unchanged) {
			toast.info(t('These are already the current questions.'));
			return;
		}
		if (questions.length === 0) {
			questions = next;
			toast.success(message);
			return;
		}
		pendingReplacement = { questions: next, message };
		showReplaceConfirm = true;
	};

	const confirmReplacement = () => {
		if (!pendingReplacement) return;
		questions = pendingReplacement.questions;
		toast.success(pendingReplacement.message);
		pendingReplacement = null;
	};

	const importSet = (assignmentId: string) => {
		importValue = '';
		const source = importableSets.find((set) => set.assignment_id === assignmentId);
		if (!source) return;
		replaceWith(
			cloneReflectionQuestions(source.questions),
			t('Imported the questions from "{{title}}".', { title: source.assignment_title })
		);
	};

	const resetToDefaults = () => {
		replaceWith(getDefaultReflectionQuestions(t), t('Restored the recommended questions.'));
	};
</script>

<div>
	<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
		<div class="flex items-center gap-2">
			<span class="text-sm font-semibold">{$i18n.t('Reflection Before Submitting')}</span>
			<span
				class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
			>
				{$i18n.t('{{count}} questions', { count: questions.length })}
			</span>
		</div>
		<EduButton size="sm" on:click={() => (showPreview = !showPreview)}>
			{showPreview ? $i18n.t('Back to editing') : $i18n.t('Preview as student')}
		</EduButton>
	</div>

	<div class="text-xs text-gray-400">
		{$i18n.t(
			'Students answer these right before submitting. "Did you use AI?" is always asked first; everything below it is up to you.'
		)}
	</div>
	{#if hasSubmissions}
		<div class="mt-1 text-xs text-gray-400">
			{$i18n.t(
				'Changes apply to future submissions. Reflections already submitted keep the questions they answered.'
			)}
		</div>
	{/if}
	{#if notice}
		<div
			class="mt-2 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
		>
			{notice}
		</div>
	{/if}

	{#if showPreview}
		<div class="mt-4 rounded-3xl border border-dashed border-gray-300 p-5 dark:border-gray-700">
			<div class="mb-4 text-xs uppercase tracking-[0.16em] text-gray-400">
				{$i18n.t('What students see')}
			</div>
			<ReflectionAnswerForm
				questions={previewQuestions}
				idPrefix="reflection-preview"
				bind:aiUsage={previewAiUsage}
				bind:drafts={previewDrafts}
			/>
		</div>
	{:else}
		<div class="mt-4 flex flex-wrap items-center gap-2">
			<div class="flex flex-wrap gap-2">
				<EduButton size="sm" disabled={atLimit} on:click={() => addQuestion('single_choice')}>
					+ {$i18n.t('Single choice')}
				</EduButton>
				<EduButton size="sm" disabled={atLimit} on:click={() => addQuestion('multi_choice')}>
					+ {$i18n.t('Multiple choice')}
				</EduButton>
				<EduButton size="sm" disabled={atLimit} on:click={() => addQuestion('text')}>
					+ {$i18n.t('Short answer')}
				</EduButton>
			</div>
			<div class="ml-auto flex flex-wrap items-center gap-2">
				<EduButton
					size="sm"
					disabled={recommended.length === 0}
					on:click={() => (showRecommended = !showRecommended)}
				>
					{$i18n.t('Recommended questions')}
				</EduButton>
				{#if importableSets.length > 0}
					<select
						bind:value={importValue}
						class="w-56 max-w-full truncate rounded-full border border-gray-300 bg-white py-1.5 pl-3 pr-8 text-xs text-gray-700 outline-none dark:border-gray-700 dark:bg-gray-850 dark:text-gray-300"
						on:change={() => importSet(importValue)}
					>
						<option value="">{$i18n.t('Import from a past assignment…')}</option>
						{#each importableSets as set (set.assignment_id)}
							<option value={set.assignment_id}>
								{set.assignment_title} · {formatEpochDate(set.created_at)} · {$i18n.t(
									'{{count}} questions',
									{ count: set.questions.length }
								)}
							</option>
						{/each}
					</select>
				{/if}
				<EduButton size="sm" variant="link" on:click={resetToDefaults}>
					{$i18n.t('Restore defaults')}
				</EduButton>
			</div>
		</div>

		{#if showRecommended && recommended.length > 0}
			<div class="mt-3 rounded-2xl bg-gray-50 p-3 dark:bg-gray-800/60">
				<div class="mb-2 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('Click to add. Questions already in the list are hidden.')}
				</div>
				<div class="flex flex-wrap gap-2">
					{#each recommended as item (item.question.prompt)}
						<button
							type="button"
							disabled={atLimit}
							class="rounded-full border border-gray-300 bg-white px-3 py-1.5 text-left text-xs text-gray-700 transition hover:border-gray-500 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-850 dark:text-gray-300"
							on:click={() => addRecommended(item.question)}
						>
							+ {item.question.prompt}
							<span class="text-gray-400"
								>· {$i18n.t(
									KINDS.find((kind) => kind.key === item.question.kind)?.label ?? ''
								)}</span
							>
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<div class="mt-4 space-y-3">
			{#each questions as question, index (question.id)}
				<div class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
					<div class="mb-3 flex flex-wrap items-center gap-2">
						<span class="w-5 shrink-0 text-center text-xs text-gray-400">{index + 1}</span>
						<div class="flex flex-wrap gap-1.5">
							{#each KINDS as kind}
								<button
									type="button"
									aria-pressed={question.kind === kind.key}
									class="{eduSegmentClass(question.kind === kind.key)} !px-3 !py-1 !text-xs"
									on:click={() => setKind(index, kind.key)}
								>
									{$i18n.t(kind.label)}
								</button>
							{/each}
						</div>
						<div class="ml-auto flex items-center gap-0.5 text-gray-400">
							<button
								type="button"
								class="rounded-full p-1.5 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 dark:hover:bg-gray-800 dark:hover:text-gray-200"
								title={$i18n.t('Move up')}
								aria-label={$i18n.t('Move up')}
								disabled={index === 0}
								on:click={() => move(index, -1)}
							>
								<ChevronUp className="size-4" />
							</button>
							<button
								type="button"
								class="rounded-full p-1.5 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 dark:hover:bg-gray-800 dark:hover:text-gray-200"
								title={$i18n.t('Move down')}
								aria-label={$i18n.t('Move down')}
								disabled={index === questions.length - 1}
								on:click={() => move(index, 1)}
							>
								<ChevronDown className="size-4" />
							</button>
							<button
								type="button"
								class="rounded-full p-1.5 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 dark:hover:bg-gray-800 dark:hover:text-gray-200"
								title={$i18n.t('Duplicate')}
								aria-label={$i18n.t('Duplicate')}
								disabled={atLimit}
								on:click={() => duplicate(index)}
							>
								<DocumentDuplicate className="size-4" />
							</button>
							<button
								type="button"
								class="rounded-full p-1.5 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
								title={$i18n.t('Remove')}
								aria-label={$i18n.t('Remove')}
								on:click={() => remove(index)}
							>
								<XMark className="size-4" />
							</button>
						</div>
					</div>

					<input
						value={question.prompt}
						maxlength="300"
						class="w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Question, e.g. What did you change after reading the feedback?')}
						on:input={(event) => update(index, { prompt: event.currentTarget.value })}
					/>

					{#if question.kind === 'text'}
						<input
							value={question.placeholder ?? ''}
							maxlength="200"
							class="mt-2 w-full {EDU_FIELD_CLASS}"
							placeholder={$i18n.t('Hint shown in the answer box (optional)')}
							on:input={(event) => update(index, { placeholder: event.currentTarget.value })}
						/>
					{:else}
						<div class="mt-2 space-y-2 pl-4">
							{#each question.options as option, optionIndex}
								<div class="flex items-center gap-2">
									<span
										class="size-3 shrink-0 border border-gray-400 {question.kind === 'single_choice'
											? 'rounded-full'
											: 'rounded-sm'}"
									></span>
									<input
										value={option}
										maxlength="100"
										data-option-of={question.id}
										class="min-w-0 flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-850 dark:text-gray-100"
										placeholder={$i18n.t('Option {{number}}', { number: optionIndex + 1 })}
										on:input={(event) =>
											updateOption(index, optionIndex, event.currentTarget.value)}
										on:keydown={(event) => {
											if (event.key === 'Enter' && !event.isComposing) {
												event.preventDefault();
												void addOption(index);
											}
										}}
									/>
									<button
										type="button"
										class="shrink-0 rounded-full p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
										title={$i18n.t('Remove')}
										aria-label={$i18n.t('Remove')}
										on:click={() => removeOption(index, optionIndex)}
									>
										<XMark className="size-3.5" />
									</button>
								</div>
							{/each}
							<div class="flex flex-wrap items-center gap-4">
								<EduButton
									size="sm"
									variant="link"
									disabled={question.options.length >= REFLECTION_MAX_OPTIONS}
									on:click={() => addOption(index)}
								>
									+ {$i18n.t('Add option')}
								</EduButton>
								<label
									class="flex cursor-pointer items-center gap-2 text-xs text-gray-600 dark:text-gray-300"
								>
									<input
										type="checkbox"
										class="size-4 accent-black dark:accent-gray-100"
										checked={question.allow_other}
										on:change={(event) =>
											update(index, { allow_other: event.currentTarget.checked })}
									/>
									{$i18n.t('Add an "Other" option with a note')}
								</label>
							</div>
						</div>
					{/if}

					<div
						class="mt-3 flex flex-wrap items-center gap-4 border-t border-gray-100 pt-3 dark:border-gray-800"
					>
						<label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
							{$i18n.t('Shown to')}
							<select
								value={question.show_when}
								class="rounded-lg border border-gray-300 bg-white py-1 pl-2 pr-7 text-xs outline-none dark:border-gray-700 dark:bg-gray-850"
								on:change={(event) =>
									update(index, { show_when: event.currentTarget.value as ReflectionShowWhen })}
							>
								{#each SHOW_WHEN as item}
									<option value={item.key}>{$i18n.t(item.label)}</option>
								{/each}
							</select>
						</label>
						<label
							class="flex cursor-pointer items-center gap-2 text-xs text-gray-600 dark:text-gray-300"
						>
							<input
								type="checkbox"
								class="size-4 accent-black dark:accent-gray-100"
								checked={question.required}
								on:change={(event) => update(index, { required: event.currentTarget.checked })}
							/>
							{$i18n.t('Required')}
						</label>
					</div>
				</div>
			{:else}
				<div
					class="rounded-2xl border border-dashed border-gray-300 px-4 py-6 text-center text-xs text-gray-400 dark:border-gray-700"
				>
					{$i18n.t('No reflection questions. Students will only be asked whether they used AI.')}
				</div>
			{/each}
		</div>
		{#if atLimit}
			<div class="mt-2 text-xs text-amber-600 dark:text-amber-400">
				{$i18n.t('An assignment can have at most {{max}} reflection questions.', {
					max: REFLECTION_MAX_QUESTIONS
				})}
			</div>
		{/if}
	{/if}
</div>

<ConfirmDialog
	bind:show={showReplaceConfirm}
	title={$i18n.t('Replace current questions?')}
	message={$i18n.t('The questions you are editing will be replaced. This cannot be undone.')}
	on:confirm={confirmReplacement}
	on:cancel={() => (pendingReplacement = null)}
/>
