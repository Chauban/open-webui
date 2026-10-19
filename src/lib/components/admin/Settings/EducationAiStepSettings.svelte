<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import type {
		AiStep,
		AiStepKey,
		AiStepPolicy,
		AiStepView,
		PlatformStepPolicy,
		ThinkingControl,
		ThinkingSetting
	} from '$lib/apis/education';
	import {
		AI_STEP_TEXT,
		FOLLOW_MODEL_TEXT,
		MISSING_MODEL_TEXT,
		MODEL_SOURCE_TEXT,
		THINKING_CONTROL_TEXT,
		THINKING_SETTINGS,
		THINKING_SETTING_TEXT
	} from '$lib/utils/ai-steps';
	import { modelDefaultNote, quirkText, type ModelDefaultGroup } from '$lib/utils/provider-quirks';
	import type { ThinkingSupport } from '$lib/utils/thinking-support';
	import ProviderQuirksPanel from '$lib/components/ProviderQuirksPanel.svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 教学各 AI 步骤用哪个模型、思考多少。行由后端登记(ai_steps.py)下发,新增步骤自动出现在表里。
	// 只有辅导对话可以下放给教师(再由教师交给学生开关),它的模型始终是学生选的;平台步骤只由管理员定。
	export let policy: AiStepPolicy;
	export let steps: AiStep[] = [];
	/** 后端算的每行现状:指定的模型还在不在。 */
	export let views: AiStepView[] = [];
	/** 可选的模型(管理员看到的全部模型)。 */
	export let models: Array<{
		id: string;
		name?: string;
		owned_by?: string;
		info?: any;
		thinking_support?: ThinkingSupport | null;
	}> = [];
	/** 「模型默认」对目前接入的模型意味着什么(后端按接入的模型与能力表算出)。 */
	export let modelDefaultMeaning: ModelDefaultGroup[] = [];
	export let disabled = false;
	export let onChange: (policy: AiStepPolicy) => void = () => {};

	type PlatformStepKey = Exclude<AiStepKey, 'coaching_chat'>;

	$: coachingStep = steps.find((step) => step.key === 'coaching_chat');
	$: platformSteps = steps.filter(
		(step): step is AiStep & { key: PlatformStepKey } => step.key !== 'coaching_chat'
	);
	$: viewsByKey = Object.fromEntries(views.map((view) => [view.key, view]));

	// 竞技场模型背后是一组模型,不能当某一步的固定模型;图片识别只列没有标明不能看图的。
	const choices = (key: PlatformStepKey) =>
		models.filter(
			(model) =>
				model.owned_by !== 'arena' &&
				(key !== 'image_parsing' || model.info?.meta?.capabilities?.vision !== false)
		);
	// 指定的模型已被删掉:后端说不在,或前端的模型列表里也没有。
	const isMissing = (key: PlatformStepKey) => {
		const model = policy[key].model;
		if (!model) return false;
		return viewsByKey[key]?.model_available === false || !models.some((item) => item.id === model);
	};

	const settingLabel = (setting: ThinkingSetting) => $i18n.t(THINKING_SETTING_TEXT[setting]);

	// 后端按所选模型与档位算好的注意事项(随每次保存刷新),写成话放在这一行下面。
	// 写成响应式声明:views 或语言变了,模板里的调用跟着重算。
	$: stepNotes = (key: AiStepKey) => {
		const view = viewsByKey[key];
		return (view?.quirks ?? [])
			.map((quirk) => quirkText(quirk, view?.thinking_format ?? null, $i18n.t))
			.filter((text): text is string => Boolean(text));
	};

	const setStep = (key: PlatformStepKey, change: Partial<PlatformStepPolicy>) =>
		onChange({ ...policy, [key]: { ...policy[key], ...change } });

	const setCoaching = (change: Partial<AiStepPolicy['coaching_chat']>) =>
		onChange({ ...policy, coaching_chat: { ...policy.coaching_chat, ...change } });

	const CONTROLS = Object.keys(THINKING_CONTROL_TEXT) as ThinkingControl[];
	const SELECT_CLASS =
		'w-44 rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300';
</script>

<div class="flex flex-col gap-3" data-testid="ai-step-settings">
	<div>
		<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
			{$i18n.t('AI step settings')}
		</div>
		<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			{$i18n.t(
				'Which model each AI step uses and how much it thinks before answering. A model you pick here is used even if students or teachers cannot use it in chat. Models without the Thinking control capability always use their own default.'
			)}
		</p>
		<!-- 每一行都能选「模型默认」,在表头说清它是什么 -->
		<p
			class="mt-1 text-[0.6875rem] text-gray-500 dark:text-gray-400"
			data-testid="model-default-note"
		>
			{modelDefaultNote(modelDefaultMeaning, $i18n.t)}
		</p>
	</div>

	<div class="divide-y divide-gray-100 dark:divide-gray-850">
		{#if coachingStep}
			<div class="flex flex-col gap-2 py-2" data-testid="ai-step-row-coaching_chat">
				<div class="min-w-0">
					<div class="text-xs text-gray-700 dark:text-gray-300">
						{$i18n.t(AI_STEP_TEXT.coaching_chat.title)}
					</div>
					<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t(AI_STEP_TEXT.coaching_chat.hint)}
						{$i18n.t(
							'Model: {{source}} — students pick from the models they can access; restrict that list with model access control.',
							{ source: $i18n.t(MODEL_SOURCE_TEXT[coachingStep.model_source]) }
						)}
						{$i18n.t(
							'The only step a teacher can set; when it is left to teachers, the default below applies until they choose.'
						)}
					</p>
					<ProviderQuirksPanel
						notes={stepNotes('coaching_chat')}
						testid="ai-step-quirks-coaching_chat"
						compact
					/>
				</div>
				<div class="flex flex-wrap items-center justify-end gap-2">
					<select
						class={SELECT_CLASS}
						value={policy.coaching_chat.control}
						{disabled}
						aria-label={$i18n.t('Who sets thinking in the coaching chat')}
						on:change={(event) =>
							setCoaching({ control: event.currentTarget.value as ThinkingControl })}
					>
						{#each CONTROLS as control}
							<option value={control}>{$i18n.t(THINKING_CONTROL_TEXT[control])}</option>
						{/each}
					</select>
					<select
						class={SELECT_CLASS}
						value={policy.coaching_chat.default}
						{disabled}
						aria-label={$i18n.t('Default thinking in the coaching chat')}
						on:change={(event) =>
							setCoaching({ default: event.currentTarget.value as ThinkingSetting })}
					>
						{#each THINKING_SETTINGS as setting}
							<option value={setting}>{settingLabel(setting)}</option>
						{/each}
					</select>
				</div>
			</div>
		{/if}

		{#each platformSteps as step (step.key)}
			<div class="flex flex-col gap-2 py-2" data-testid={`ai-step-row-${step.key}`}>
				<div class="min-w-0">
					<div class="text-xs text-gray-700 dark:text-gray-300">
						{$i18n.t(AI_STEP_TEXT[step.key].title)}
					</div>
					<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t(AI_STEP_TEXT[step.key].hint)}
						{$i18n.t('Set by: {{control}}.', { control: $i18n.t(THINKING_CONTROL_TEXT.admin) })}
					</p>
					{#if AI_STEP_TEXT[step.key].note}
						<p class="mt-0.5 text-[0.6875rem] text-amber-600 dark:text-amber-500">
							{$i18n.t(AI_STEP_TEXT[step.key].note ?? '')}
						</p>
					{/if}
					{#if isMissing(step.key)}
						<p
							class="mt-0.5 text-[0.6875rem] text-rose-500"
							data-testid={`ai-step-missing-${step.key}`}
						>
							{$i18n.t(MISSING_MODEL_TEXT[step.model_source])}
						</p>
					{/if}
					<ProviderQuirksPanel
						notes={stepNotes(step.key)}
						testid={`ai-step-quirks-${step.key}`}
						compact
					/>
				</div>
				<div class="flex flex-wrap items-center justify-end gap-2">
					<select
						class={SELECT_CLASS}
						value={policy[step.key].model ?? ''}
						{disabled}
						aria-label={$i18n.t('Model for {{step}}', {
							step: $i18n.t(AI_STEP_TEXT[step.key].title)
						})}
						on:change={(event) => setStep(step.key, { model: event.currentTarget.value || null })}
					>
						<option value="">{$i18n.t(FOLLOW_MODEL_TEXT[step.model_source])}</option>
						{#if isMissing(step.key)}
							<option value={policy[step.key].model}>{policy[step.key].model}</option>
						{/if}
						{#each choices(step.key) as model (model.id)}
							<option value={model.id}>{model.name ?? model.id}</option>
						{/each}
					</select>
					<select
						class={SELECT_CLASS}
						value={policy[step.key].thinking}
						{disabled}
						aria-label={$i18n.t(AI_STEP_TEXT[step.key].title)}
						on:change={(event) =>
							setStep(step.key, { thinking: event.currentTarget.value as ThinkingSetting })}
					>
						{#each THINKING_SETTINGS as setting}
							<option value={setting}>{settingLabel(setting)}</option>
						{/each}
					</select>
				</div>
			</div>
		{/each}
	</div>

	<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
		{$i18n.t(
			'A teacher’s setting only reaches the coaching chat; the other steps always follow this table, so their results stay comparable across classes.'
		)}
	</p>
</div>
