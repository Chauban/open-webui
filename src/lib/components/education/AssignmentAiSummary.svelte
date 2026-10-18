<script lang="ts">
	import { getContext, onMount } from 'svelte';

	import {
		getTeacherAssignmentAiSettings,
		type AiStepThinking,
		type CoachingThinking
	} from '$lib/apis/education';
	import { AI_STEP_TEXT, MODEL_SOURCE_TEXT, THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';
	import EduCard from './EduCard.svelte';

	const i18n = getContext('i18n');

	// 本作业此刻实际生效的 AI 设置,由后端按管理员设置和本作业算出;教师改作业、管理员改下放
	// 之后都以这里为准。读不出来时不挡作业设置页。
	export let assignmentId: string;

	let steps: AiStepThinking[] = [];
	let coaching: CoachingThinking | null = null;
	let failed = false;

	const COACHING_SOURCE_TEXT = {
		admin: 'Administrator default',
		teacher: 'Set for this assignment',
		student: 'Switched off by the student'
	};

	onMount(async () => {
		try {
			const settings = await getTeacherAssignmentAiSettings(localStorage.token, assignmentId);
			steps = settings.steps;
			coaching = settings.coaching_thinking;
		} catch (error) {
			console.error(error);
			failed = true;
		}
	});
</script>

{#if !failed && coaching}
	<EduCard padding="lg" class="mb-4">
		<section data-testid="assignment-ai-summary">
			<h2 class="text-base font-semibold">{$i18n.t('AI settings in effect')}</h2>
			<div class="mt-3 divide-y divide-gray-100 text-sm dark:divide-gray-850">
				{#each steps as step (step.key)}
					<div
						class="flex items-start justify-between gap-4 py-2"
						data-testid={`ai-summary-${step.key}`}
					>
						<div class="min-w-0">
							<div>{$i18n.t(AI_STEP_TEXT[step.key].title)}</div>
							<div class="text-xs text-gray-400">
								{$i18n.t(MODEL_SOURCE_TEXT[step.model_source])} ·
								{step.key === 'coaching_chat'
									? $i18n.t(COACHING_SOURCE_TEXT[coaching.source])
									: $i18n.t('Set by the administrator')}
							</div>
						</div>
						<div class="shrink-0 text-right">
							<div>
								{$i18n.t('Thinking: {{level}}', {
									level: $i18n.t(THINKING_SETTING_TEXT[step.thinking])
								})}
							</div>
							{#if step.key === 'coaching_chat' && coaching.students_choose}
								<div class="text-xs text-gray-400">{$i18n.t('Students can switch it off')}</div>
							{/if}
						</div>
					</div>
				{/each}
			</div>
			<ul class="mt-3 list-disc pl-4 text-xs text-gray-500 dark:text-gray-400">
				<li>
					{$i18n.t(
						'Students cannot change model parameters or add their own system prompt in this assignment’s chat.'
					)}
				</li>
				<li>
					{$i18n.t(
						'Your setting only reaches the coaching chat; the other steps follow the administrator so results stay comparable across classes.'
					)}
				</li>
				<li>
					{$i18n.t('A model without thinking control answers with its own default.')}
				</li>
			</ul>
		</section>
	</EduCard>
{/if}
