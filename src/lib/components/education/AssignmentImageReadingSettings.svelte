<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import type { ImageParsingModelView } from '$lib/apis/education';

	export let enabled = false;
	export let photoEnabled = false;
	export let platformModel: ImageParsingModelView | null = null;
	export let photoTranscriptionModel: ImageParsingModelView | null = null;
	const i18n = getContext<Writable<I18n>>('i18n');
</script>

<div class="space-y-4">
	<div class="space-y-2">
		<label class="flex cursor-pointer items-center gap-3 text-sm font-medium">
			<input type="checkbox" role="switch" bind:checked={photoEnabled} class="h-4 w-4 rounded" />
			{$i18n.t('照片转正文')}
		</label>
		<p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
			{$i18n.t(
				'允许学生把手写或打印稿照片转为可编辑正文，原图保留供核对。只转录、不润色，默认关闭。'
			)}
		</p>
		<p class="break-words text-xs text-gray-600 dark:text-gray-300">
			{$i18n.t('照片转正文模型：{{model}}', {
				model: photoTranscriptionModel?.name ?? $i18n.t('Not configured')
			})}
		</p>
		{#if photoEnabled && !photoTranscriptionModel?.available}<p
				role="status"
				class="text-xs text-amber-700 dark:text-amber-300"
			>
				{$i18n.t('照片转正文模型尚未配置或不可用，请联系管理员。')}
			</p>{/if}
	</div>
	<div class="space-y-2">
		<label class="flex cursor-pointer items-center gap-3 text-sm font-medium">
			<input type="checkbox" role="switch" bind:checked={enabled} class="h-4 w-4 rounded" />
			{$i18n.t('AI 读取参考图片')}
		</label>
		<p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
			{$i18n.t(
				'允许学生按需读取参考图片中的文字和图表信息，供 AI 辅导参考；不会自动加入正文。默认关闭，原图始终可上传、查看和提交。'
			)}
		</p>
		<p class="break-words text-xs text-gray-600 dark:text-gray-300">
			{$i18n.t('参考图片识读模型：{{model}}', {
				model: platformModel?.name ?? $i18n.t('Not configured')
			})}
		</p>
		{#if enabled && !platformModel?.available}<p
				role="status"
				class="text-xs text-amber-700 dark:text-amber-300"
			>
				{$i18n.t('参考图片识读模型尚未配置或不可用，请联系管理员。')}
			</p>{/if}
	</div>
	<p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
		{$i18n.t('两项能力独立设置。关闭不会删除已有正文、原图或历史提交；识别结果请对照原图核对。')}
	</p>
</div>
