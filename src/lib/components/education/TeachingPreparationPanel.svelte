<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import {
		teachingApi,
		preparationAssignment,
		type AiCandidate,
		type Preparation
	} from '$lib/apis/education/teaching';
	import type { AssignmentDraft } from '$lib/utils/assignment-form';
	import type { TeachingConfig } from '$lib/apis/education';
	import { toLocalDateTimeInput } from '$lib/utils/education';
	import { EDU_FIELD_CLASS } from './styles';
	const i18n = getContext('i18n');
	export let draft: AssignmentDraft;
	export let selectedClassroomIds = new Set<string>();
	export let template: TeachingConfig;
	export let assignment: {
		id: string;
		classroom_id: string | null;
		config_revision: number;
	} | null = null;
	let ai: AiCandidate = {
		web_search: false,
		prompt: template.prompt,
		model_id: '',
		thinking: 'model_default',
		template_version: template.version
	};
	let preparation: Preparation | null = null;
	let models: {
		id: string;
		name: string;
		capabilities: { reasoning?: boolean };
		thinking_support: Record<string, unknown>;
	}[] = [];
	let versions: {
		id: string;
		revision: number;
		config: { ai: AiCandidate };
		change_summary: string;
	}[] = [];
	let busy = false;
	let loading = true;
	let searchAvailable = false;
	let initializationFailed = false;
	$: unavailable = busy || loading || initializationFailed;
	let status = '';
	let error = '';
	let changeSummary = '';
	let confirmed = false;
	let publishKey = crypto.randomUUID();
	let current = '';
	let savedAiInput = '';
	let priorTrials: { id: string; created_at: number; model_id: string }[] = [];
	const sourceTrialId = $page.url.searchParams.get('source_trial');
	const sourceSequence = $page.url.searchParams.get('source_sequence');
	$: selected = models.find((m) => m.id === ai.model_id);
	$: if (selected && !selected.capabilities.reasoning) ai.thinking = 'model_default';
	$: if (selected?.thinking_support.can_turn_off === false && ai.thinking === 'off')
		ai.thinking = 'model_default';
	$: if (selected?.thinking_support.graded === false && ['low', 'high'].includes(ai.thinking))
		ai.thinking = 'medium';
	$: fingerprintInput = JSON.stringify([draft, [...selectedClassroomIds], ai]);
	$: dirty = current !== fingerprintInput;
	$: aiDirty = savedAiInput !== JSON.stringify([draft.title, draft.description, ai]);
	const fail = (e: unknown) => {
		error = String(
			(e as { detail?: string; message?: string }).detail ?? (e as Error).message ?? e
		);
		status = '保存失败';
	};
	onMount(async () => {
		try {
			const options = await teachingApi<{
				search_available?: boolean;
				models: typeof models;
				recommended_thinking: AiCandidate['thinking'];
				policy: { recommended_model_id: string | null };
			}>('/teacher/teaching-models');
			models = options.models;
			searchAvailable = options.search_available === true;
			ai.model_id =
				options.policy.recommended_model_id ?? (models.length === 1 ? models[0].id : '');
			ai.thinking = options.recommended_thinking;
			if (assignment) {
				versions = await teachingApi(`/assignments/${assignment.id}/ai-revisions`);
				if (versions[0]) ai = structuredClone(versions[0].config.ai);
				priorTrials = await teachingApi(`/assignments/${assignment.id}/teaching-trials`);
			}
			const duplicateId = $page.url.searchParams.get('from');
			if (!assignment && duplicateId) {
				const copied = await teachingApi<typeof versions>(
					`/assignments/${duplicateId}/ai-revisions`
				);
				if (copied[0]) ai = structuredClone(copied[0].config.ai);
			}
			const id = $page.url.searchParams.get('preparation');
			if (id) {
				const restored = await teachingApi<Preparation>(`/teacher/teaching-preparations/${id}`);
				if (restored.assignment_id !== (assignment?.id ?? null))
					throw new Error('Preparation does not belong to this assignment');
				preparation = restored;
				ai = structuredClone(preparation.payload.ai);
			}
			current = JSON.stringify([draft, [...selectedClassroomIds], ai]);
			savedAiInput = JSON.stringify([draft.title, draft.description, ai]);
		} catch (e) {
			initializationFailed = true;
			fail(e);
		} finally {
			loading = false;
		}
	});
	async function save() {
		error = '';
		status = '保存中';
		const payload = {
			assignment: preparationAssignment(
				draft,
				assignment ? [assignment.classroom_id!] : [...selectedClassroomIds]
			),
			ai
		};
		preparation =
			preparation && !preparation.published
				? await teachingApi<Preparation>(
						`/teacher/teaching-preparations/${preparation.id}`,
						'PUT',
						{ expected_revision: preparation.revision, payload }
					)
				: await teachingApi<Preparation>('/teacher/teaching-preparations', 'POST', {
						assignment_id: assignment?.id ?? null,
						payload
					});
		current = JSON.stringify([draft, [...selectedClassroomIds], ai]);
		savedAiInput = JSON.stringify([draft.title, draft.description, ai]);
		confirmed = false;
		publishKey = crypto.randomUUID();
		await goto(
			`${$page.url.pathname}?preparation=${preparation.id}${sourceTrialId ? `&source_trial=${sourceTrialId}&source_sequence=${sourceSequence}` : ''}`,
			{ replaceState: true, noScroll: true }
		);
		preparation = await teachingApi<Preparation>(
			`/teacher/teaching-preparations/${preparation.id}`
		);
		status = '已保存';
		return preparation;
	}
	async function continueTrial(trialId: string) {
		const saved = await save();
		await goto(`/teacher/teaching-trials/${trialId}?preparation=${saved.id}`);
	}
	async function run(operation: () => Promise<unknown>) {
		if (unavailable) return;
		busy = true;
		error = '';
		try {
			await operation();
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}
	async function trial() {
		const saved = await save();
		const result = await teachingApi<{ id: string }>('/teacher/teaching-trials', 'POST', {
			preparation_id: saved.id,
			expected_revision: saved.revision,
			...(sourceTrialId
				? { source_trial_id: sourceTrialId, source_sequence: Number(sourceSequence) }
				: {})
		});
		await goto(`/teacher/teaching-trials/${result.id}`);
	}
	async function restoreVersion(revisionId: string) {
		const saved = await save();
		preparation = await teachingApi<Preparation>(
			`/teacher/teaching-preparations/${saved.id}/adopt-revision`,
			'POST',
			{ expected_revision: saved.revision, revision_id: revisionId }
		);
		ai = structuredClone(preparation.payload.ai);
		current = JSON.stringify([draft, [...selectedClassroomIds], ai]);
		preparation = await teachingApi<Preparation>(`/teacher/teaching-preparations/${saved.id}`);
		savedAiInput = JSON.stringify([draft.title, draft.description, ai]);
	}
	async function publish() {
		if (!preparation || dirty) throw new Error('请先保存准备稿并核对发布内容。');
		const result = await teachingApi<{ id: string }[]>(
			`/teacher/teaching-preparations/${preparation.id}/publish`,
			'POST',
			{
				expected_revision: preparation.revision,
				expected_config_revision: assignment?.config_revision ?? null,
				idempotency_key: publishKey,
				change_summary: changeSummary
			}
		);
		await goto(
			result.length === 1 ? `/teacher/assignments/${result[0].id}` : '/teacher/assignments'
		);
	}
</script>

<section
	id="assignment-teaching"
	class="my-6 min-w-0 scroll-mt-4 space-y-4 rounded-xl border border-gray-200 p-5 dark:border-gray-700"
>
	<h2 class="font-semibold">{$i18n.t('AI 辅导设置')}</h2>
	{#if assignment}<p class="text-sm text-gray-500">
			{$i18n.t('本区域只调整 AI 辅导；题目、评分、反思和截止请先在上方保存作业设置。')}
		</p>
		<a class="text-sm underline" href={$page.url.pathname} data-sveltekit-reload
			>{$i18n.t('从当前作业重新准备')}</a
		>{/if}
	{#if assignment}<p>
			{$i18n.t('正在使用')}：{versions[0]
				? `v${versions[0].revision} · ${versions[0].config.ai.model_id}`
				: $i18n.t('尚未发布辅导版本')}
		</p>{/if}
	<p class="text-sm text-gray-500">
		{$i18n.t('准备稿、试教和采用方案不会改变学生正在使用的配置。')}
	</p>
	{#if sourceTrialId}<p class="text-sm text-amber-700">
			{$i18n.t('本次试教将保留所选节点的稿件和已完成对话，并使用下面的新方案。')}
		</p>{/if}
	<label class="block"
		>{$i18n.t('你希望 AI 怎样辅导学生')}<textarea
			class="mt-2 min-h-64 w-full {EDU_FIELD_CLASS}"
			bind:value={ai.prompt}
			disabled={unavailable}
		></textarea></label
	>
	<details class="text-sm">
		<summary>{$i18n.t('编写提示')}</summary>
		<p>
			{$i18n.t('写明辅导目标、判断依据、表达方式和示例。这里的完整原文就是本次作业的辅导提示词。')}
		</p>
	</details>
	<button
		type="button"
		class="text-sm underline"
		disabled={unavailable}
		on:click={() => {
			if (window.confirm(`${$i18n.t('将替换为以下推荐提示词，是否继续？')}\n\n${template.prompt}`))
				ai = { ...ai, prompt: template.prompt, template_version: template.version };
		}}>{$i18n.t('恢复推荐版本')}</button
	>
	<label class="block"
		>{$i18n.t('本次作业的辅导模型')}<select
			class="mt-2 w-full {EDU_FIELD_CLASS}"
			bind:value={ai.model_id}
			disabled={unavailable}
			><option value="">{$i18n.t('请选择模型')}</option>{#each models as model}<option
					value={model.id}>{model.name}</option
				>{/each}</select
		></label
	>
	<p class="text-sm text-gray-500">{$i18n.t('用于初次阅读、交流和修改复看。学生不能逐轮更换。')}</p>
	<label class="flex items-center gap-2">
		<input
			type="checkbox"
			checked={ai.web_search === true}
			on:change={(event) => {
				ai.web_search = event.currentTarget.checked;
			}}
			disabled={unavailable || (!searchAvailable && !ai.web_search)}
		/>
		{$i18n.t('允许按需搜索资料')}
	</label>
	<p class="text-sm text-gray-500">
		{$i18n.t('独立于辅导提示词。关闭后不再搜索，历史对话中的资料仍保留。保存并发布后生效。')}
	</p>
	{#if !searchAvailable}<p class="text-sm text-amber-700">
			{$i18n.t('管理员尚未开启资料搜索，当前可关闭已有设置。')}
		</p>{/if}
	{#if !models.length}<p role="alert">
			{$i18n.t('管理员尚未开放教学模型，请先配置教学模型清单。')}
		</p>{/if}
	<details>
		<summary>{$i18n.t('思考设置')}</summary><select
			class={EDU_FIELD_CLASS}
			bind:value={ai.thinking}
			disabled={unavailable || !selected?.capabilities.reasoning}
		>
			<option value="model_default">{$i18n.t('模型默认')}</option>
			{#if selected?.capabilities.reasoning}{#each ['off', 'low', 'medium', 'high'].filter((level) => (level !== 'off' || selected.thinking_support.can_turn_off !== false) && (selected.thinking_support.graded !== false || ['off', 'medium'].includes(level))) as level}<option
						value={level}
						>{$i18n.t(
							selected.thinking_support.graded === false && level === 'medium' ? '开启' : level
						)}</option
					>{/each}{/if}
		</select>
	</details>
	{#if versions.length}<details>
			<summary>{$i18n.t('历史辅导版本')}</summary>{#each versions as version}<div class="my-2">
					v{version.revision} · {version.config.ai.model_id} · {version.change_summary}
					· {$i18n.t(version.config.ai.web_search ? '资料搜索开启' : '资料搜索关闭')}
					<button
						class="underline"
						type="button"
						disabled={unavailable}
						on:click={() => run(() => restoreVersion(version.id))}
						>{$i18n.t('以此版本准备新方案')}</button
					>
					<details>
						<summary>{$i18n.t('查看辅导方式')}</summary>
						<pre class="whitespace-pre-wrap">{version.config.ai.prompt}</pre>
					</details>
				</div>{/each}
		</details>{/if}
	<div class="flex flex-wrap gap-3">
		<button class="rounded-lg border px-4 py-2" disabled={unavailable} on:click={() => run(save)}
			>{$i18n.t('保存准备稿')}</button
		><button class="rounded-lg border px-4 py-2" disabled={unavailable} on:click={() => run(trial)}
			>{$i18n.t('用样稿试教')}</button
		><span role="status">{$i18n.t(loading ? 'Loading...' : dirty ? '有未保存修改' : status)}</span>
	</div>
	{#if preparation?.trials?.length}<details>
			<summary>{$i18n.t('试教记录')}</summary>{#each preparation.trials as trial}<a
					class="block underline"
					href={`/teacher/teaching-trials/${trial.id}`}
					>{new Date(trial.created_at * 1000).toLocaleString()}</a
				>{/each}
		</details>{/if}
	<p>
		{$i18n.t('本配置已试教')}：{!aiDirty && preparation?.coverage?.stages.length
			? preparation.coverage.stages.map((s) => $i18n.t(s)).join('、')
			: $i18n.t('尚未试教或配置已变化')}
	</p>
	{#if priorTrials.length}<details>
			<summary>{$i18n.t('从既有试教继续测试新方案')}</summary>{#each priorTrials as trial}<button
					type="button"
					class="my-2 block text-sm underline"
					disabled={unavailable}
					on:click={() => run(() => continueTrial(trial.id))}
					>{new Date(trial.created_at * 1000).toLocaleString()} · {trial.model_id}</button
				>{/each}
		</details>{/if}
	{#if assignment}<label class="block"
			>{$i18n.t('调整说明')}<textarea class="w-full {EDU_FIELD_CLASS}" bind:value={changeSummary}
			></textarea></label
		>{/if}
	{#if preparation && !preparation.published}<div class="space-y-3 border-t pt-4">
			<p>
				{assignment ? preparation.payload.assignment.title : draft.title} · {ai.model_id} · {$i18n.t(
					ai.thinking
				)} · {$i18n.t('班级')}：{assignment ? 1 : selectedClassroomIds.size} · {(assignment &&
				preparation.payload.assignment.due_at
					? toLocalDateTimeInput(preparation.payload.assignment.due_at)
					: draft.dueAt) || $i18n.t('尚未设置截止时间')}
			</p>
			<label class="flex gap-2"
				><input type="checkbox" bind:checked={confirmed} disabled={unavailable || dirty} />{$i18n.t(
					'已核对当前配置及试教覆盖情况，按当前配置发布。'
				)}</label
			><button
				class="rounded-lg bg-gray-900 px-4 py-2 text-white dark:bg-white dark:text-gray-900"
				disabled={unavailable || dirty || !confirmed}
				on:click={() => run(publish)}>{$i18n.t(assignment ? '应用新版本' : '正式布置')}</button
			>
		</div>{/if}
	{#if error}<p role="alert" class="text-red-600">{$i18n.t(error)}</p>{/if}
</section>
