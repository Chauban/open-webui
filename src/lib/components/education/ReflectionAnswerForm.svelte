<script lang="ts">
	// 学生作答提交前反思。教师编辑器里的「学生视角预览」也用它，保证所见即所得。
	//
	// 「这次用了 AI 吗」是系统固定题，永远排第一；其余题目按作业设定渲染，
	// 并按 show_when 随这道题的答案出现或隐藏。
	import { getContext } from 'svelte';

	import type { ReflectionQuestion } from '$lib/apis/education/types';
	import { EDU_FIELD_CLASS, eduSegmentClass } from '$lib/components/education/styles';
	import {
		emptyReflectionAnswerDraft,
		isReflectionQuestionVisible,
		type AiUsage,
		type ReflectionAnswerDraft,
		type ReflectionAnswerDrafts
	} from '$lib/utils/reflection-questions';

	const i18n = getContext('i18n');

	export let questions: ReflectionQuestion[] = [];
	export let aiUsage: AiUsage = null;
	export let drafts: ReflectionAnswerDrafts = {};
	/** 预览里区分同一页上的多份表单，避免 label for 撞 id。 */
	export let idPrefix = 'reflection';
	export let onChange: () => void = () => {};

	$: visibleQuestions = questions.filter((question) =>
		isReflectionQuestionVisible(question, aiUsage)
	);

	const draftOf = (drafts: ReflectionAnswerDrafts, id: string) =>
		drafts[id] ?? emptyReflectionAnswerDraft();

	const patchDraft = (id: string, patch: Partial<ReflectionAnswerDraft>) => {
		drafts = { ...drafts, [id]: { ...draftOf(drafts, id), ...patch } };
		onChange();
	};

	const selectAiUsage = (value: 'used' | 'none') => {
		aiUsage = value;
		onChange();
	};

	const toggleOption = (question: ReflectionQuestion, option: string) => {
		const draft = draftOf(drafts, question.id);
		const isSelected = draft.selected.includes(option);
		if (question.kind === 'single_choice') {
			patchDraft(question.id, { selected: isSelected ? [] : [option], otherChosen: false });
			return;
		}
		patchDraft(question.id, {
			selected: isSelected
				? draft.selected.filter((item) => item !== option)
				: [...draft.selected, option]
		});
	};

	const toggleOther = (question: ReflectionQuestion) => {
		const draft = draftOf(drafts, question.id);
		patchDraft(question.id, {
			otherChosen: !draft.otherChosen,
			selected: question.kind === 'single_choice' ? [] : draft.selected
		});
	};
</script>

<div class="space-y-5">
	<div>
		<div class="mb-2 text-sm font-medium text-gray-800 dark:text-gray-200">
			{$i18n.t('Did you use AI for this submission?')}
		</div>
		<div class="flex flex-wrap gap-2">
			<button
				type="button"
				aria-pressed={aiUsage === 'used'}
				class={eduSegmentClass(aiUsage === 'used')}
				on:click={() => selectAiUsage('used')}
			>
				{$i18n.t('Used AI')}
			</button>
			<button
				type="button"
				aria-pressed={aiUsage === 'none'}
				class={eduSegmentClass(aiUsage === 'none')}
				on:click={() => selectAiUsage('none')}
			>
				{$i18n.t('Did not use AI')}
			</button>
		</div>
	</div>

	{#each visibleQuestions as question (question.id)}
		{@const draft = draftOf(drafts, question.id)}
		<div>
			<label
				for="{idPrefix}-{question.id}"
				class="mb-2 flex items-baseline gap-2 text-sm font-medium text-gray-800 dark:text-gray-200"
			>
				<span class="whitespace-pre-wrap">{question.prompt}</span>
				{#if question.kind === 'multi_choice'}
					<span class="shrink-0 text-xs font-normal text-gray-400"
						>{$i18n.t('Select all that apply')}</span
					>
				{/if}
				{#if !question.required}
					<span class="shrink-0 text-xs font-normal text-gray-400">{$i18n.t('Optional')}</span>
				{/if}
			</label>

			{#if question.kind === 'text'}
				<textarea
					id="{idPrefix}-{question.id}"
					value={draft.text}
					class="min-h-20 w-full {EDU_FIELD_CLASS}"
					placeholder={question.placeholder ?? ''}
					maxlength="2000"
					on:input={(event) => patchDraft(question.id, { text: event.currentTarget.value })}
				></textarea>
			{:else}
				<div id="{idPrefix}-{question.id}" class="flex flex-wrap gap-2">
					{#each question.options as option}
						<button
							type="button"
							aria-pressed={draft.selected.includes(option)}
							class={eduSegmentClass(draft.selected.includes(option))}
							on:click={() => toggleOption(question, option)}
						>
							{option}
						</button>
					{/each}
					{#if question.allow_other}
						<button
							type="button"
							aria-pressed={draft.otherChosen}
							class={eduSegmentClass(draft.otherChosen)}
							on:click={() => toggleOther(question)}
						>
							{$i18n.t('Other')}
						</button>
					{/if}
				</div>
				{#if question.allow_other && draft.otherChosen}
					<input
						value={draft.otherText}
						class="mt-2 w-full {EDU_FIELD_CLASS}"
						maxlength="300"
						placeholder={$i18n.t('Briefly describe your answer')}
						aria-label={$i18n.t('Other')}
						on:input={(event) => patchDraft(question.id, { otherText: event.currentTarget.value })}
					/>
				{/if}
			{/if}
		</div>
	{/each}

	{#if aiUsage == null && questions.some((question) => question.show_when !== 'always')}
		<div class="text-xs text-gray-400">
			{$i18n.t('More questions appear after you answer whether you used AI.')}
		</div>
	{/if}
</div>
