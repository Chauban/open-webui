<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import type { AiStep, AiStepKey, ThinkingPolicy, ThinkingSetting } from '$lib/apis/education';
	import {
		AI_STEP_TEXT,
		MODEL_SOURCE_TEXT,
		THINKING_CONTROL_TEXT,
		THINKING_SETTINGS,
		THINKING_SETTING_TEXT
	} from '$lib/utils/ai-steps';

	const i18n: Writable<i18nType> = getContext('i18n');

	// 教学各 AI 步骤的思考档位。行由后端登记(ai_steps.py)下发,新增步骤自动出现在表里;
	// 平台步骤只由管理员定,教师的设置碰不到它们。
	export let policy: ThinkingPolicy;
	export let steps: AiStep[] = [];
	export let disabled = false;
	export let onChange: (policy: ThinkingPolicy) => void = () => {};

	type PlatformStepKey = Exclude<AiStepKey, 'coaching_chat'>;

	$: platformSteps = steps.filter(
		(step): step is AiStep & { key: PlatformStepKey } => step.key !== 'coaching_chat'
	);

	const settingLabel = (key: AiStepKey, setting: ThinkingSetting) =>
		key === 'first_read' && setting === 'model_default'
			? $i18n.t('Model default (recommended)')
			: $i18n.t(THINKING_SETTING_TEXT[setting]);

	const setStep = (key: PlatformStepKey, value: ThinkingSetting) =>
		onChange({ ...policy, [key]: value });
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
			'These steps always follow this table, never a teacher’s setting, so their results stay comparable across classes.'
		)}
	</p>
</div>
