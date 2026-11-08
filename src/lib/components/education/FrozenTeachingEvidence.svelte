<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');
	export let evidence: {
		revisions: {
			id: string;
			revision: number;
			config: { ai: { prompt: string; model_id: string; thinking: string; web_search?: boolean } };
			change_summary: string;
		}[];
		calls: { id: string; revision_id: string; context: Record<string, unknown> }[];
	} | null = null;
</script>

{#if evidence}<details class="my-4 rounded-xl border p-4 dark:border-gray-700">
		<summary>{$i18n.t('本次提交冻结的辅导版本与调用证据')}</summary>
		<p class="my-2 text-sm text-gray-500">
			{$i18n.t('这里展示每次调用当时使用的版本，之后发布的方案不会改写本次记录。')}
		</p>
		{#each evidence.revisions as version}<details class="my-3">
				<summary
					>v{version.revision} · {version.config.ai.model_id} · {$i18n.t(
						version.config.ai.thinking
					)} · {version.change_summary}</summary
				>
				<pre class="whitespace-pre-wrap text-sm">{version.config.ai.prompt}</pre>
				<p class="text-sm">
					{$i18n.t(version.config.ai.web_search ? '资料搜索开启' : '资料搜索关闭')}
				</p>
				{#each evidence.calls.filter((call) => call.revision_id === version.id) as call}<details
						class="my-2"
					>
						<summary>{String(call.context.purpose)} · {call.id}</summary>
						<pre
							class="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(
								call.context,
								null,
								2
							)}</pre>
					</details>{/each}
			</details>{/each}
	</details>{/if}
