<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import DocxPreview from '$lib/components/common/DocxPreview.svelte';
	import { getWritingMaterialAsset } from '$lib/apis/education';
	import type { WritingMaterial } from '$lib/types/writing-materials';
	const i18n: any = getContext('i18n');
	export let materials: WritingMaterial[] = [];
	export let submissionId: string | null = null;
	$: originals = materials.filter(
		(material, index) =>
			materials.findIndex(
				(item) => (item.origin_id ?? item.id) === (material.origin_id ?? material.id)
			) === index
	);
	let downloading = '';
	let error = '';
	let showPreview = false;
	let previewName = '';
	let previewUrl = '';
	let docxData: ArrayBuffer | null = null;
	let previewText = '';
	onDestroy(() => {
		if (previewUrl) URL.revokeObjectURL(previewUrl);
	});
	async function preview(material: WritingMaterial) {
		downloading = material.id;
		error = '';
		try {
			const blob = await getWritingMaterialAsset(
				localStorage.token,
				material.id,
				'original',
				submissionId
			);
			if (previewUrl) URL.revokeObjectURL(previewUrl);
			previewUrl = '';
			docxData = null;
			previewText = '';
			previewName = material.filename;
			if (/\.docx$/i.test(previewName)) docxData = await blob.arrayBuffer();
			else if (/\.pdf$/i.test(previewName))
				previewUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
			else if (/\.(png|jpe?g|webp)$/i.test(previewName)) previewUrl = URL.createObjectURL(blob);
			else if (/\.(txt|md)$/i.test(previewName)) previewText = await blob.text();
			else {
				await download(material);
				return;
			}
			showPreview = true;
		} catch {
			error = $i18n.t('Could not load the original material. Please try again.');
		} finally {
			downloading = '';
		}
	}
	async function download(material: WritingMaterial) {
		downloading = material.id;
		error = '';
		try {
			const blob = await getWritingMaterialAsset(
				localStorage.token,
				material.id,
				'original',
				submissionId
			);
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = material.filename;
			link.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		} catch {
			error = $i18n.t('Could not load the original material. Please try again.');
		} finally {
			downloading = '';
		}
	}
</script>

{#if materials.length}
	<details class="my-2 text-sm text-gray-500 dark:text-gray-400">
		<summary class="cursor-pointer">{$i18n.t('上传原件')} ({originals.length})</summary>
		<p class="mt-2 text-xs">{$i18n.t('这是上传时的原文件，不包含在线修改。')}</p>
		<ul class="mt-2 space-y-2">
			{#each originals as material (material.id)}
				<li class="flex flex-wrap items-center justify-between gap-2">
					<span class="min-w-0 break-all">{material.filename}</span>
					<div class="flex shrink-0 gap-3">
						<button
							type="button"
							class="underline underline-offset-4"
							disabled={!!downloading}
							on:click={() => preview(material)}>{$i18n.t('查看原件')}</button
						>
						<button
							type="button"
							class="underline underline-offset-4"
							disabled={!!downloading}
							on:click={() => download(material)}>{$i18n.t('下载上传原件')}</button
						>
					</div>
				</li>
			{/each}
		</ul>
		{#if error}<p role="alert" class="mt-2 text-red-600">{error}</p>{/if}
	</details>
{/if}

<Modal
	bind:show={showPreview}
	size="xl"
	title={previewName}
	description={$i18n.t('这是上传时的原文件，不包含在线修改。')}
>
	{#if docxData}<DocxPreview data={docxData} />
	{:else if /\.pdf$/i.test(previewName)}<iframe
			title={previewName}
			class="h-[70vh] w-full"
			src={previewUrl}
		></iframe>
	{:else if previewUrl}<img src={previewUrl} alt={previewName} class="max-w-full" />
	{:else}<pre class="whitespace-pre-wrap break-words">{previewText}</pre>{/if}
</Modal>
