<script lang="ts">
	// @ts-nocheck
	import { createEventDispatcher, getContext, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { v4 as uuidv4 } from 'uuid';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		chats,
		currentChatPage,
		models,
		settings,
		temporaryChatEnabled,
		chatId as chatIdStore,
		chatTitle
	} from '$lib/stores';
	import { getChatList, updateChatById } from '$lib/apis/chats';
	import { upsertWritingChatMessage } from '$lib/apis/education';
	import { generateOpenAIChatCompletion } from '$lib/apis/openai';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { createMessagesList } from '$lib/utils';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let chatId = '';
	export let sessionId = '';
	export let chat = null;

	let loading = true;
	let loadError = '';
	let initialized = false;
	let generating = false;
	let prompt = '';
	let history = {
		messages: {},
		currentId: null
	};
	let selectedModels = [''];
	let atSelectedModel = undefined;
	let params = {};
	let chatFiles = [];
	let files = [];
	let autoScroll = true;
	let selectedToolIds = [];
	let selectedFilterIds = [];
	let imageGenerationEnabled = false;
	let webSearchEnabled = false;
	let codeInterpreterEnabled = false;
	let showCommands = false;
	let taskIds = null;
	let messageQueue = [];

	let messagesContainerElement;

	const messageList = () => {
		if (!history?.currentId) return [];
		const list = [];
		let current = history.messages[history.currentId];
		const visited = new Set();
		while (current && !visited.has(current.id)) {
			list.unshift(current);
			visited.add(current.id);
			current = current.parentId ? history.messages[current.parentId] : null;
		}
		return list;
	};

	const syncFromChat = async (chatRecord) => {
		const chatPayload = chatRecord?.chat ?? {};
		history =
			(chatPayload?.history ?? undefined) !== undefined
				? chatPayload.history
				: {
						messages: {},
						currentId: null
					};
		selectedModels =
			(chatPayload?.models ?? undefined) !== undefined
				? chatPayload.models
				: [$models[0]?.id ?? ''];
		params = chatPayload?.params ?? {};
		chatFiles = chatPayload?.files ?? [];
		chatTitle.set(chatPayload?.title ?? 'Assignment Chat');
		await chatIdStore.set(chatId);
		await tick();
	};

	const persistMessage = async (messageId: string, message: Record<string, unknown>) => {
		if (!sessionId) return;
		await upsertWritingChatMessage(localStorage.token, sessionId, messageId, {
			message
		}).catch(() => null);
	};

	const saveChat = async () => {
		chat = await updateChatById(localStorage.token, chatId, {
			models: selectedModels,
			history,
			messages: createMessagesList(history, history.currentId),
			params,
			files: chatFiles
		});
		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, $currentChatPage));
	};

	const scrollToBottom = async () => {
		await tick();
		messagesContainerElement?.scrollTo({
			top: messagesContainerElement.scrollHeight,
			behavior: 'auto'
		});
	};

	const insertHandler = async (message) => {
		dispatch('insert', {
			content: message.content,
			sourceMessageId: message.id
		});
	};

	const copyHandler = async (message) => {
		try {
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
			toast.success('Copied with source');
		} catch (error) {
			toast.error('Failed to copy');
		}
	};

	const sendPrompt = async (content: string, parentMessageId = null, overrideMessages = null) => {
		if (!content?.trim() || generating) return;

		generating = true;
		const userMessageId = uuidv4();
		const responseMessageId = uuidv4();
		const resolvedParentId = parentMessageId ?? history.currentId ?? null;

		const userMessage = {
			id: userMessageId,
			parentId: resolvedParentId,
			childrenIds: [responseMessageId],
			role: 'user',
			content: content.trim(),
			timestamp: Math.floor(Date.now() / 1000)
		};

		const responseMessage = {
			id: responseMessageId,
			parentId: userMessageId,
			childrenIds: [],
			role: 'assistant',
			content: '',
			done: false,
			model: selectedModels[0] ?? $models[0]?.id ?? '',
			timestamp: Math.floor(Date.now() / 1000)
		};

		if (resolvedParentId && history.messages[resolvedParentId]) {
			const siblingIds = history.messages[resolvedParentId].childrenIds ?? [];
			history.messages[resolvedParentId].childrenIds = [...siblingIds, userMessageId];
		}

		history.messages[userMessageId] = userMessage;
		history.messages[responseMessageId] = responseMessage;
		history.currentId = responseMessageId;

		await persistMessage(userMessageId, userMessage);
		await saveChat();
		await scrollToBottom();

		try {
			const baseMessages =
				overrideMessages ??
				createMessagesList(history, userMessageId).map((message) => ({
					role: message.role,
					content: message.content
				}));

			const res = await generateOpenAIChatCompletion(
				localStorage.token,
				{
					stream: false,
					model: selectedModels[0] ?? $models[0]?.id ?? '',
					messages: baseMessages,
					chat_id: chatId
				},
				`${WEBUI_BASE_URL}/api`
			);

			const assistantContent = res?.choices?.[0]?.message?.content ?? '';
			history.messages[responseMessageId] = {
				...history.messages[responseMessageId],
				content: assistantContent,
				done: true
			};
			await persistMessage(responseMessageId, history.messages[responseMessageId]);
			await saveChat();
			await scrollToBottom();
		} catch (error) {
			delete history.messages[responseMessageId];
			delete history.messages[userMessageId];
			if (resolvedParentId && history.messages[resolvedParentId]) {
				history.messages[resolvedParentId].childrenIds = (
					history.messages[resolvedParentId].childrenIds ?? []
				).filter((id) => id !== userMessageId);
			}
			history.currentId = resolvedParentId;
			toast.error(`${error}`);
		} finally {
			generating = false;
		}
	};

	const submitMessage = async () => {};

	const initializeWorkspace = async () => {
		try {
			loadError = '';
			if ($temporaryChatEnabled) {
				temporaryChatEnabled.set(false);
			}

			await syncFromChat(chat);
			await scrollToBottom();
		} catch (error) {
			console.error(error);
			loadError = `${error}`;
			toast.error(loadError);
		} finally {
			loading = false;
		}
	};

	$: if (!initialized) {
		initialized = true;
		void initializeWorkspace();
	}
</script>

<div class="flex h-full min-h-0 flex-col bg-white">
	{#if loading}
		<div class="flex h-full w-full items-center justify-center">
			<Spinner className="size-5" />
		</div>
	{:else if loadError}
		<div class="flex h-full items-center justify-center px-6">
			<div class="rounded-3xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
				{loadError}
			</div>
		</div>
	{:else}
		<div class="border-b border-gray-200 px-5 py-4">
			<div class="flex items-center justify-between gap-3">
				<div>
					<div class="text-xs uppercase tracking-[0.18em] text-gray-500">Assignment Chat</div>
					<div class="text-lg font-semibold text-gray-900">{chat?.chat?.title ?? 'New Chat'}</div>
				</div>
				<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
					{selectedModels[0] || 'No model'}
				</div>
			</div>
		</div>

		<div
			class="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-5"
			bind:this={messagesContainerElement}
		>
			{#if messageList().length === 0}
				<div class="m-auto max-w-md text-center">
					<div class="text-lg font-semibold text-gray-900">Start with the assignment assistant</div>
					<div class="mt-2 text-sm text-gray-500">
						Ask for an outline, examples, or revision help, then insert useful answers into the draft.
					</div>
				</div>
			{:else}
				<div class="space-y-4">
					{#each messageList() as message (message.id)}
						<div class={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
							<div
								class={`max-w-[85%] rounded-3xl px-4 py-3 ${
									message.role === 'user'
										? 'bg-emerald-50 text-gray-900'
										: 'bg-stone-100 text-gray-900'
								}`}
							>
								<div class="mb-2 text-[11px] uppercase tracking-[0.14em] text-gray-500">
									{message.role === 'user' ? 'You' : 'Assistant'}
								</div>
								<div class="whitespace-pre-wrap break-words text-sm leading-6">
									{message.content || (message.role === 'assistant' && generating ? 'Generating...' : '')}
								</div>

								{#if message.role === 'assistant' && message.content}
									<div class="mt-3 flex flex-wrap gap-2">
										<button
											class="rounded-full border border-gray-300 px-3 py-1 text-xs"
											on:click={() => insertHandler(message)}
										>
											Insert to Draft
										</button>
										<button
											class="rounded-full border border-gray-300 px-3 py-1 text-xs"
											on:click={() => copyHandler(message)}
										>
											Copy with Source
										</button>
									</div>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<div class="border-t border-gray-200 px-5 py-4">
			<textarea
				class="min-h-28 w-full rounded-3xl border border-gray-300 px-4 py-3 text-sm outline-none"
				bind:value={prompt}
				placeholder="Ask about this assignment, then insert useful parts into the draft"
				disabled={generating}
			></textarea>
			<div class="mt-3 flex justify-end">
				<button
					class="rounded-full bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
					on:click={async () => {
						await sendPrompt(prompt);
						prompt = '';
					}}
					disabled={generating || !prompt.trim()}
				>
					{generating ? 'Generating...' : 'Send'}
				</button>
			</div>
		</div>
	{/if}
</div>
