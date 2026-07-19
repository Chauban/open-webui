<script lang="ts">
	import { getContext } from 'svelte';

	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ReviewResultCard from '$lib/components/education/ReviewResultCard.svelte';
	import SourceHighlightedText from '$lib/components/education/SourceHighlightedText.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { getMyAssignmentSubmissions } from '$lib/apis/education';

	const i18n = getContext('i18n');

	export let show = false;
	export let assignmentId: string;

	type SubmissionRound = {
		submission_id: string;
		round_no: number;
		is_current: number;
		submitted_at: number;
		content: {
			content_json: Record<string, unknown> | null;
			content_text: string;
		};
		review: {
			review_status: string;
			score?: number | null;
			rubric?: Record<string, number> | null;
			overall_comment?: string | null;
			returned_comment?: string | null;
			resubmit_due_at?: number | null;
			reviewed_at?: number | null;
		} | null;
	};

	let loading = false;
	let error = '';
	let rounds: SubmissionRound[] = [];
	let activeRoundNo: number | null = null;

	$: activeRound = rounds.find((round) => round.round_no === activeRoundNo) ?? null;

	const load = async () => {
		loading = true;
		error = '';
		rounds = [];
		activeRoundNo = null;

		try {
			const res = await getMyAssignmentSubmissions(localStorage.token, assignmentId);
			rounds = ((res?.rounds ?? []) as SubmissionRound[])
				.slice()
				.sort((a, b) => a.round_no - b.round_no);
			const current = rounds.find((round) => round.is_current) ?? rounds[rounds.length - 1];
			activeRoundNo = current ? current.round_no : null;
		} catch (err: any) {
			error = err?.detail ?? $i18n.t('Failed to load submission history.');
		} finally {
			loading = false;
		}
	};

	$: if (show && assignmentId) {
		load();
	}
</script>

<Modal bind:show size="lg">
	<div class="flex max-h-[85vh] flex-col">
		<div
			class="flex shrink-0 items-center justify-between border-b border-gray-100 px-5 py-4 dark:border-gray-850"
		>
			<div class="text-lg font-semibold text-gray-950 dark:text-gray-100">
				{$i18n.t('Submission History')}
			</div>
			<button
				class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
				on:click={() => (show = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<div class="flex-1 overflow-y-auto px-5 py-4">
			{#if loading}
				<div class="flex justify-center py-10">
					<Spinner className="size-6" />
				</div>
			{:else if error}
				<div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
					{error}
				</div>
			{:else if rounds.length === 0}
				<div class="py-10 text-center text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('No submissions yet.')}
				</div>
			{:else}
				{#if rounds.length > 1}
					<div class="mb-3 flex flex-wrap items-center gap-1.5">
						{#each rounds as round (round.submission_id)}
							<button
								class="rounded-lg border px-2.5 py-1 text-sm {round.round_no === activeRoundNo
									? 'border-transparent bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
									: 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'}"
								on:click={() => (activeRoundNo = round.round_no)}
							>
								{$i18n.t('Round {{round}}', { round: round.round_no })}
								{#if !round.is_current}<span class="opacity-60"> · {$i18n.t('History')}</span>{/if}
							</button>
						{/each}
					</div>
				{/if}

				{#if activeRound}
					<ReviewResultCard
						review={{
							round_no: activeRound.round_no,
							submitted_at: activeRound.submitted_at,
							review_status: activeRound.review?.review_status ?? 'pending',
							score: activeRound.review?.score ?? null,
							overall_comment: activeRound.review?.overall_comment ?? null,
							rubric: activeRound.review?.rubric ?? null,
							returned_comment: activeRound.review?.returned_comment ?? null,
							resubmit_due_at: activeRound.review?.resubmit_due_at ?? null,
							reviewed_at: activeRound.review?.reviewed_at ?? null
						}}
					/>

					<div class="rounded-2xl bg-stone-50 p-4 dark:bg-gray-900">
						<div
							class="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400"
						>
							{$i18n.t('Content Snapshot')}
						</div>
						<SourceHighlightedText
							json={activeRound.content.content_json}
							text={activeRound.content.content_text}
							segments={[]}
						/>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</Modal>
