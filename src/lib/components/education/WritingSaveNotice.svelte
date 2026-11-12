<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as I18n } from 'i18next';
	import type { WritingSaveProblem } from '$lib/utils/writing-save';
	import type { WritingBackup } from '$lib/utils/writing-backup';
	export let problem: WritingSaveProblem | null = null;
	export let localSafe = true;
	export let backups: WritingBackup[] = [];
	export let busy = false;
	export let readonly = false;
	export let chatBlocked = false;
	export let onRetry = () => {};
	export let onLogin = () => {};
	export let onCopy = () => {};
	export let onDownload = () => {};
	export let onRestore = (_backup: WritingBackup) => {};
	export let onDiscard = (_backup: WritingBackup) => {};
	export let onDownloadBackup = (_backup: WritingBackup) => {};
	const i18n = getContext<Writable<I18n>>('i18n');
	let selected = '';
	$: if (!backups.some((item) => item.id === selected)) selected = backups[0]?.id ?? '';
	$: backup = backups.find((item) => item.id === selected) ?? backups[0];
	const button =
		'rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-medium hover:bg-amber-100 disabled:opacity-50 dark:border-amber-800 dark:hover:bg-amber-950';
</script>

{#if problem || !localSafe || backups.length || chatBlocked}
	<div
		class="m-3 max-h-[40dvh] shrink-0 overflow-y-auto rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-gray-850 dark:text-amber-100"
		data-testid="writing-save-notice"
	>
		<div role={problem || !localSafe ? 'alert' : 'status'} aria-live="polite">
			{#if problem}<p>{$i18n.t(problem.message)}</p>{/if}
			{#if !localSafe}<p class="font-medium">
					{$i18n.t('本浏览器无法备份稿件，请立即复制全文或下载文字备份。')}
				</p>
			{:else if problem}<p class="mt-1 text-xs">
					{$i18n.t('当前稿件已备份在本浏览器，尚未全部同步到服务器。')}
				</p>{/if}
			{#if chatBlocked}<p class="mt-1">
					{$i18n.t('消息尚未发送，输入已保留。请先处理稿件保存，再点击发送。')}
				</p>{/if}
		</div>
		{#if problem?.requestId}
			<details class="mt-2 text-xs break-all">
				<summary>{$i18n.t('保存错误详情')}</summary>
				<p>{$i18n.t('错误编号')}：{problem.requestId}</p>
				{#if problem.field}<p>{$i18n.t('检查位置')}：{problem.field}</p>{/if}
			</details>
		{/if}
		{#if problem || !localSafe || chatBlocked}
			<div class="mt-2 flex flex-wrap gap-2">
				{#if problem?.login}<button class={button} on:click={onLogin}>{$i18n.t('重新登录')}</button>
				{:else}<button class={button} disabled={busy || readonly} on:click={onRetry}
						>{$i18n.t('重试保存')}</button
					>{/if}
				<button class={button} on:click={onCopy}>{$i18n.t('复制全文')}</button>
				<button class={button} on:click={onDownload}>{$i18n.t('下载文字备份')}</button>
			</div>
		{/if}
		{#if backup}
			<p class="mt-2 font-medium">{$i18n.t('发现本浏览器中尚未同步的稿件。')}</p>
			<p class="mt-1 text-xs">
				{$i18n.t(
					'恢复会用所选备份继续编辑并保存。请先核对或下载当前稿件；其他页面仍在编辑时，请先关闭其他页面。'
				)}
			</p>
			<label class="mt-2 block text-xs"
				>{$i18n.t('选择本地备份')}
				<select
					bind:value={selected}
					class="ml-2 max-w-full rounded border bg-white px-2 py-1 text-gray-900"
				>
					{#each backups as item}<option value={item.id}
							>{new Date(item.updatedAt).toLocaleString()}</option
						>{/each}
				</select>
			</label>
			<div class="mt-2 flex flex-wrap gap-2">
				<button class={button} disabled={busy || readonly} on:click={() => onRestore(backup)}
					>{$i18n.t('恢复此稿并保存')}</button
				>
				<button class={button} on:click={() => onDownloadBackup(backup)}
					>{$i18n.t('下载所选备份')}</button
				>
				<button class={button} on:click={onDownload}>{$i18n.t('下载当前稿件')}</button>
				<button class={button} on:click={() => onDiscard(backup)}>{$i18n.t('放弃所选备份')}</button>
			</div>
		{/if}
	</div>
{/if}
