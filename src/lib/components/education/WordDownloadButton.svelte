<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { downloadWritingWord } from '$lib/apis/education';
	import { resolveErrorMessage } from '$lib/utils/education';
	import type { WritingNode } from '$lib/utils/writing-document';
	import EduButton from './EduButton.svelte';
	export let sessionId: string | undefined = undefined;
	export let submissionId: string | undefined = undefined;
	export let versionId: string | undefined = undefined;
	export let contentJson: WritingNode | undefined = undefined;
	export let disabled = false;
	export let beforeDownload: () => Promise<void> = async () => {};
	const i18n: any = getContext('i18n');
	let busy = false;
	async function download() {
		busy = true;
		try {
			await beforeDownload();
			await downloadWritingWord(localStorage.token, {
				sessionId,
				submissionId,
				versionId,
				contentJson
			});
		} catch (error) {
			toast.error(resolveErrorMessage(error, (key) => $i18n.t(key)));
		} finally {
			busy = false;
		}
	}
</script>

<EduButton size="sm" disabled={disabled || busy} on:click={download}>
	{$i18n.t(busy ? '正在生成 Word…' : submissionId ? '下载已提交稿（Word）' : '下载当前稿（Word）')}
</EduButton>
