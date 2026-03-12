<script lang="ts">
	// @ts-nocheck
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';

	import RichTextInput from '$lib/components/common/RichTextInput.svelte';
	import AssignmentChatWorkspace from '$lib/components/education/AssignmentChatWorkspace.svelte';
	import {
		autosaveWritingSession,
		createProvenanceSegments,
		createWritingVersion,
		getAssignmentWorkspace,
		submitAssignment
	} from '$lib/apis/education';

	getContext('i18n');

	let loaded = false;
	let loadError = '';
	let assignment = null;
	let writingSession = null;
	let chat = null;
	let editor = null;
	let noteJson = null;
	let noteText = '';
	let noteHtml = '';
	let saveStatus = 'Unsaved';
	let saving = false;
	let showSubmitModal = false;

	let aiHelpType = '帮助突破卡壳';
	let reflectionText = '';

	let lastText = '';
	let pendingSource: null | { sourceType: string; sourceMessageId?: string | null; text?: string } = null;
	let unsavedSegments = [];
	let autoSaveTimer: ReturnType<typeof setTimeout> | null = null;

	const helpTypes = ['Outline', 'Examples', 'Polish', 'Unblock', 'Logic', 'Other'];

	const makeSegment = (sourceType: string, segmentText: string, sourceMessageId?: string | null) => ({
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
		saveStatus = 'Saving...';
		if (autoSaveTimer) clearTimeout(autoSaveTimer);
		autoSaveTimer = setTimeout(() => {
			void persistDraft('autosave');
		}, 1200);
	};

	const persistDraft = async (triggerType = 'autosave') => {
		if (!writingSession) return;
		if (saving) return;
		saving = true;
		saveStatus = 'Saving...';

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

			saveStatus = 'Saved';
		} catch (error) {
			console.error(error);
			saveStatus = 'Save failed';
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

	const insertAssistantContent = ({ detail }) => {
		if (!editor) return;
		pendingSource = { sourceType: 'ai_inserted', sourceMessageId: detail.sourceMessageId, text: detail.content };
		editor.chain().focus().insertContent(detail.content).run();
	};

	const submit = async () => {
		if (reflectionText.trim().length < 30) {
			toast.error('Reflection must be at least 30 characters.');
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
			toast.success('Submitted');
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
			chat = workspace.chat;
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
	<div
		class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col overflow-hidden bg-stone-100 transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''}"
	>
		<nav class="w-full px-2.5 pt-1.5 backdrop-blur-xl drag-region">
			<div class="flex items-center">
				{#if $mobile}
					<div class="{$showSidebar ? 'md:hidden' : ''} flex flex-none items-center self-end mt-1.5">
						<Tooltip
							content={$showSidebar ? 'Close Sidebar' : 'Open Sidebar'}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class="flex cursor-pointer rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-850"
								on:click={() => showSidebar.set(!$showSidebar)}
							>
								<div class="self-center p-1.5">
									<SidebarIcon />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div class="ml-2 flex w-full items-center justify-between py-1">
					<div>
						<div class="text-xs uppercase tracking-[0.18em] text-gray-500">Growth Writing</div>
						<h1 class="text-xl font-semibold text-gray-900">{assignment.title}</h1>
					</div>
					<div class="flex items-center gap-3">
						<div class="rounded-full bg-white px-3 py-1 text-sm text-gray-600">{saveStatus}</div>
						<button
							class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white"
							on:click={() => {
								showSubmitModal = true;
							}}
						>
							Submit
						</button>
					</div>
				</div>
			</div>
		</nav>

		<div class="min-h-0 flex flex-1 overflow-hidden">
			<div class="min-w-0 flex-1 bg-white">
				<AssignmentChatWorkspace
					chatId={writingSession.chat_id}
					sessionId={writingSession.id}
					{chat}
					on:insert={insertAssistantContent}
				/>
			</div>

			<div class="hidden h-full w-full max-w-[560px] min-w-[360px] flex-col border-l border-gray-200 bg-stone-50 lg:flex">
				<div class="border-b border-gray-200 bg-white px-5 py-4">
					<div class="text-sm font-semibold">Draft</div>
					<div class="text-xs text-gray-500">
						Track typed text, AI insertions, and in-app AI paste.
					</div>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
					<RichTextInput
						bind:editor
						bind:value={noteJson}
						json={true}
						placeholder="Write the final draft here."
						className="input-prose min-h-[70vh]"
						onChange={handleContentChange}
						on:paste={async (event) => {
							const clipboardEvent = event?.detail?.event ?? event;
							const payload =
								clipboardEvent?.clipboardData?.getData(
									'application/x-openwebui-ai-snippet+json'
								) ?? '';
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

		{#if showSubmitModal}
			<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
				<div class="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
					<h2 class="text-xl font-semibold text-gray-900">Micro Reflection</h2>
					<p class="mt-1 text-sm text-gray-500">Submission is blocked until reflection is complete.</p>

					<div class="mt-5">
						<label class="mb-2 block text-sm font-medium text-gray-800">Main help from AI</label>
						<select bind:value={aiHelpType} class="w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm">
							{#each helpTypes as item}
								<option value={item}>{item}</option>
							{/each}
						</select>
					</div>

					<div class="mt-4">
						<label class="mb-2 block text-sm font-medium text-gray-800">
							Which AI suggestion did you reject, or where did the AI perform poorly?
						</label>
						<textarea
							bind:value={reflectionText}
							class="min-h-40 w-full rounded-2xl border border-gray-300 px-3 py-3 text-sm outline-none"
							placeholder="Recommended 50-100 characters. Minimum 30."
						></textarea>
					</div>

					<div class="mt-6 flex justify-end gap-3">
						<button
							class="rounded-full border border-gray-300 px-4 py-2 text-sm"
							on:click={() => {
								showSubmitModal = false;
							}}
						>
							Cancel
						</button>
						<button class="rounded-full bg-gray-900 px-4 py-2 text-sm text-white" on:click={submit}>
							Submit
						</button>
					</div>
				</div>
			</div>
		{/if}
	</div>
{:else if loadError}
	<div class="mx-auto max-w-3xl px-4 py-16">
		<div class="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
			{loadError}
		</div>
	</div>
{/if}
