<script lang="ts">
	import AssignmentChangeReason from './AssignmentChangeReason.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	let confirmation: ConfirmDialog;
	import { getContext, onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto, replaceState } from '$app/navigation';
	import { user } from '$lib/stores';
	import {
		createPreparationAutosave,
		loadDraft,
		type DraftBackup,
		type SaveState
	} from '$lib/utils/preparation-autosave';
	import {
		teachingApi,
		preparationAssignment,
		type AiCandidate,
		type Preparation
	} from '$lib/apis/education/teaching';
	import { buildAssignmentPayload, type AssignmentDraft } from '$lib/utils/assignment-form';

	import type { TeachingConfig, ThinkingControl, ThinkingSetting } from '$lib/apis/education';
	import { toLocalDateTimeInput } from '$lib/utils/education';
	import {
		getAiCandidateErrors,
		getPreparationErrors,
		preparationErrorMessages
	} from '$lib/utils/teaching-preparation-form';
	import { EDU_FIELD_CLASS } from './styles';
	const i18n = getContext('i18n');
	export let draft: AssignmentDraft;
	export let selectedClassroomIds = new Set<string>();
	export let template: TeachingConfig;
	export let initialPreparation: Preparation | null = null;
	export let initialBackup: DraftBackup | undefined = undefined;
	export let ready = false;
	export let thinkingPolicy: { control: ThinkingControl; default: ThinkingSetting } | null = null;
	let autosave: ReturnType<typeof createPreparationAutosave> | undefined;
	let saveState: SaveState = 'idle';
	let saveError = '';
	let localSafe = true;
	let disposed = false;
	let initializedMode = draft.taskMode;
	$: argument = draft.taskMode === 'revise_argument';
	export let assignment: {
		id: string;
		classroom_id: string | null;
		config_revision: number;
	} | null = null;
	const initialAssignment = preparationAssignment(
		draft,
		assignment ? [assignment.classroom_id!] : [...selectedClassroomIds]
	);
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
	let errors: string[] = [];
	let failedInput = '';
	let validationAttempted = false;
	let changeSummary = '';
	let confirmed = false;
	let confirmedInput = '';
	let publishKey = crypto.randomUUID();
	let savePayload: Preparation['payload'];
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
	$: aiDirty = savedAiInput !== JSON.stringify([draft.title, draft.description, ai]);
	$: confirmationInput = JSON.stringify([fingerprintInput, changeSummary]);
	$: if (confirmedInput !== confirmationInput) confirmed = false;
	$: preparationErrors = getPreparationErrors(draft, ai, (key, options) => $i18n.t(key, options));
	$: savePayload = {
		assignment: preparationAssignment(
			draft,
			assignment ? [assignment.classroom_id!] : [...selectedClassroomIds]
		),
		ai
	};
	$: if (autosave && !loading && !disposed) autosave.observe(savePayload);
	$: if (!loading && initializedMode !== draft.taskMode) {
		initializedMode = draft.taskMode;
		ai = { ...ai, prompt: template.prompt, template_version: template.version };
	}
	$: visibleErrors = failedInput === confirmationInput ? errors : [];
	$: publishRequirements = [
		...preparationErrors,
		...(!assignment && !draft.title.trim() ? [$i18n.t('Assignment title is required.')] : []),
		...(!assignment && !selectedClassroomIds.size
			? [$i18n.t('At least one classroom is required')]
			: []),
		...(!assignment && (!draft.dueAt || !(new Date(draft.dueAt).getTime() > 0))
			? [$i18n.t('Assignment due time is required.')]
			: []),
		...(assignment && !changeSummary.trim() ? [$i18n.t('Describe the teaching change')] : []),
		...(!confirmed ? [$i18n.t('请先勾选上方的发布确认，再继续。')] : [])
	];
	const fail = (e: unknown, failureStatus: string) => {
		failedInput = confirmationInput;
		errors = preparationErrorMessages(e, (key, options) => $i18n.t(key, options));
		status = failureStatus;
	};
	onMount(async () => {
		try {
			const options = await teachingApi<{
				search_available?: boolean;
				models: typeof models;
				recommended_thinking: AiCandidate['thinking'];
				policy: { recommended_model_id: string | null };
			}>('/teacher/teaching-models').catch(() => ({
				models: [],
				recommended_thinking: 'model_default' as const,
				policy: { recommended_model_id: null },
				search_available: false
			}));
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
			if (!assignment && duplicateId && argument && !$page.url.searchParams.has('preparation')) {
				const copied = await teachingApi<typeof versions>(
					`/assignments/${duplicateId}/ai-revisions`
				);
				if (copied[0]) ai = structuredClone(copied[0].config.ai);
			}
			let backup = initialBackup;
			preparation = initialPreparation;
			const id = $page.url.searchParams.get('preparation');
			if (id && !preparation && !backup) {
				const restored = await loadDraft($user!.id, id);
				preparation = restored.preparation;
				backup = restored.backup;
			}
			if (preparation || backup) {
				if (
					(backup?.assignmentId ?? preparation?.assignment_id ?? null) !== (assignment?.id ?? null)
				)
					throw new Error('Preparation does not belong to this assignment');
				ai = JSON.parse(JSON.stringify((backup?.payload ?? preparation!.payload).ai));
				if (preparation?.published) {
					preparation = null;
					backup = undefined;
				}
			}
			const activeModel = models.find((model) => model.id === ai.model_id);
			if (activeModel && !activeModel.capabilities.reasoning) ai.thinking = 'model_default';
			if (activeModel?.thinking_support.can_turn_off === false && ai.thinking === 'off')
				ai.thinking = 'model_default';
			if (activeModel?.thinking_support.graded === false && ['low', 'high'].includes(ai.thinking))
				ai.thinking = 'medium';
			savedAiInput = JSON.stringify([draft.title, draft.description, ai]);
			if (disposed) return;
			autosave = createPreparationAutosave({
				owner: $user!.id,
				assignmentId: assignment?.id ?? null,
				initial: { assignment: initialAssignment, ai },
				preparation,
				backup,
				onId: (id) => {
					const url = new URL($page.url);
					url.searchParams.set('preparation', id);
					replaceState(url, {});
				},
				onChange: (state, saved, error, safe) => {
					if (
						saved &&
						preparation?.coverage &&
						savedAiInput === JSON.stringify([draft.title, draft.description, ai])
					) {
						saved.coverage = preparation.coverage;
						saved.trials = preparation.trials;
					}
					saveState = state;
					localSafe = safe ?? true;
					saveError = error
						? preparationErrorMessages(error, (key, options) => $i18n.t(key, options)).join('\n')
						: '';
					preparation = saved;
				}
			});
		} catch (e) {
			initializationFailed = true;
			fail(e, '加载失败');
		} finally {
			loading = false;
			ready = !initializationFailed;
		}
	});
	onDestroy(() => {
		disposed = true;
		autosave?.destroy();
	});
	function validateTrial() {
		validationAttempted = true;
		const errors = getAiCandidateErrors(ai, (key, options) => $i18n.t(key, options));
		if (!draft.title.trim() || !draft.description.trim())
			errors.push($i18n.t('Title and assignment requirements are required for a trial'));
		if (errors.length) throw new Error(errors.join('\n'));
	}
	async function save() {
		if (!autosave) throw new Error('加载失败');
		autosave.observe({
			assignment: preparationAssignment(
				draft,
				assignment ? [assignment.classroom_id!] : [...selectedClassroomIds]
			),
			ai
		});
		const saved = await autosave.flush();
		if (!saved) throw new Error('保存失败');
		preparation = saved;
		return saved;
	}

	async function continueTrial(trialId: string) {
		validateTrial();
		const saved = await save();
		await goto(`/teacher/teaching-trials/${trialId}?preparation=${saved.id}`);
	}
	async function run(operation: () => Promise<unknown>, failureStatus = '保存失败') {
		if (unavailable) return;
		busy = true;
		errors = [];
		try {
			await operation();
		} catch (e) {
			fail(e, failureStatus);
		} finally {
			busy = false;
		}
	}
	async function trial() {
		validateTrial();
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
		preparation = await teachingApi<Preparation>(`/teacher/teaching-preparations/${saved.id}`);
		savedAiInput = JSON.stringify([draft.title, draft.description, ai]);
		autosave?.accept(preparation);
	}
	async function publish() {
		if (publishRequirements.length) throw new Error(publishRequirements.join('\n'));
		const reviewedInput = confirmationInput;
		if (!argument) {
			const result = buildAssignmentPayload(
				draft,
				(key, options) => $i18n.t(key, options),
				thinkingPolicy?.control
			);
			if (result.error) throw new Error(result.error);
		}
		const saved = await save();
		if (reviewedInput !== confirmationInput) {
			throw new Error('保存期间内容发生变化，请核对后重新确认发布。');
		}
		status = '发布中';
		const result = await teachingApi<{ id: string }[]>(
			`/teacher/teaching-preparations/${saved.id}/publish`,
			'POST',
			{
				expected_revision: saved.revision,
				expected_config_revision: assignment?.config_revision ?? null,
				idempotency_key: publishKey,
				change_summary: changeSummary
			}
		);
		autosave?.published();
		await goto(
			result.length === 1 ? `/teacher/assignments/${result[0].id}` : '/teacher/assignments'
		);
	}
</script>

<svelte:window
	on:online={() => {
		if (autosave?.pending) void autosave.flush().catch(() => {});
	}}
	on:beforeunload={(event) => {
		if (autosave?.pending && !autosave.localSafe) {
			event.preventDefault();
			event.returnValue = '';
		}
	}}
/>

<section
	id="assignment-teaching"
	class="my-6 min-w-0 scroll-mt-4 space-y-4 rounded-xl border border-gray-200 p-5 dark:border-gray-700"
>
	{#if argument}
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
				aria-invalid={validationAttempted && (!ai.prompt.trim() || ai.prompt.length > 65000)}
				aria-describedby={validationAttempted && !ai.prompt.trim()
					? 'preparation-prompt-error'
					: undefined}
			></textarea></label
		>
		{#if validationAttempted && !ai.prompt.trim()}
			<p id="preparation-prompt-error" class="text-sm text-red-600">
				{$i18n.t('请填写辅导提示词。')}
			</p>
		{/if}
		<details class="text-sm">
			<summary>{$i18n.t('编写提示')}</summary>
			<p>
				{$i18n.t(
					'写明辅导目标、判断依据、表达方式和示例。这里的完整原文就是本次作业的辅导提示词。'
				)}
			</p>
		</details>
		<button
			type="button"
			class="text-sm underline"
			disabled={unavailable}
			on:click={async () => {
				if (
					await confirmation.ask({
						title: $i18n.t('恢复推荐版本'),
						message: `${$i18n.t('将替换为以下推荐提示词，是否继续？')}\n\n${template.prompt}`,
						confirmLabel: $i18n.t('确认替换')
					})
				)
					ai = { ...ai, prompt: template.prompt, template_version: template.version };
			}}>{$i18n.t('恢复推荐版本')}</button
		>
		<label class="block"
			>{$i18n.t('本次作业的辅导模型')}<select
				class="mt-2 w-full {EDU_FIELD_CLASS}"
				bind:value={ai.model_id}
				disabled={unavailable}
				aria-invalid={validationAttempted && !ai.model_id}
				aria-describedby={validationAttempted && !ai.model_id
					? 'preparation-model-error'
					: undefined}
				><option value="">{$i18n.t('请选择模型')}</option>{#each models as model}<option
						value={model.id}>{model.name}</option
					>{/each}</select
			></label
		>
		{#if validationAttempted && !ai.model_id}
			<p id="preparation-model-error" class="text-sm text-red-600">
				{$i18n.t('请选择本次作业的辅导模型。')}
			</p>
		{/if}
		<p class="text-sm text-gray-500">
			{$i18n.t('用于初次阅读、交流和修改复看。学生不能逐轮更换。')}
		</p>
		{#if searchAvailable}
			<label class="flex items-center gap-2">
				<input
					type="checkbox"
					checked={ai.web_search === true}
					on:change={(event) => {
						ai.web_search = event.currentTarget.checked;
					}}
					disabled={unavailable}
				/>
				{$i18n.t('允许按需搜索资料')}
			</label>
		{/if}
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
			<button
				type="button"
				class="rounded-lg border px-4 py-2 disabled:cursor-not-allowed disabled:opacity-50"
				disabled={unavailable}
				on:click={() => run(trial, '试教未能开始')}>{$i18n.t('用样稿试教')}</button
			>
		</div>
		{#if visibleErrors.length && status !== '发布失败'}
			<div role="alert" class="space-y-1 whitespace-pre-line text-sm text-red-600">
				{#each visibleErrors as message}<p>{message}</p>{/each}
			</div>
		{/if}
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
		{#if assignment}
			<AssignmentChangeReason id="teaching-change-reason" bind:value={changeSummary} disabled={unavailable} />
		{/if}
	{/if}
	<div class="text-sm text-gray-500" aria-live="polite">
		<p role="status">
			{$i18n.t(
				loading
					? 'Loading...'
					: saveState === 'saving'
						? '正在自动保存…'
						: saveState === 'saved'
							? '已自动保存'
							: saveState === 'failed' || saveState === 'conflict'
								? '自动保存失败'
								: '编辑后自动保存草稿，仅自己可见。'
			)}
		</p>
		{#if !localSafe}<p class="text-amber-700">
				{$i18n.t('浏览器无法保留备份，请等待保存成功后离开。')}
			</p>{/if}
		{#if saveError}
			<p role="alert" class="whitespace-pre-line text-red-600">{saveError}</p>
			{#if localSafe}<p>{$i18n.t('当前内容已保留在此浏览器，可从作业列表继续编辑。')}</p>{/if}
			{#if saveState === 'conflict'}<button
					type="button"
					class="underline"
					on:click={() => void autosave?.copyAfterConflict().catch(() => {})}
					>{$i18n.t('保留为另一份草稿')}</button
				>{:else}<button
					type="button"
					class="underline"
					on:click={() => void autosave?.flush().catch(() => {})}>{$i18n.t('重试保存')}</button
				>{/if}
		{/if}
	</div>
	{#if !loading && !initializationFailed && !preparation?.published}<div
			class="space-y-3 border-t pt-4"
		>
			<p>
				{draft.title}{#if argument}
					· {ai.model_id} · {$i18n.t(ai.thinking)}{/if} · {$i18n.t('班级')}：{assignment
					? 1
					: selectedClassroomIds.size} · {(assignment && preparation?.payload.assignment.due_at
					? toLocalDateTimeInput(preparation?.payload.assignment.due_at)
					: draft.dueAt) || $i18n.t('尚未设置截止时间')}
			</p>
			<label class="flex gap-2"
				><input
					type="checkbox"
					checked={confirmed}
					on:change={(event) => {
						confirmed = event.currentTarget.checked;
						confirmedInput = confirmationInput;
					}}
					disabled={unavailable}
					aria-describedby={publishRequirements.length
						? 'preparation-publish-requirements'
						: undefined}
				/>{$i18n.t(
					argument
						? '已核对当前配置及试教覆盖情况，按当前配置发布。'
						: '已核对作业内容，正式布置给学生。'
				)}</label
			>
			{#if publishRequirements.length}
				<div
					id="preparation-publish-requirements"
					aria-live="polite"
					class="text-sm text-amber-700 dark:text-amber-400"
				>
					<p>{$i18n.t('发布前还需完成：')}</p>
					<ul class="mt-1 list-disc space-y-1 pl-5">
						{#each publishRequirements as requirement}<li>{requirement}</li>{/each}
					</ul>
				</div>
			{/if}
			<button
				type="button"
				class="rounded-lg bg-gray-900 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-gray-900"
				disabled={unavailable || saveState === 'conflict' || publishRequirements.length > 0}
				aria-describedby={publishRequirements.length
					? 'preparation-publish-requirements'
					: undefined}
				on:click={() => run(publish, '发布失败')}
				>{$i18n.t(
					busy && status === '发布中' ? '发布中' : assignment ? '应用新版本' : '正式布置'
				)}</button
			>
			{#if visibleErrors.length && status === '发布失败'}
				<div role="alert" class="space-y-1 whitespace-pre-line text-sm text-red-600">
					{#each visibleErrors as message}<p>{message}</p>{/each}
				</div>
			{/if}
		</div>{/if}
</section>

<ConfirmDialog bind:this={confirmation} />
