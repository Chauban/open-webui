<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import {
		getModelHealth,
		getModelFailures,
		type HealthPeriod,
		type ModelHealth,
		type ModelFailure
	} from '$lib/apis/analytics/model-health';
	import { models } from '$lib/stores';
	const i18n = getContext('i18n');
	let period: HealthPeriod = '24h';
	let entries: ModelHealth[] = [];
	let loading = true;
	let error = false;
	let selected: string | null = null;
	let failures: ModelFailure[] = [];
	let detailLoading = false;
	let detailError = false;
	let total = 0;
	let offset = 0;
	let version = 0;
	let detailVersion = 0;
	const name = (id: string) => $models.find((model) => model.id === id)?.name || id;
	const rate = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(1)}%`);
	const date = (value: number | null) => (value ? new Date(value * 1000).toLocaleString() : '—');
	const seconds = (value: number | null) =>
		value === null ? '—' : `${(value / 1000).toFixed(1)} s`;
	const reason = (value: string) =>
		$i18n.t(
			{
				timeout: 'Request timed out',
				connection: 'Connection failed',
				rate_limit: 'Rate limited',
				authentication: 'Authentication failed',
				provider: 'Provider error',
				interrupted: 'Stream interrupted',
				request: 'Request rejected',
				invalid_response: 'Invalid response'
			}[value] || 'Unknown error'
		);
	const outcome = (value: string) =>
		$i18n.t(
			{ success: 'Succeeded after retry', failed: 'Final failure', cancelled: 'Cancelled' }[
				value
			] || 'Unknown'
		);

	async function load() {
		const current = ++version;
		++detailVersion;
		loading = true;
		error = false;
		selected = null;
		try {
			const result = await getModelHealth(localStorage.token, period);
			if (current === version) entries = result.models;
		} catch {
			if (current === version) error = true;
		} finally {
			if (current === version) loading = false;
		}
	}
	async function details(id: string, pageOffset = 0) {
		const current = ++detailVersion;
		selected = id;
		offset = pageOffset;
		detailLoading = true;
		detailError = false;
		failures = [];
		try {
			const result = await getModelFailures(localStorage.token, period, id, offset);
			if (current === detailVersion) {
				failures = result.items;
				total = result.total;
			}
		} catch {
			if (current === detailVersion) detailError = true;
		} finally {
			if (current === detailVersion) detailLoading = false;
		}
	}
	onMount(load);
</script>

<section class="health" aria-label={$i18n.t('Model health')}>
	<header>
		<div>
			<h2>{$i18n.t('Model health')}</h2>
			<p>
				{$i18n.t(
					'Completed server model calls. Retries and fallback attempts are counted separately.'
				)}
			</p>
		</div>
		<div class="controls">
			<select aria-label={$i18n.t('Health time range')} bind:value={period} on:change={load}>
				<option value="1h">{$i18n.t('Last hour')}</option><option value="24h"
					>{$i18n.t('Last 24 hours')}</option
				><option value="7d">{$i18n.t('Last 7 days')}</option>
			</select>
			<button on:click={load} disabled={loading}>{$i18n.t('Refresh')}</button>
		</div>
	</header>
	<p class="note">
		{$i18n.t(
			'Cancelled calls are excluded from failure rates. Records are kept for 30 days, starting when monitoring is enabled.'
		)}
	</p>
	{#if loading}<p role="status">{$i18n.t('Loading...')}</p>
	{:else if error}<p role="alert">
			{$i18n.t('Could not load model health. Please refresh to retry.')}
		</p>
	{:else if entries.length === 0}<p class="empty">
			{$i18n.t(
				'No completed model calls in this period. New calls will appear here after they finish.'
			)}
		</p>
	{:else}
		<div class="table-scroll">
			<table>
				<thead
					><tr
						>{#each ['Model', 'Calls', 'Final failures', 'Failure rate', 'Failed attempts', 'Attempt failure rate', 'Average successful duration', 'Affected users', 'Fallback successes / calls', 'Cancelled', 'Last failure'] as title}<th
								>{$i18n.t(title)}</th
							>{/each}</tr
					></thead
				>
				<tbody
					>{#each entries as entry (entry.model_id)}
						<tr class:has-failure={entry.failures > 0}>
							<td
								><button
									class="model"
									on:click={() => details(entry.model_id)}
									aria-expanded={selected === entry.model_id}>{name(entry.model_id)}</button
								></td
							>
							<td>{entry.calls}</td><td>{entry.failures}</td><td>{rate(entry.failure_rate)}</td>
							<td>{entry.attempt_failures} / {entry.attempts}</td><td
								>{rate(entry.attempt_failure_rate)}</td
							>
							<td>{seconds(entry.average_duration_ms)}</td><td>{entry.affected_users}</td><td
								>{entry.fallback_successes} / {entry.fallback_calls}</td
							><td>{entry.cancelled}</td><td>{date(entry.last_failure_at)}</td>
						</tr>
					{/each}</tbody
				>
			</table>
		</div>
		{#if selected}
			{@const entry = entries.find((item) => item.model_id === selected)}
			<div class="detail">
				<header>
					<h3>{name(selected)} · {$i18n.t('Failure details')}</h3>
					<a href="/?settings=admin%3Amodels">{$i18n.t('Model settings')}</a>
				</header>
				{#if entry}
					<div class="reasons">
						{#each Object.entries(entry.reasons) as [key, count]}<span>{reason(key)} {count}</span
							>{/each}
					</div>
					<div class="table-scroll">
						<table>
							<thead
								><tr
									><th>{$i18n.t('Actual model')}</th><th>{$i18n.t('Connection route')}</th><th
										>{$i18n.t('Failed attempts')}</th
									><th>{$i18n.t('Last failure')}</th></tr
								></thead
							><tbody>
								{#each entry.routes as route}<tr
										><td>{route.model_id}</td><td>{route.route}</td><td
											>{route.failures} / {route.attempts}</td
										><td>{date(route.last_failure_at)}</td></tr
									>{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if detailLoading}<p role="status">{$i18n.t('Loading...')}</p>
				{:else if detailError}<p role="alert">
						{$i18n.t('Could not load failure details.')}
						<button on:click={() => details(selected, offset)}>{$i18n.t('Retry')}</button>
					</p>
				{:else if failures.length === 0}<p>{$i18n.t('No failed attempts in this period.')}</p>
				{:else}
					<div class="table-scroll">
						<table>
							<thead
								><tr
									>{#each ['Time', 'Actual model', 'Connection route', 'Failure reason', 'HTTP status', 'Duration', 'Fallback', 'Final outcome'] as title}<th
											>{$i18n.t(title)}</th
										>{/each}</tr
								></thead
							><tbody>
								{#each failures as failure (failure.id)}<tr
										><td>{date(failure.started_at)}</td><td>{failure.model_id}</td><td
											>{failure.route}</td
										><td>{reason(failure.reason)}</td><td>{failure.http_status ?? '—'}</td><td
											>{seconds(failure.duration_ms)}</td
										><td>{$i18n.t(failure.fallback ? 'Yes' : 'No')}</td><td
											>{outcome(failure.final_outcome)}</td
										></tr
									>{/each}
							</tbody>
						</table>
					</div>
					<div class="controls pagination">
						<button disabled={offset === 0} on:click={() => details(selected, offset - 25)}
							>{$i18n.t('Previous')}</button
						><span>{offset + 1}–{Math.min(offset + 25, total)} / {total}</span><button
							disabled={offset + 25 >= total}
							on:click={() => details(selected, offset + 25)}>{$i18n.t('Next')}</button
						>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</section>

<style>
	.health {
		color: inherit;
		font-family: 'Noto Sans SC', 'Source Han Sans SC', system-ui, sans-serif;
		padding: 1rem 0;
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}
	h2 {
		font-family: 'Noto Serif SC', 'Source Han Serif SC', serif;
		font-size: 1.15rem;
		font-weight: 600;
	}
	h3 {
		font-weight: 600;
	}
	p {
		font-size: 0.85rem;
		line-height: 1.6;
		margin: 0.6rem 0;
	}
	.note {
		opacity: 0.7;
	}
	.controls {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.6rem;
		font-size: 0.85rem;
	}
	button,
	select {
		min-height: 40px;
		border-radius: 8px;
		padding: 0.4rem 0.7rem;
		background: transparent;
		border: 1px solid #64708466;
	}
	button:disabled {
		opacity: 0.4;
		cursor: default;
	}
	button:focus-visible,
	select:focus-visible,
	a:focus-visible {
		outline: 2px solid #ff6a45;
		outline-offset: 3px;
	}
	.model {
		text-align: left;
		border: 0;
		padding-left: 0;
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	.table-scroll {
		overflow-x: auto;
		margin-top: 0.8rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8rem;
		text-align: left;
	}
	th,
	td {
		padding: 0.65rem 0.75rem;
		border-bottom: 1px solid #64708433;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}
	th {
		font-weight: 500;
		opacity: 0.8;
	}
	.has-failure td:nth-child(3) {
		color: #b53f3f;
		font-weight: 700;
	}
	:global(.dark) .has-failure td:nth-child(3) {
		color: #ffb199;
	}
	.detail {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 2px solid #20406a66;
	}
	.reasons {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-top: 0.8rem;
		font-size: 0.85rem;
	}
	.pagination {
		justify-content: flex-end;
		margin-top: 0.8rem;
	}
	a {
		text-decoration: underline;
		font-size: 0.85rem;
	}
	.empty {
		padding: 2rem 0;
	}
</style>
