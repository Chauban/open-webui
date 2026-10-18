<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import type {
		AiStep,
		AiStepKey,
		ThinkingControl,
		ThinkingPolicy,
		ThinkingSetting
	} from '$lib/apis/education';
	import {
		AI_STEP_TEXT,
		MODEL_SOURCE_TEXT,
		THINKING_CONTROL_TEXT,
		THINKING_SETTINGS,
		THINKING_SETTING_TEXT
	} from '$lib/utils/ai-steps';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 教学各 AI 步骤的思考档位。行由后端登记(ai_steps.py)下发,新增步骤自动出现在表里。
	// 只有辅导对话可以下放给教师(再由教师交给学生开关);平台步骤只由管理员定。
	export let policy: ThinkingPolicy;
	export let steps: AiStep[] = [];
	export let disabled = false;
	export let onChange: (policy: ThinkingPolicy) => void = () => {};

	type PlatformStepKey = Exclude<AiStepKey, 'coaching_chat'>;

	$: coachingStep = steps.find((step) => step.key === 'coaching_chat');
	$: platformSteps = steps.filter(
		(step): step is AiStep & { key: PlatformStepKey } => step.key !== 'coaching_chat'
	);

	const settingLabel = (key: AiStepKey, setting: ThinkingSetting) =>
		key === 'first_read' && setting === 'model_default'
			? $i18n.t('Model default (recommended)')
			: $i18n.t(THINKING_SETTING_TEXT[setting]);

	const setStep = (key: PlatformStepKey, value: ThinkingSetting) =>
		onChange({ ...policy, [key]: value });

	const setCoaching = (change: Partial<ThinkingPolicy['coaching_chat']>) =>
		onChange({ ...policy, coaching_chat: { ...policy.coaching_chat, ...change } });

	const CONTROLS = Object.keys(THINKING_CONTROL_TEXT) as ThinkingControl[];
</script>

<div class="flex flex-col gap-3" data-testid="thinking-policy">
	<div>
		<div class="text-xs font-medium text-gray-700 dark:text-gray-300">
			{$i18n.t('AI thinking settings')}
		</div>
		<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
			{$i18n.t(
				'How much each AI step thinks before answering. Models without the Thinking control capability always use their own default.'
			)}
		</p>
	</div>

	<div class="divide-y divide-gray-100 dark:divide-gray-850">
		{#if coachingStep}
			<div class="flex flex-col gap-2 py-2" data-testid="thinking-row-coaching_chat">
				<div class="min-w-0">
					<div class="text-xs text-gray-700 dark:text-gray-300">
						{$i18n.t(AI_STEP_TEXT.coaching_chat.title)}
					</div>
					<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t(AI_STEP_TEXT.coaching_chat.hint)}
						{$i18n.t('Model: {{source}}.', {
							source: $i18n.t(MODEL_SOURCE_TEXT[coachingStep.model_source])
						})}
						{$i18n.t(
							'The only step a teacher can set; when it is left to teachers, the default below applies until they choose.'
						)}
					</p>
				</div>
				<div class="flex flex-wrap items-center justify-end gap-2">
					<select
						class="rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300"
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
						class="w-40 rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300"
						value={policy.coaching_chat.default}
						{disabled}
						aria-label={$i18n.t('Default thinking in the coaching chat')}
						on:change={(event) =>
							setCoaching({ default: event.currentTarget.value as ThinkingSetting })}
					>
						{#each THINKING_SETTINGS as setting}
							<option value={setting}>{settingLabel('coaching_chat', setting)}</option>
						{/each}
					</select>
				</div>
			</div>
		{/if}
		{#each platformSteps as step (step.key)}
			<div
				class="flex items-start justify-between gap-4 py-2"
				data-testid={`thinking-row-${step.key}`}
			>
				<div class="min-w-0">
					<div class="text-xs text-gray-700 dark:text-gray-300">
						{$i18n.t(AI_STEP_TEXT[step.key].title)}
					</div>
					<p class="mt-0.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t(AI_STEP_TEXT[step.key].hint)}
						{$i18n.t('Model: {{source}}.', {
							source: $i18n.t(MODEL_SOURCE_TEXT[step.model_source])
						})}
						{$i18n.t('Set by: {{control}}.', { control: $i18n.t(THINKING_CONTROL_TEXT.admin) })}
					</p>
					{#if AI_STEP_TEXT[step.key].note}
						<p class="mt-0.5 text-[0.6875rem] text-amber-600 dark:text-amber-500">
							{$i18n.t(AI_STEP_TEXT[step.key].note ?? '')}
						</p>
					{/if}
				</div>
				<select
					class="w-40 shrink-0 rounded-lg bg-transparent px-2 py-1 text-xs text-gray-700 outline-hidden dark:text-gray-300"
					value={policy[step.key]}
					{disabled}
					aria-label={$i18n.t(AI_STEP_TEXT[step.key].title)}
					on:change={(event) => setStep(step.key, event.currentTarget.value as ThinkingSetting)}
				>
					{#each THINKING_SETTINGS as setting}
						<option value={setting}>{settingLabel(step.key, setting)}</option>
					{/each}
				</select>
			</div>
		{/each}
	</div>

	<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
		{$i18n.t(
			'A teacher’s setting only reaches the coaching chat; the other steps always follow this table, so their results stay comparable across classes.'
		)}
	</p>
</div>
