<script lang="ts">
	import { getContext } from 'svelte';

	import { eduSegmentClass } from '$lib/components/education/styles';
	import type { ThinkingControl, ThinkingSetting } from '$lib/apis/education';
	import { THINKING_SETTINGS, THINKING_SETTING_TEXT } from '$lib/utils/ai-steps';

	const i18n = getContext('i18n');

	// 辅导对话的思考档位,只在管理员下放后出现。只管辅导对话:通读与补看、读者试读、
	// 图片识别始终按管理员的设置,各班结果才可比。
	export let control: ThinkingControl;
	export let adminDefault: ThinkingSetting;
	export let value: ThinkingSetting | null = null;
	export let studentsChoose = false;
	export let disabled = false;

	$: options = [
		{
			key: null,
			label: $i18n.t('Admin default ({{level}})', {
				level: $i18n.t(THINKING_SETTING_TEXT[adminDefault])
			})
		},
		...THINKING_SETTINGS.map((setting) => ({
			key: setting,
			label: $i18n.t(THINKING_SETTING_TEXT[setting])
		}))
	];
</script>

<div data-testid="assignment-thinking">
	<div class="mb-2 text-sm font-semibold">{$i18n.t('AI thinking in the coaching chat')}</div>
	<div class="flex flex-wrap gap-2">
		{#each options as option}
			<button
				type="button"
				class={eduSegmentClass(value === option.key)}
				{disabled}
				on:click={() => (value = option.key)}
			>
				{option.label}
			</button>
		{/each}
	</div>
	<div class="mt-2 text-xs text-gray-400">
		{$i18n.t(
			'Coaching chat only. The first read, follow-up review, reader check and image parsing follow the administrator’s settings.'
		)}
	</div>

	{#if control === 'student'}
		<label class="mt-3 flex items-start gap-2 text-sm">
			<input type="checkbox" class="mt-0.5" bind:checked={studentsChoose} {disabled} />
			<span>
				{$i18n.t('Let students switch thinking off')}
				<span class="block text-xs text-gray-400">
					{$i18n.t(
						'Students get a switch in the chat: on uses the level above, off answers without thinking. Each reply records which one was used.'
					)}
				</span>
			</span>
		</label>
	{/if}
</div>
