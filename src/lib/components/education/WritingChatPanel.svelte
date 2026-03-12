<script lang="ts">
	// @ts-nocheck
	import { createEventDispatcher } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { updateChatById } from '$lib/apis/chats';
	import { upsertWritingChatMessage } from '$lib/apis/education';
	import { generateOpenAIChatCompletion } from '$lib/apis/openai';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { models } from '$lib/stores';

	const dispatch = createEventDispatcher();

	export let chatId = '';
	export let sessionId = '';
	export let chat: any = null;
	export let disabled = false;

	let prompt = '';
	let generating = false;

	const messageList = () => {
		if (!chat?.chat?.history?.currentId) return [];
		const messages: any[] = [];
		let current = chat.chat.history.messages[chat.chat.history.currentId];
		while (current) {
			messages.unshift(current);
			current = current.parentId ? chat.chat.history.messages[current.parentId] : null;
		}
		return messages;
	};

	const saveChat = async () => {
		await updateChatById(localStorage.token, chatId, chat.chat);
	};

	const persistMessage = async (messageId: string, message: Record<string, unknown>) => {
		if (!sessionId) return;
		await upsertWritingChatMessage(localStorage.token, sessionId, messageId, {
			message
		});
	};

	const appendAssistantMessage = async (userMessage: any, content: string) => {
		if (!chat) return;
		const assistantId = crypto.randomUUID();
		const assistantMessage = {
			id: assistantId,
			parentId: userMessage.id,
			childrenIds: [],
			role: 'assistant',
			content,
			model: $models[0]?.id ?? '',
			timestamp: Date.now()
		};

		chat.chat.history.messages[userMessage.id].childrenIds = [assistantId];
		chat.chat.history.messages[assistantId] = assistantMessage;
		chat.chat.history.currentId = assistantId;
		await persistMessage(assistantId, assistantMessage);
		await saveChat();
	};

	const send = async () => {
		if (!prompt.trim() || generating || disabled) return;
		if (!chat) return;

		const userMessageId = crypto.randomUUID();
		const previousId = chat?.chat?.history?.currentId ?? null;
		const userMessage = {
			id: userMessageId,
			parentId: previousId,
			childrenIds: [],
			role: 'user',
			content: prompt.trim(),
			timestamp: Date.now()
		};

		if (!chat.chat.history.messages) {
			chat.chat.history.messages = {};
		}
		chat.chat.history.messages[userMessageId] = userMessage;
		chat.chat.history.currentId = userMessageId;
		if (previousId && chat.chat.history.messages[previousId]) {
			const previousChildren = chat.chat.history.messages[previousId].childrenIds ?? [];
			chat.chat.history.messages[previousId].childrenIds = [...previousChildren, userMessageId];
		}

		const payloadMessages = messageList().map((message) => ({
			role: message.role,
			content: message.content
		}));

		const currentPrompt = prompt;
		prompt = '';
		generating = true;
		await persistMessage(userMessageId, userMessage);
		await saveChat();

		try {
			const res = await generateOpenAIChatCompletion(
				localStorage.token,
				{
					stream: false,
					model: $models[0]?.id ?? '',
					messages: payloadMessages,
					chat_id: chatId
				},
				`${WEBUI_BASE_URL}/api`
			);
			const content = res?.choices?.[0]?.message?.content ?? '';
			await appendAssistantMessage(userMessage, content);
			dispatch('message', { role: 'assistant', content, parentId: userMessageId });
		} catch (error) {
			toast.error(`${error}`);
			prompt = currentPrompt;
		} finally {
			generating = false;
		}
	};
</script>

<div class="flex h-full flex-col rounded-3xl border border-gray-200 bg-white">
	<div class="border-b border-gray-200 px-4 py-3">
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="text-sm font-semibold">Assignment Assistant</div>
				<div class="text-xs text-gray-500">
					This conversation belongs only to this assignment and will appear in teacher review.
				</div>
			</div>
			<div class="rounded-full bg-stone-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-gray-600">
				Task Scoped
			</div>
		</div>
	</div>

	<div class="flex-1 space-y-3 overflow-y-auto px-4 py-4">
		{#each messageList() as message (message.id)}
			<div
				class={`rounded-2xl px-3 py-3 text-sm ${
					message.role === 'assistant' ? 'bg-stone-50' : 'bg-emerald-50/60'
				}`}
			>
				<div class="mb-2 text-[11px] uppercase tracking-[0.14em] text-gray-500">
					{message.role === 'assistant' ? 'AI' : 'You'}
				</div>
				<div class="whitespace-pre-wrap break-words">{message.content}</div>
				{#if message.role === 'assistant'}
					<div class="mt-3 flex gap-2">
						<button
							class="rounded-full border border-gray-300 px-3 py-1 text-xs"
							on:click={() => dispatch('insert', { content: message.content, sourceMessageId: message.id })}
						>
							Insert to Draft
						</button>
						<button
							class="rounded-full border border-gray-300 px-3 py-1 text-xs"
							on:click={async () => {
								await navigator.clipboard.write([
									new ClipboardItem({
										'text/plain': new Blob([message.content], { type: 'text/plain' }),
										'application/x-openwebui-ai-snippet+json': new Blob(
											[
												JSON.stringify({
													sourceType: 'ai_pasted',
													sourceMessageId: message.id,
													text: message.content
												})
											],
											{ type: 'application/x-openwebui-ai-snippet+json' }
										)
									})
								]);
								toast.success('Copied');
							}}
						>
							Copy with source
						</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>

	<div class="border-t border-gray-200 p-4">
		<div class="mb-3 rounded-2xl bg-stone-50 px-3 py-2 text-xs text-gray-500">
			Use this panel for task-specific asking, outlining, examples, and revision help.
		</div>
		<textarea
			class="min-h-24 w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm outline-none"
			bind:value={prompt}
			placeholder="Ask about this assignment, then insert useful parts into the draft"
			disabled={disabled || generating}
		></textarea>
		<div class="mt-3 flex justify-end">
			<button
				class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
				on:click={send}
				disabled={disabled || generating}
			>
				{generating ? 'Generating...' : 'Send'}
			</button>
		</div>
	</div>
</div>
