<script lang="ts">
	// 提交前的读者试读环节。
	//
	// 这里的 AI 是「质疑读者」，和左侧的辅导助手是相反的角色：辅导助手负责帮，
	// 这位只负责问，而且它的输出进不了正文。所以这个界面刻意做成卡片式单轮推进，
	// 不是聊天流 —— 聊天框天然无限、可跑题、可已读不回，压不住有限回合。
	//
	// 措辞上不出现「对抗」「挑战」「找茬」：那会让学生进入防御姿态。学生的心理
	// 位置应该是「我在准备」，不是「我在被考」。
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import EduButton from '$lib/components/education/EduButton.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { resolveErrorMessage } from '$lib/utils/education';
	import {
		respondToChallenge,
		skipAssignmentChallenge,
		startAssignmentChallenge
	} from '$lib/apis/education';
	import type { ChallengeDetail } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let assignment: any;
	export let writingSessionId: string;
	export let modelId: string;
	export let detail: ChallengeDetail | null = null;
	/** 回去修改：关掉试读，回到编辑器。 */
	export let onBackToRevise: () => void;
	/** 继续提交：进入原来的反思弹窗。 */
	export let onContinue: () => void;
	/** 试读状态变了就报上去，写作面板要据此渲染待改清单。 */
	export let onDetailChange: (next: ChallengeDetail | null) => void = () => {};

	let busy = false;
	let responseText = '';

	$: plannedRounds = detail?.session?.planned_rounds ?? assignment?.challenge_rounds ?? 3;
	$: turns = detail?.turns ?? [];
	$: currentTurn = turns.find((turn) => turn.response_text === null) ?? null;
	$: closing = detail?.session?.closing_summary_json ?? null;
	$: phase = !detail ? 'contract' : detail.session.status === 'completed' ? 'closing' : 'turn';

	const applyDetail = (next: ChallengeDetail | null) => {
		detail = next;
		responseText = '';
		onDetailChange(next);
	};

	const start = async () => {
		if (busy) return;
		busy = true;
		try {
			applyDetail(
				await startAssignmentChallenge(localStorage.token, assignment.id, {
					writing_session_id: writingSessionId,
					model: modelId
				})
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, $i18n.t('Could not start the read-through.')));
		} finally {
			busy = false;
		}
	};

	const send = async () => {
		if (busy || !currentTurn) return;
		const text = responseText.trim();
		if (!text) {
			toast.error($i18n.t('Write your response first.'));
			return;
		}
		busy = true;
		try {
			applyDetail(
				await respondToChallenge(localStorage.token, detail!.session.id, {
					turn_no: currentTurn.turn_no,
					response_text: text,
					model: modelId
				})
			);
		} catch (error) {
			toast.error(resolveErrorMessage(error, $i18n.t('Could not send your response.')));
		} finally {
			busy = false;
		}
	};

	const skip = async () => {
		if (busy) return;
		busy = true;
		try {
			// 还没开始就跳过：没有 session 可标记，直接进反思。
			if (detail) {
				applyDetail(await skipAssignmentChallenge(localStorage.token, detail.session.id));
			}
			onContinue();
		} catch (error) {
			toast.error(resolveErrorMessage(error, $i18n.t('Could not skip the read-through.')));
		} finally {
			busy = false;
		}
	};
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
	<div
		class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white p-6 shadow-2xl dark:bg-gray-850"
	>
		{#if phase === 'contract'}
			<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('A reader takes a look first')}
			</h2>
			<div class="mt-4 space-y-2 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
				<!-- 先亮契约，否则学生会一直向它求助，然后觉得这 AI 很笨。 -->
				<p>{$i18n.t('I am a reader who does not agree with you.')}</p>
				<p>
					{$i18n.t(
						'I will not rewrite anything for you. I will only say where you have not convinced me.'
					)}
				</p>
				<p>
					{$i18n.t('{{count}} rounds in total. Answer in your own words.', {
						count: plannedRounds
					})}
				</p>
			</div>
			<div class="mt-6 flex items-center justify-between gap-3">
				<EduButton variant="link" disabled={busy} on:click={skip}>
					{$i18n.t('Skip this time')}
				</EduButton>
				<EduButton
					variant="primary"
					class="flex items-center gap-2"
					disabled={busy}
					on:click={start}
				>
					{#if busy}
						<Spinner className="size-4" />
						{$i18n.t('The reader is reading...')}
					{:else}
						{$i18n.t('Start')}
					{/if}
				</EduButton>
			</div>
		{:else if phase === 'turn' && currentTurn}
			<div class="text-xs uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
				{$i18n.t('Round {{current}} of {{total}}', {
					current: currentTurn.turn_no,
					total: plannedRounds
				})}
			</div>

			<div class="mt-4 flex-1 space-y-4 overflow-y-auto pr-1">
				{#each turns.filter((turn) => turn.response_text !== null) as answered (answered.id)}
					<div class="rounded-2xl bg-stone-50 px-4 py-3 dark:bg-gray-900">
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Round {{current}} of {{total}}', {
								current: answered.turn_no,
								total: plannedRounds
							})}
						</div>
						<p class="mt-1 whitespace-pre-wrap text-sm text-gray-600 dark:text-gray-300">
							{answered.challenge_text}
						</p>
						<p
							class="mt-2 whitespace-pre-wrap border-l-2 border-gray-300 pl-3 text-sm text-gray-800 dark:border-gray-700 dark:text-gray-200"
						>
							{answered.response_text}
						</p>
					</div>
				{/each}

				<div class="rounded-2xl border border-gray-200 px-4 py-4 dark:border-gray-800">
					<p class="whitespace-pre-wrap text-sm leading-relaxed text-gray-900 dark:text-gray-100">
						{currentTurn.challenge_text}
					</p>
				</div>

				<div>
					<label
						for="challenge-response"
						class="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
					>
						{$i18n.t('Your response')}
					</label>
					<textarea
						id="challenge-response"
						bind:value={responseText}
						rows="5"
						disabled={busy}
						class="w-full {EDU_FIELD_CLASS}"
						placeholder={$i18n.t('Answer in your own words. This reader will not write it for you.')}
					/>
				</div>
			</div>

			<div class="mt-5 flex items-center justify-between gap-3">
				<EduButton variant="link" disabled={busy} on:click={skip}>
					{$i18n.t('Skip this time')}
				</EduButton>
				<EduButton
					variant="primary"
					class="flex items-center gap-2"
					disabled={busy || responseText.trim().length === 0}
					on:click={send}
				>
					{#if busy}
						<Spinner className="size-4" />
						{$i18n.t('The reader is reading...')}
					{:else}
						{$i18n.t('Send response')}
					{/if}
				</EduButton>
			</div>
		{:else}
			<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('What the reader thinks now')}
			</h2>

			<div class="mt-4 flex-1 space-y-5 overflow-y-auto pr-1">
				{#if closing && closing.stood.length > 0}
					<div>
						<div class="text-sm font-medium text-gray-800 dark:text-gray-200">
							{$i18n.t('You held these up')}
						</div>
						<ul class="mt-2 space-y-1.5">
							{#each closing.stood as item}
								<li class="flex gap-1.5 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
									<span aria-hidden="true">·</span><span>{item}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/if}

				{#if closing && closing.unresolved.length > 0}
					<div>
						<div class="text-sm font-medium text-gray-800 dark:text-gray-200">
							{$i18n.t('These still need work')}
						</div>
						<ul class="mt-2 space-y-1.5">
							{#each closing.unresolved as item}
								<li class="flex gap-1.5 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
									<span aria-hidden="true">·</span><span>{item}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/if}

				{#if !closing || (closing.stood.length === 0 && closing.unresolved.length === 0)}
					<p class="text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t('The reader did not leave a summary this time.')}
					</p>
				{/if}
			</div>

			<div class="mt-6 flex items-center justify-between gap-3">
				<!-- 「回去修改」是这个环节能真正作用于正文的唯一入口，必须给。 -->
				<EduButton variant="secondary" on:click={onBackToRevise}>
					{$i18n.t('Back to revise')}
				</EduButton>
				<EduButton variant="primary" on:click={onContinue}>
					{$i18n.t('Continue to submit')}
				</EduButton>
			</div>
		{/if}
	</div>
</div>
