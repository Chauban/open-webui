<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { mobile } from '$lib/stores';

	import RichTextInput from '$lib/components/common/RichTextInput.svelte';
	import Chat from '$lib/components/chat/Chat.svelte';
	import {
		autosaveWritingSession,
		createProvenanceSegments,
		createWritingVersion,
		getAssignmentWorkspace,
		submitAssignment
	} from '$lib/apis/education';

	const i18n = getContext('i18n');

	let loaded = false;
	let loadError = '';
	let assignment = null;
	let writingSession = null;
	let editor = null;
	let noteJson = null;
	let noteText = '';
	let noteHtml = '';
	let saveStatusKey = 'Unsaved';
	let saving = false;
	let showSubmitModal = false;
	let showMobileDraft = false;

	let aiHelpType = "Help Break Through Writer's Block";
	let reflectionText = '';

	let lastText = '';
	let pendingSource: null | { sourceType: string; sourceMessageId?: string | null; text?: string } =
		null;
	let unsavedSegments = [];
	let autoSaveTimer: ReturnType<typeof setTimeout> | null = null;

	const helpTypes = [
		'Outline',
		'Examples',
		'Polish',
		"Help Break Through Writer's Block",
		'Strengthen Reasoning',
		'Other'
	];

	const makeSegment = (
		sourceType: string,
		segmentText: string,
		sourceMessageId?: string | null
	) => ({
		segment_id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
		source_type: sourceType,
		segment_text: segmentText,
		source_message_id: sourceMessageId ?? null,
		start_offset: null,
		end_offset: null,
		metadata_json: null
	});

	const extractInsertedSegment = (prev: string, next: string) => {
		if (next.length <= prev.length) return null;

		let start = 0;
		while (start < prev.length && prev[start] === next[start]) {
			start += 1;
		}

		let end = 0;
		while (
			end < prev.length - start &&
			prev[prev.length - 1 - end] === next[next.length - 1 - end]
		) {
			end += 1;
		}

		const inserted = next.slice(start, next.length - end);
		if (!inserted.trim()) return null;

		return { inserted, startOffset: start, endOffset: start + inserted.length };
	};

	const scheduleSave = () => {
		saveStatusKey = 'Saving...';
		if (autoSaveTimer) clearTimeout(autoSaveTimer);
		autoSaveTimer = setTimeout(() => {
			void persistDraft('autosave');
		}, 1200);
	};

	const persistDraft = async (triggerType = 'autosave') => {
		if (!writingSession) return;
		if (saving) return;
		saving = true;
		saveStatusKey = 'Saving...';

		try {
			await autosaveWritingSession(localStorage.token, writingSession.id, {
				content_json: noteJson,
				content_html: noteHtml,
				content_text: noteText,
				save_reason: triggerType
			});

			const version = await createWritingVersion(localStorage.token, writingSession.id, {
				trigger_type: triggerType,
				content_json: noteJson,
				content_text: noteText
			});

			if (unsavedSegments.length > 0) {
				await createProvenanceSegments(localStorage.token, writingSession.id, {
					version_id: version.id,
					segments: unsavedSegments
				});
				unsavedSegments = [];
			}

			saveStatusKey = 'Saved';
		} catch (error) {
			console.error(error);
			saveStatusKey = 'Save failed';
		} finally {
			saving = false;
		}
	};

	const handleContentChange = (content) => {
		noteJson = content.json;
		noteHtml = content.html;
		noteText = content.md;

		const inserted = extractInsertedSegment(lastText, noteText);
		if (inserted) {
			const sourceType = pendingSource?.sourceType ?? 'user_typed';
			const sourceMessageId = pendingSource?.sourceMessageId ?? null;
			unsavedSegments = [
				...unsavedSegments,
				{
					...makeSegment(sourceType, inserted.inserted, sourceMessageId),
					start_offset: inserted.startOffset,
					end_offset: inserted.endOffset
				}
			];
		}

		lastText = noteText;
		pendingSource = null;
		scheduleSave();
	};

	const insertAssistantContent = async (message) => {
		if (!editor) return;
		pendingSource = {
			sourceType: 'ai_inserted',
			sourceMessageId: message.id ?? null,
			text: message.content ?? ''
		};
		editor
			.chain()
			.focus()
			.insertContent(message.content ?? '')
			.run();
	};

	const copyAssistantContentWithSource = async (message) => {
		await navigator.clipboard.write([
			new ClipboardItem({
				'text/plain': new Blob([message.content ?? ''], { type: 'text/plain' }),
				'application/x-openwebui-ai-snippet+json': new Blob(
					[
						JSON.stringify({
							sourceType: 'ai_pasted',
							sourceMessageId: message.id ?? null,
							text: message.content ?? ''
						})
					],
					{ type: 'application/x-openwebui-ai-snippet+json' }
				)
			})
		]);
		toast.success($i18n.t('Copied with source'));
	};

	const submit = async () => {
		if (reflectionText.trim().length < 30) {
			toast.error($i18n.t('Reflection must be at least 30 characters.'));
			return;
		}

		await persistDraft('submit_preflight');

		try {
			await submitAssignment(localStorage.token, assignment.id, {
				writing_session_id: writingSession.id,
				final_content_json: noteJson,
				final_content_html: noteHtml,
				final_content_text: noteText,
				ai_help_type: aiHelpType,
				reflection_text: reflectionText
			});
			toast.success($i18n.t('Assignment submitted'));
			await goto('/me/writing');
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	onMount(async () => {
		try {
			const workspace = await getAssignmentWorkspace(localStorage.token, $page.params.assignmentId);
			assignment = workspace.assignment;
			writingSession = workspace.writing_session;
			noteJson = workspace.note?.data?.content?.json ?? null;
			noteHtml = workspace.note?.data?.content?.html ?? '';
			noteText = workspace.note?.data?.content?.md ?? '';
			lastText = noteText;
			loaded = true;
		} catch (error) {
			loadError = `${error?.detail ?? error}`;
			toast.error(loadError);
		}
	});
</script>

{#if loaded}
	<Chat
		chatIdProp={writingSession.chat_id}
		responseInsertHandler={insertAssistantContent}
		responseCopyHandler={copyAssistantContentWithSource}
		responseInsertLabel="Insert to Assignment"
		showRightPanel={!$mobile}
		rightPanelDefaultSize={34}
		rightPanelMinSize={26}
		rightPanelClassName="hidden lg:flex"
	>
		<div
			slot="right-panel"
			class="h-full w-full flex-col border-l border-gray-200 bg-stone-50 lg:flex"
		>
			<div class="border-b border-gray-200 bg-white px-5 py-4">
				<div class="flex items-start justify-between gap-4">
					<div>
						<div class="text-xs uppercase tracking-[0.18em] text-gray-500">
							{$i18n.t('Assignment Writing')}
						</div>
						<div class="text-sm font-semibold text-gray-900">{assignment.title}</div>
						<div class="text-xs text-gray-500">
							{$i18n.t('Track typed text, AI insertions, and in-app AI paste.')}
						</div>
					</div>
					<div class="flex items-center gap-2">
						<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
							{$i18n.t(saveStatusKey)}
						</div>
						<button
							class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white"
							on:click={() => {
								showSubmitModal = true;
							}}
						>
							{$i18n.t('Submit Assignment')}
						</button>
					</div>
				</div>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
				<RichTextInput
					bind:editor
					bind:value={noteJson}
					json={true}
					placeholder={$i18n.t('Write the final assignment here.')}
					className="input-prose min-h-[70vh]"
					onChange={handleContentChange}
					on:paste={async (event) => {
						const clipboardEvent = event?.detail?.event ?? event;
						const payload =
							clipboardEvent?.clipboardData?.getData('application/x-openwebui-ai-snippet+json') ??
							'';
						if (!payload) return;
						try {
							const meta = JSON.parse(payload);
							pendingSource = {
								sourceType: meta.sourceType ?? 'ai_pasted',
								sourceMessageId: meta.sourceMessageId ?? null,
								text: meta.text ?? ''
							};
						} catch (error) {
							console.error(error);
						}
					}}
				/>
			</div>
		</div>
	</Chat>

	{#if $mobile}
		<div class="pointer-events-none fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
			<div
				class="pointer-events-auto flex items-center gap-2 rounded-full border border-gray-200 bg-white/95 px-3 py-2 shadow-lg backdrop-blur"
			>
				<div class="rounded-full bg-stone-100 px-3 py-1 text-xs text-gray-600">
					{$i18n.t(saveStatusKey)}
				</div>
				<button
					class="rounded-full border border-gray-300 px-3 py-1.5 text-sm text-gray-700"
					on:click={() => {
						showMobileDraft = true;
					}}
				>
					{$i18n.t('Assignment Content')}
				</button>
				<button
					class="rounded-full bg-gray-900 px-3 py-1.5 text-sm text-white"
					on:click={() => {
						showSubmitModal = true;
					}}
				>
					{$i18n.t('Submit Assignment')}
				</button>
			</div>
		</div>
	{/if}

	{#if showMobileDraft}
		<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
		<div
			class="fixed inset-0 z-40 flex items-end bg-black/40 lg:hidden"
			on:click={() => (showMobileDraft = false)}
		>
			<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
			<div
				class="flex h-[78dvh] w-full flex-col rounded-t-3xl bg-stone-50"
				on:click|stopPropagation
			>
				<div class="border-b border-gray-200 bg-white px-5 py-4">
					<div class="flex items-start justify-between gap-4">
						<div>
							<div class="text-xs uppercase tracking-[0.18em] text-gray-500">
								{$i18n.t('Assignment Writing')}
							</div>
							<div class="text-sm font-semibold text-gray-900">{assignment.title}</div>
						</div>
						<button
							class="rounded-full border border-gray-300 px-3 py-1.5 text-sm"
							on:click={() => {
								showMobileDraft = false;
							}}
						>
							{$i18n.t('Close')}
						</button>
					</div>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
					<RichTextInput
						bind:editor
						bind:value={noteJson}
						json={true}
						placeholder={$i18n.t('Write the final assignment here.')}
						className="input-prose min-h-[60vh]"
						onChange={handleContentChange}
						on:paste={async (event) => {
							const clipboardEvent = event?.detail?.event ?? event;
							const payload =
								clipboardEvent?.clipboardData?.getData('application/x-openwebui-ai-snippet+json') ??
								'';
							if (!payload) return;
							try {
								const meta = JSON.parse(payload);
								pendingSource = {
									sourceType: meta.sourceType ?? 'ai_pasted',
									sourceMessageId: meta.sourceMessageId ?? null,
									text: meta.text ?? ''
								};
							} catch (error) {
								console.error(error);
							}
						}}
					/>
				</div>
			</div>
		</div>
	{/if}

	{#if showSubmitModal}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
			<div class="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="text-xl font-semibold text-gray-900">
					{$i18n.t('Reflection Before Submitting Assignment')}
				</h2>
				<p class="mt-1 text-sm text-gray-500">
					{$i18n.t('Complete your reflection before submitting your assignment.')}
				</p>

				<div class="mt-5">
					<label for="ai-help-type" class="mb-2 block text-sm font-medium text-gray-800">
						{$i18n.t('What did AI mainly help you with?')}
					</label>
					<select
						id="ai-help-type"
						bind:value={aiHelpType}
						class="w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm"
					>
						{#each helpTypes as item}
							<option value={item}>{$i18n.t(item)}</option>
						{/each}
					</select>
				</div>

				<div class="mt-4">
					<label for="reflection-text" class="mb-2 block text-sm font-medium text-gray-800">
						{$i18n.t('Which AI suggestion did you reject, or where did AI perform poorly?')}
					</label>
					<textarea
						id="reflection-text"
						bind:value={reflectionText}
						class="min-h-40 w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm outline-none"
						placeholder={$i18n.t('Recommended 50-100 characters. Minimum 30.')}
					></textarea>
				</div>

				<div class="mt-6 flex justify-end gap-3">
					<button
						class="rounded-full border border-gray-300 px-4 py-2 text-sm"
						on:click={() => {
							showSubmitModal = false;
						}}
					>
						{$i18n.t('Cancel')}
					</button>
					<button class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white" on:click={submit}>
						{$i18n.t('Submit Assignment')}
					</button>
				</div>
			</div>
		</div>
	{/if}
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	</div>
{/if}
