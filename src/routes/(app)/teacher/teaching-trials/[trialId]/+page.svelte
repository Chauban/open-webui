<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import {
		teachingApi,
		trialAction,
		type Trial,
		type Preparation,
		type AiCandidate
	} from '$lib/apis/education/teaching';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import TeacherPageShell from '$lib/components/education/TeacherPageShell.svelte';
	import { EDU_FIELD_CLASS } from '$lib/components/education/styles';
	import { teachingTrialStatus } from '$lib/utils/teaching-trial-status';
	const i18n = getContext('i18n');
	type Input = {
		comparison_mode: 'models' | 'prompts';
		title: string;
		description: string;
		candidates: AiCandidate[];
		sample: string;
	};
	type Work = { id: string; revision: number; payload: Input };
	type Group = { id: string; payload: Input; trials: Trial[] };
	type Plan = { id: string; name: string; trial_id: string; config: Trial['config'] };
	type Model = {
		id: string;
		name: string;
		capabilities: Record<string, boolean>;
		thinking_support: Record<string, boolean>;
	};
	type Lane = {
		trial: Trial;
		busy: boolean;
		partial: string;
		error: string;
		controller?: AbortController;
		pending?: { expected_sequence: number; idempotency_key: string; action: string; text: string };
	};
	let work: Work | null = null;
	let input: Input = {
		comparison_mode: 'models',
		title: '',
		description: '',
		candidates: [],
		sample: ''
	};
	let preparation: Preparation | null = null;
	let models: Model[] = [];
	let searchAvailable = false;
	let groups: Group[] = [];
	let lanes: Lane[] = [];
	let plans: Plan[] = [];
	let current: Group | null = null;
	let active = 0;
	let message = '';
	let error = '';
	let saving = false;
	let saved = false;
	let adopting: Plan | null = null;
	let includeTask = true;
	let adoptKey: string | null = null;
	let source: { source_trial_id: string; source_sequence: number } | null = null;
	let runKey: string | null = null;
	let names: Record<string, string> = {};
	let collapsed: Record<string, boolean> = {};
	let recipient = 'all';
	let saveTarget: Lane | null = null;
	let showSave = false;
	let retaining = false;
	let notice = '';
	let editorOpen = true;
	let showAdopt = false;
	let retainedPlan: Plan | null = null;
	let saveError = '';
	$: unsaved = !!work && JSON.stringify(input) !== JSON.stringify(work.payload);
	$: sampleChanged = sendTargets.some((lane) => lane.trial.state.draft !== input.sample);
	$: sendHint = dirty
		? '设置已修改，请先重新测试，或恢复本轮设置后继续交流。'
		: targetBusy
			? '所选模型正在生成，请等待完成或停止生成。'
			: !sendTargets.length
				? '请先开始测试，再扮演学生继续交流。'
				: sampleChanged
					? '下次发送会先保存修改后的样稿，再交给所选模型。'
					: '';
	function beginAdopt(plan: Plan) {
		adopting = plan;
		adoptKey = null;
		includeTask = !preparation?.assignment_id;
		showAdopt = true;
		error = '';
	}

	$: expanded = lanes.filter((l) => !collapsed[l.trial.id]);
	$: sendTargets = lanes.filter(
		(l) =>
			(recipient === 'all' || recipient === l.trial.id) &&
			l.trial.state.baseline !== null &&
			l.trial.state.status !== 'finished'
	);
	$: targetBusy = sendTargets.some((l) => l.busy || l.trial.state.running_event_id);
	function fold(lane: Lane) {
		collapsed = { ...collapsed, [lane.trial.id]: true };
		if (lanes[active]?.trial.id === lane.trial.id)
			active = lanes.findIndex((l) => !collapsed[l.trial.id]);
	}
	function unfold(lane: Lane) {
		collapsed = { ...collapsed, [lane.trial.id]: false };
		active = lanes.indexOf(lane);
	}
	function beginSave(lane: Lane) {
		saveTarget = lane;
		names[lane.trial.id] ??= `${lane.trial.config.title} · ${laneName(lane)}`;
		saveError = '';
		showSave = true;
	}

	const explain = (e: unknown) =>
		e instanceof Error
			? e.message
			: typeof e === 'object' && e !== null && 'detail' in e
				? String(e.detail)
				: String(e);
	$: returnUrl = preparation?.assignment_id
		? `/teacher/assignments/${preparation.assignment_id}/settings?preparation=${preparation.id}`
		: `/teacher/assignments/new?preparation=${preparation?.id}`;
	$: busy = lanes.some((l) => l.busy || l.trial.state.running_event_id);
	$: dirty =
		!!current &&
		JSON.stringify({ ...input, sample: '' }) !== JSON.stringify({ ...current.payload, sample: '' });
	const touch = () => {
		lanes = [...lanes];
	};
	const modelName = (id: string) => models.find((m) => m.id === id)?.name ?? id;
	function chooseGroup(group: Group) {
		current = group;
		recipient = 'all';
		collapsed = {};
		active = 0;
		lanes = group.trials.map((trial) => ({ trial, busy: false, partial: '', error: '' }));
	}
	async function refreshLane(lane: Lane) {
		lane.trial = await teachingApi<Trial>(`/teacher/teaching-trials/${lane.trial.id}`);
		// The history selector must not restore the empty snapshot captured at creation.
		groups = groups.map((group) => ({
			...group,
			trials: group.trials.map((trial) => (trial.id === lane.trial.id ? lane.trial : trial))
		}));
		if (current) current = groups.find((group) => group.id === current!.id) ?? current;
		touch();
	}
	onMount(() => {
		let disposed = false;
		let timer: ReturnType<typeof setTimeout>;
		async function poll() {
			if (disposed) return;
			await Promise.all(
				lanes
					.filter((l) => !l.busy && l.trial.state.running_event_id)
					.map((l) =>
						refreshLane(l).catch((e) => {
							l.error = explain(e);
							touch();
						})
					)
			);
			if (!disposed) timer = setTimeout(poll, 2000);
		}
		(async () => {
			try {
				const seed = await teachingApi<Trial>(`/teacher/teaching-trials/${$page.params.trialId}`);
				preparation = await teachingApi<Preparation>(
					`/teacher/teaching-preparations/${$page.url.searchParams.get('preparation') ?? seed.preparation_id}`
				);
				const options = await teachingApi<{ models: Model[]; search_available?: boolean }>(
					'/teacher/teaching-models'
				);
				models = options.models;
				searchAvailable = options.search_available === true;
				work = await teachingApi<Work>('/teacher/teaching-workbenches', 'POST', {
					trial_id: seed.id,
					preparation_id: preparation.id
				});
				input = structuredClone(work.payload);
				groups = await teachingApi<Group[]>(`/teacher/teaching-workbenches/${work.id}/comparisons`);
				plans = await teachingApi<Plan[]>('/teacher/saved-teaching-plans');
				if (groups.length) chooseGroup(groups[0]);
				else
					chooseGroup({
						id: seed.id,
						payload: {
							comparison_mode: 'models',
							title: seed.config.title,
							description: seed.config.description,
							candidates: [seed.config.ai],
							sample: seed.state.draft
						},
						trials: [seed]
					});
				poll();
			} catch (e) {
				error = explain(e);
			}
		})();
		return () => {
			disposed = true;
			clearTimeout(timer);
		};
	});
	function toggle(model: Model) {
		const old = input.candidates.find((c) => c.model_id === model.id);
		if (old) {
			if (input.candidates.length > 1) input.candidates = input.candidates.filter((c) => c !== old);
		} else if (input.candidates.length < 3)
			input.candidates = [
				...input.candidates,
				{ ...input.candidates[0], model_id: model.id, thinking: 'model_default' }
			];
		input = { ...input };
		saved = false;
	}
	function changeMode(mode: Input['comparison_mode']) {
		if (mode === input.comparison_mode) return;
		if (!confirm($i18n.t('切换比较方式将以方案 A 为基础重新准备，是否继续？'))) return;
		const first = structuredClone(input.candidates[0]);
		input = {
			...input,
			comparison_mode: mode,
			candidates: mode === 'prompts' ? [first, structuredClone(first)] : [first]
		};
		saved = false;
	}
	function sharedSettings(settings: Partial<AiCandidate>) {
		input = { ...input, candidates: input.candidates.map((c) => ({ ...c, ...settings })) };
		saved = false;
	}
	function laneName(lane: Lane) {
		const prefix =
			current?.payload.comparison_mode === 'prompts'
				? `${$i18n.t('方案')} ${String.fromCharCode(65 + lanes.indexOf(lane))} · `
				: '';
		return prefix + modelName(lane.trial.config.ai.model_id);
	}
	function updatePrompt(value: string) {
		input.candidates = input.candidates.map((c) => ({ ...c, prompt: value }));
		input = { ...input };
		saved = false;
	}
	async function save() {
		if (!work) return;
		work = await teachingApi<Work>(`/teacher/teaching-workbenches/${work.id}`, 'PUT', {
			expected_revision: work.revision,
			payload: input
		});
		saved = true;
	}
	async function saveOnly() {
		saving = true;
		error = '';
		try {
			await save();
		} catch (e) {
			error = explain(e);
		} finally {
			saving = false;
		}
	}
	async function act(lane: Lane, action: string, text = '', retry = false) {
		if (lane.busy) return;
		lane.busy = true;
		lane.error = '';
		lane.partial = '';
		touch();
		try {
			if (!retry && action === 'coaching_chat' && input.sample !== lane.trial.state.draft) {
				await trialAction(
					lane.trial.id,
					{
						expected_sequence: lane.trial.sequence,
						idempotency_key: crypto.randomUUID(),
						action: 'save',
						text: input.sample
					},
					() => {}
				);
				await refreshLane(lane);
			}
			if (!retry)
				lane.pending = {
					expected_sequence: lane.trial.sequence,
					idempotency_key: crypto.randomUUID(),
					action,
					text
				};
			lane.controller = new AbortController();
			await trialAction(
				lane.trial.id,
				lane.pending,
				(delta) => {
					lane.partial += delta;
					touch();
				},
				lane.controller.signal
			);
			await refreshLane(lane);
			lane.pending = undefined;
			lane.partial = '';
			if (lane.trial.events.at(-1)?.call?.status === 'failed')
				lane.error = '生成失败，输入和测试记录已保留。';
		} catch (e) {
			lane.error = explain(e);
			await refreshLane(lane).catch(() => {});
		} finally {
			lane.busy = false;
			touch();
		}
	}
	async function run() {
		if (!work || busy || saving) return;
		saving = true;
		error = '';
		try {
			if (!runKey) {
				await save();
				runKey = crypto.randomUUID();
			}
			const group = await teachingApi<Group>(
				`/teacher/teaching-workbenches/${work.id}/comparisons`,
				'POST',
				{ expected_revision: work.revision, idempotency_key: runKey, ...source }
			);
			runKey = null;
			source = null;
			input.sample = group.trials[0].state.draft;
			groups = [group, ...groups.filter((g) => g.id !== group.id)];
			chooseGroup(group);
			if (lanes[0].trial.state.baseline === null)
				await Promise.all(lanes.map((l) => act(l, 'confirm', group.payload.sample)));
		} catch (e) {
			error = explain(e);
		} finally {
			saving = false;
		}
	}
	async function stop(lane: Lane) {
		try {
			await refreshLane(lane);
			await trialAction(
				lane.trial.id,
				{
					expected_sequence: lane.trial.sequence,
					idempotency_key: crypto.randomUUID(),
					action: 'stop'
				},
				() => {}
			);
			lane.controller?.abort();
			await refreshLane(lane);
		} catch (e) {
			lane.error = explain(e);
			touch();
		}
	}
	async function retain(lane: Lane) {
		retaining = true;
		try {
			const plan = await teachingApi<Plan>('/teacher/saved-teaching-plans', 'POST', {
				trial_id: lane.trial.id,
				name: names[lane.trial.id]?.trim() || `${lane.trial.config.title} · ${laneName(lane)}`
			});
			plans = [plan, ...plans.filter((p) => p.id !== plan.id)];
			retainedPlan = plan;
			showSave = false;
			notice = '方案已保存，可在下方「已保存方案」中使用。';
		} catch (e) {
			saveError = explain(e);
		} finally {
			retaining = false;
		}
	}
	function loadPlan(plan: Plan) {
		if (
			work &&
			JSON.stringify(input) !== JSON.stringify(work.payload) &&
			!confirm($i18n.t('替换尚未保存的试教输入？'))
		)
			return;
		input = {
			...input,
			comparison_mode: 'models',
			title: plan.config.title,
			description: plan.config.description,
			candidates: [structuredClone(plan.config.ai)]
		};
		saved = false;
	}
	async function adopt() {
		if (!adopting || !preparation) return;
		saving = true;
		adoptKey ??= crypto.randomUUID();
		try {
			await teachingApi(
				`/teacher/saved-teaching-plans/${adopting.id}/adopt/${preparation.id}`,
				'POST',
				{
					expected_revision: preparation.revision,
					include_task: includeTask,
					idempotency_key: adoptKey
				}
			);
			await goto(returnUrl);
		} catch (e) {
			error = explain(e);
		} finally {
			saving = false;
		}
	}
	async function send() {
		if (targetBusy || saving || dirty || !message.trim() || !sendTargets.length) return;
		const targets = [...sendTargets];
		const text = message;
		saving = true;
		try {
			await save();
		} catch (e) {
			error = explain(e);
			return;
		} finally {
			saving = false;
		}
		await Promise.all(targets.map((l) => act(l, 'coaching_chat', text)));
		if (targets.every((l) => !l.error) && message === text) message = '';
	}
</script>

<TeacherPageShell width="full" title={$i18n.t('教师试教，学生不可见')}>
	<div class="mx-auto w-full min-w-0 max-w-screen-2xl space-y-8 p-4 trial-workbench">
		{#if work && preparation}
			<nav class="flex flex-wrap items-center gap-4">
				<a class="underline" href={returnUrl}>{$i18n.t('返回作业准备')}</a><a
					class="underline"
					href="#saved-plans">{$i18n.t('已保存方案')}</a
				>
				<button
					aria-expanded={editorOpen}
					aria-controls="trial-editor"
					on:click={() => (editorOpen = !editorOpen)}
					>{$i18n.t(editorOpen ? '收起编辑区' : '展开编辑区')}</button
				>
			</nav>
			<div class="trial-layout" class:editor-open={editorOpen}>
				<section
					id="trial-editor"
					hidden={!editorOpen}
					class="trial-settings grid min-w-0 gap-5 rounded-xl border p-5"
				>
					<h2 class="font-semibold">{$i18n.t('AI 辅导设置')}</h2>
					<details class="trial-task">
						<summary>{$i18n.t('作业题目与要求')}</summary>
						<label
							>{$i18n.t('作业题目')}<input
								class="w-full {EDU_FIELD_CLASS}"
								bind:value={input.title}
							/></label
						>
						<label
							>{$i18n.t('作业要求')}<textarea
								class="min-h-24 w-full {EDU_FIELD_CLASS}"
								bind:value={input.description}
							></textarea></label
						>
					</details>
					<label
						>{$i18n.t('比较方式')}<select
							class={EDU_FIELD_CLASS}
							value={input.comparison_mode}
							disabled={busy || saving}
							on:change={(e) => {
								changeMode(e.currentTarget.value as Input['comparison_mode']);
								e.currentTarget.value = input.comparison_mode;
							}}
							><option value="models">{$i18n.t('比较模型')}</option><option value="prompts"
								>{$i18n.t('比较提示词 A／B')}</option
							></select
						></label
					>
					{#if input.comparison_mode === 'prompts'}
						<p class="text-sm text-gray-500">
							{$i18n.t('两版提示词共用模型、思考、搜索、样稿及对话起点。')}
						</p>
						{#each input.candidates as candidate, index}<label
								>{$i18n.t('辅导提示词')}
								{String.fromCharCode(65 + index)}<textarea
									class="min-h-48 w-full {EDU_FIELD_CLASS}"
									bind:value={candidate.prompt}
								></textarea></label
							>{/each}
						<label
							>{$i18n.t('共用模型')}<select
								class={EDU_FIELD_CLASS}
								value={input.candidates[0].model_id}
								on:change={(e) =>
									sharedSettings({ model_id: e.currentTarget.value, thinking: 'model_default' })}
								>{#each models as model}<option value={model.id}>{model.name}</option
									>{/each}</select
							></label
						>
					{:else}
						<label
							>{$i18n.t('辅导提示词')}<textarea
								class="min-h-48 w-full {EDU_FIELD_CLASS}"
								value={input.candidates[0]?.prompt ?? ''}
								on:input={(e) => updatePrompt(e.currentTarget.value)}
							></textarea></label
						>
						<fieldset>
							<legend>{$i18n.t('参与对比的模型（1—3 个）')}</legend>
							<div class="flex flex-wrap gap-4">
								{#each models as model}<label
										><input
											type="checkbox"
											checked={input.candidates.some((c) => c.model_id === model.id)}
											disabled={input.candidates.length === 3 &&
												!input.candidates.some((c) => c.model_id === model.id)}
											on:change={() => toggle(model)}
										/>
										{model.name}</label
									>{/each}
							</div>
						</fieldset>
					{/if}
					{#each input.comparison_mode === 'prompts' ? input.candidates.slice(0, 1) : input.candidates as candidate}
						{@const model = models.find((m) => m.id === candidate.model_id)}
						<label
							>{modelName(candidate.model_id)} · {$i18n.t('思考设置')}
							<select
								class="max-w-full {EDU_FIELD_CLASS}"
								value={candidate.thinking}
								on:change={(e) => {
									if (input.comparison_mode === 'prompts')
										sharedSettings({ thinking: e.currentTarget.value as AiCandidate['thinking'] });
									else {
										candidate.thinking = e.currentTarget.value as AiCandidate['thinking'];
										input = { ...input };
									}
								}}
							>
								<option value="model_default">{$i18n.t('模型默认')}</option>
								{#if model?.capabilities.reasoning}{#each ['off', 'low', 'medium', 'high'].filter((level) => (level !== 'off' || model.thinking_support.can_turn_off !== false) && (model.thinking_support.graded !== false || ['off', 'medium'].includes(level))) as level}<option
											value={level}>{$i18n.t(level)}</option
										>{/each}{/if}
							</select></label
						>
						<label class="flex items-center gap-2">
							<input
								type="checkbox"
								checked={candidate.web_search === true}
								on:change={(event) => {
									if (input.comparison_mode === 'prompts')
										sharedSettings({ web_search: event.currentTarget.checked });
									else {
										candidate.web_search = event.currentTarget.checked;
										input = { ...input };
									}
								}}
								disabled={busy || (!searchAvailable && !candidate.web_search)}
							/>
							{modelName(candidate.model_id)} · {$i18n.t('允许按需搜索资料')}
						</label>
					{/each}
					<p class="text-sm text-gray-500">
						{$i18n.t('搜索开关独立于提示词。修改后请重新测试，旧结果保留原设置。')}
					</p>
					{#if !searchAvailable}<p class="text-sm text-amber-700">
							{$i18n.t('管理员尚未开启资料搜索，当前可关闭已有设置。')}
						</p>{/if}
					<label
						>{$i18n.t('试教样稿')}<textarea
							class="min-h-40 w-full {EDU_FIELD_CLASS}"
							bind:value={input.sample}
						></textarea></label
					>
					<div class="flex flex-wrap gap-4">
						<button disabled={saving} on:click={saveOnly}>{$i18n.t('保存试教工作稿')}</button
						><button class="trial-primary" disabled={saving || busy} on:click={run}
							>{$i18n.t(
								source
									? '从所选节点比较新方案'
									: lanes.some((l) => l.trial.state.baseline !== null)
										? '重新测试'
										: '开始测试'
							)}</button
						>{#if unsaved}<span class="text-sm text-amber-700">{$i18n.t('有未保存修改')}</span
							>{:else if saved}<span role="status">{$i18n.t('已保存')}</span>{/if}
					</div>

					{#if source}<p>
							{$i18n.t('新一轮将从所选节点的稿件和历史开始。')}
							<button on:click={() => (source = null)}>{$i18n.t('取消')}</button>
						</p>{/if}
				</section>
				<div class="trial-results min-w-0 space-y-5">
					<div class="trial-result-toolbar">
						<h2 class="text-lg font-semibold">{$i18n.t('试教反馈')}</h2>
						{#if groups.length}<label class="trial-history"
								><span>{$i18n.t('查看试教结果')}</span><select
									disabled={busy}
									class="max-w-full {EDU_FIELD_CLASS}"
									value={current?.id}
									on:change={(e) => {
										const group = groups.find((g) => g.id === e.currentTarget.value);
										if (group) chooseGroup(group);
									}}
									>{#each groups as group, index}<option value={group.id}
											>{$i18n.t('测试')}
											{groups.length - index} · {group.payload.title} · {group.payload.candidates
												.map(
													(c, i) =>
														`${group.payload.comparison_mode === 'prompts' ? String.fromCharCode(65 + i) + ': ' : ''}${modelName(c.model_id)}`
												)
												.join(' / ')}</option
										>{/each}</select
								></label
							>{/if}
					</div>
					{#if dirty && current}<div class="trial-change-note">
							<span>{$i18n.t('下方是修改前的反馈。重新测试后才会使用上方的新设置。')}</span>
							<button class="trial-primary" disabled={busy || saving} on:click={run}
								>{$i18n.t('用新设置测试')}</button
							>
							<details class="w-full">
								<summary>{$i18n.t('查看本轮设置与当前修改')}</summary>
								<div class="grid gap-4 md:grid-cols-2">
									<div>
										<h3>{$i18n.t('本轮使用')}</h3>
										<p>{current.payload.title}</p>
										<p class="whitespace-pre-wrap">{current.payload.description}</p>
										<p class="whitespace-pre-wrap">
											{current.payload.candidates
												.map((c, i) => `${String.fromCharCode(65 + i)}: ${c.prompt}`)
												.join('\n\n')}
										</p>
										{#each current.payload.candidates as candidate}<p>
												{modelName(candidate.model_id)} · {$i18n.t(candidate.thinking)} · {$i18n.t(
													candidate.web_search ? '资料搜索开启' : '资料搜索关闭'
												)}
											</p>{/each}
									</div>
									<div>
										<h3>{$i18n.t('当前编辑')}</h3>
										<p>{input.title}</p>
										<p class="whitespace-pre-wrap">{input.description}</p>
										<p class="whitespace-pre-wrap">
											{input.candidates
												.map((c, i) => `${String.fromCharCode(65 + i)}: ${c.prompt}`)
												.join('\n\n')}
										</p>
										{#each input.candidates as candidate}<p>
												{modelName(candidate.model_id)} · {$i18n.t(candidate.thinking)} · {$i18n.t(
													candidate.web_search ? '资料搜索开启' : '资料搜索关闭'
												)}
											</p>{/each}
									</div>
								</div>
							</details>
							<button
								disabled={busy}
								on:click={() => {
									if (confirm($i18n.t('载入本组设置将替换当前编辑内容，继续？'))) {
										input = structuredClone(current!.payload);
										input.sample = lanes[0].trial.state.draft;
									}
								}}>{$i18n.t('恢复这次测试的设置')}</button
							>
						</div>{/if}
					{#if lanes.some((l) => collapsed[l.trial.id])}<div
							class="trial-folded"
							aria-label={$i18n.t('已收起的模型')}
						>
							{#each lanes.filter((l) => collapsed[l.trial.id]) as lane}<button
									aria-expanded="false"
									aria-label={`${$i18n.t('展开')} ${laneName(lane)}`}
									on:click={() => unfold(lane)}
									>{$i18n.t('展开')}
									{laneName(lane)}{#if lane.busy || lane.trial.state.running_event_id}<span
											class="text-xs"
										>
											· {$i18n.t('正在生成…')}</span
										>{:else if teachingTrialStatus(lane.trial).status === 'failed'}<span
											class="text-xs text-red-600"
										>
											· {$i18n.t('生成失败')}</span
										>{:else if teachingTrialStatus(lane.trial).status === 'stopped'}<span
											class="text-xs"
										>
											· {$i18n.t('已停止')}</span
										>{/if}</button
								>{/each}
						</div>{/if}
					<div class="flex flex-wrap gap-3 lg:hidden">
						{#each expanded as lane}<button
								class:font-bold={lanes.indexOf(lane) === active}
								on:click={() => (active = lanes.indexOf(lane))}>{laneName(lane)}</button
							>{/each}
					</div>
					<div
						class="grid min-w-0 items-start gap-6 {expanded.length === 3
							? 'lg:grid-cols-3'
							: expanded.length === 2
								? 'lg:grid-cols-2'
								: 'grid-cols-1'}"
					>
						{#each expanded as lane (lane.trial.id)}
							{@const outcome = teachingTrialStatus(lane.trial)}
							<section
								class="trial-model min-w-0 rounded-xl border {lanes.indexOf(lane) === active
									? ''
									: 'hidden lg:block'}"
								aria-label={laneName(lane)}
							>
								<header class="trial-model-header">
									<div class="min-w-0">
										<h3 class="break-words text-base font-semibold">
											{laneName(lane)}
										</h3>
										<p class="mt-1 text-xs text-gray-500">
											{$i18n.t(lane.trial.config.ai.thinking)} · {$i18n.t(
												lane.trial.config.ai.web_search ? '资料搜索开启' : '资料搜索关闭'
											)}
										</p>
										<p class="mt-2 text-xs" class:text-red-600={outcome.status === 'failed'}>
											{$i18n.t(lane.busy ? '正在生成…' : outcome.label)}
										</p>
									</div>
									<button
										class="trial-quiet"
										aria-label={`${$i18n.t('收起')} ${laneName(lane)}`}
										aria-expanded="true"
										on:click={() => fold(lane)}>{$i18n.t('收起')}</button
									>
								</header>
								<div class="trial-dialogue">
									{#each lane.trial.state.dialogue as entry, n}<article
											class="trial-message {entry.role === 'user' ? 'trial-message-user' : ''}"
										>
											<p class="mb-3 text-xs text-gray-500">
												{$i18n.t(entry.role === 'user' ? '模拟学生' : 'AI 反馈')}
											</p>
											<Markdown id={`${lane.trial.id}-${n}`} content={entry.content} />
											{#if entry.role === 'assistant'}{@const node = lane.trial.events.find(
													(e) => !e.state.running_event_id && e.state.dialogue.length === n + 1
												)}{#if node}<details class="trial-more">
														<summary>{$i18n.t('继续测试新设置')}</summary><button
															disabled={busy}
															on:click={() =>
																(source = {
																	source_trial_id: lane.trial.id,
																	source_sequence: node.sequence
																})}>{$i18n.t('从这条反馈继续')}</button
														>
													</details>{/if}{/if}
										</article>{/each}
									{#if lane.partial}<article class="trial-message">
											<Markdown
												id={`${lane.trial.id}-stream`}
												content={lane.partial}
												done={false}
											/>
										</article>{/if}
									{#if lane.busy || lane.trial.state.running_event_id}<div class="trial-running">
											<p role="status">{$i18n.t('正在生成…')}</p>
											<button on:click={() => stop(lane)}>{$i18n.t('停止生成')}</button>
										</div>{:else if outcome.status === 'failed'}<p
											role="alert"
											class="p-5 text-sm text-red-600"
										>
											{$i18n.t(outcome.message)}
										</p>{:else if outcome.status === 'stopped'}<p
											role="status"
											class="p-5 text-sm text-gray-600"
										>
											{$i18n.t(outcome.message)}
										</p>{:else if outcome.status === 'idle' && !lane.trial.state.dialogue.length && !lane.error}<p
											class="p-6 text-sm text-gray-500"
										>
											{$i18n.t('点击上方「开始测试」，查看这个模型的反馈。')}
										</p>{/if}
									{#if lane.error && !lane.busy && !['failed', 'stopped'].includes(outcome.status)}<p
											role="alert"
											class="px-5 text-sm text-red-600"
										>
											{$i18n.t(lane.error)}
										</p>{/if}
									{#if !lane.busy && lane.trial.events.at(-1)?.call?.status === 'failed'}<div
											class="p-5"
										>
											<button on:click={() => act(lane, 'retry')}>{$i18n.t('重试')}</button>
										</div>{:else if lane.pending && !lane.busy}<div class="p-5">
											<button
												on:click={() => act(lane, lane.pending!.action, lane.pending!.text, true)}
												>{$i18n.t('重试')}</button
											>
										</div>{/if}
								</div>
								<footer class="trial-model-footer">
									<span class="text-xs text-gray-500">{$i18n.t('保存这个模型与提示词的组合')}</span
									><button
										disabled={!lane.trial.events.some((e) => e.call?.status === 'ready') ||
											plans.some((p) => p.trial_id === lane.trial.id)}
										on:click={() => beginSave(lane)}
										>{$i18n.t(
											plans.some((p) => p.trial_id === lane.trial.id) ? '已保存方案' : '保存方案'
										)}</button
									>
								</footer>
							</section>
						{/each}
					</div>
					<section class="trial-composer rounded-xl border p-5">
						<div class="flex flex-wrap gap-2 mb-3">
							{#each ['我不同意你的判断，能解释一下依据吗？', '请直接帮我重写这一段。', '我暂时不想继续改了，谢谢。'] as question}<button
									class="trial-quiet"
									on:click={() => (message = question)}>{$i18n.t(question)}</button
								>{/each}
						</div>
						<label class="grid gap-3"
							><span class="font-medium">{$i18n.t('继续提问')}</span><textarea
								aria-label={$i18n.t('扮演学生交流')}
								class="min-h-24 w-full {EDU_FIELD_CLASS}"
								bind:value={message}
								placeholder={$i18n.t('输入学生可能会问的问题，测试 AI 怎样回应。')}
							></textarea></label
						>
						<div class="trial-composer-actions">
							<label class="trial-recipient"
								><span>{$i18n.t('发送给')}</span><select
									class={EDU_FIELD_CLASS}
									bind:value={recipient}
									><option value="all"
										>{$i18n.t(
											current?.payload.comparison_mode === 'prompts' ? '全部方案' : '全部模型'
										)} ({lanes.length})</option
									>{#each lanes as lane}<option value={lane.trial.id}>{laneName(lane)}</option
										>{/each}</select
								></label
							><button
								class="trial-primary"
								disabled={targetBusy || saving || dirty || !message.trim() || !sendTargets.length}
								aria-describedby="trial-send-hint"
								on:click={send}>{$i18n.t('发送')}</button
							>
						</div>
						<p
							id="trial-send-hint"
							class="mt-3 text-sm text-gray-600 dark:text-gray-300"
							aria-live="polite"
						>
							{$i18n.t(sendHint)}
						</p>
					</section>
				</div>
			</div>
			{#if notice}<div class="flex flex-wrap items-center gap-3">
					<p role="status" class="text-sm text-green-700">{$i18n.t(notice)}</p>
					{#if retainedPlan}<button
							disabled={!!preparation.published}
							on:click={() => beginAdopt(retainedPlan!)}>{$i18n.t('带回作业设置')}</button
						>{/if}
				</div>{/if}

			<section id="saved-plans" class="space-y-3 rounded-xl border p-4">
				<h2 class="text-lg font-semibold">{$i18n.t('已保存方案')}</h2>
				<p class="text-sm text-gray-500">
					{$i18n.t(
						'保存的组合可以再次测试；点击「用于作业」带回作业设置，正式发布前不会影响学生。'
					)}
				</p>
				{#each plans as plan}<details>
						<summary>{plan.name} · {modelName(plan.config.ai.model_id)}</summary>
						<h3>{plan.config.title}</h3>
						<p class="whitespace-pre-wrap">{plan.config.description}</p>
						<p class="whitespace-pre-wrap">{plan.config.ai.prompt}</p>
						<p>{$i18n.t(plan.config.ai.web_search ? '资料搜索开启' : '资料搜索关闭')}</p>
						<div class="flex gap-4">
							<button on:click={() => loadPlan(plan)}>{$i18n.t('加载继续试教')}</button><button
								disabled={!!preparation.published}
								on:click={() => beginAdopt(plan)}>{$i18n.t('用于作业')}</button
							>
						</div>
					</details>{/each}
			</section>
			{#if adopting}<Modal bind:show={showAdopt} size="lg"
					><section class="trial-save-dialog space-y-3 p-6">
						<h2>{$i18n.t('将方案用于作业')}</h2>
						<div class="grid gap-4 md:grid-cols-2">
							<div>
								<h3>{$i18n.t('当前准备稿')}</h3>
								<p>{preparation.payload.assignment.title}</p>
								<p class="whitespace-pre-wrap">{preparation.payload.assignment.description}</p>
								<p>
									{modelName(preparation.payload.ai.model_id)} · {$i18n.t(
										preparation.payload.ai.thinking
									)}
								</p>
								<p class="whitespace-pre-wrap">{preparation.payload.ai.prompt}</p>
								<p>
									{$i18n.t(preparation.payload.ai.web_search ? '资料搜索开启' : '资料搜索关闭')}
								</p>
							</div>
							<div>
								<h3>{adopting.name}</h3>
								<p>{adopting.config.title}</p>
								<p class="whitespace-pre-wrap">{adopting.config.description}</p>
								<p>
									{modelName(adopting.config.ai.model_id)} · {$i18n.t(adopting.config.ai.thinking)}
								</p>
								<p class="whitespace-pre-wrap">{adopting.config.ai.prompt}</p>
								<p>{$i18n.t(adopting.config.ai.web_search ? '资料搜索开启' : '资料搜索关闭')}</p>
							</div>
						</div>
						{#if !preparation.assignment_id}<label
								><input type="checkbox" bind:checked={includeTask} />{$i18n.t(
									'同时采用题目与要求'
								)}</label
							>{:else}<p>
								{$i18n.t('仅采用 AI 配置；题目要求请在作业设置修改，任务不一致时需重新试教。')}
							</p>{/if}
						<div class="flex gap-4">
							<button disabled={saving} on:click={adopt}>{$i18n.t('带回作业设置')}</button><button
								on:click={() => (showAdopt = false)}>{$i18n.t('取消')}</button
							>
						</div>
						{#if error}<p role="alert" class="text-red-600">{$i18n.t(error)}</p>{/if}
					</section></Modal
				>{/if}
		{:else}<p role="status">{$i18n.t('加载中…')}</p>{/if}
		{#if error && !showAdopt}<p role="alert" class="text-red-600">{$i18n.t(error)}</p>{/if}
	</div>
</TeacherPageShell>

<Modal bind:show={showSave} size="sm">
	<div class="trial-save-dialog p-6">
		<h2 class="text-lg font-semibold">{$i18n.t('保存方案')}</h2>
		{#if saveTarget}<p class="my-3 text-sm text-gray-500">
				{laneName(saveTarget)} — {$i18n.t('保存这次反馈实际使用的提示词和模型。')}
			</p>
			{#if dirty}<p class="mb-3 text-sm text-amber-700">
					{$i18n.t('当前修改尚未测试，保存的是这次反馈实际使用的配置。')}
				</p>{/if}
			{#if saveError}<p role="alert" class="text-red-600">{$i18n.t(saveError)}</p>{/if}
			<label class="grid gap-2"
				>{$i18n.t('方案名称')}<input
					class={EDU_FIELD_CLASS}
					bind:value={names[saveTarget.trial.id]}
				/></label
			>
			<div class="mt-6 flex justify-end gap-3">
				<button disabled={retaining} on:click={() => (showSave = false)}>{$i18n.t('取消')}</button
				><button
					class="trial-primary"
					disabled={retaining || !names[saveTarget.trial.id]?.trim()}
					on:click={() => retain(saveTarget!)}>{$i18n.t('保存')}</button
				>
			</div>{/if}
	</div>
</Modal>

<style>
	.trial-layout {
		display: grid;
		gap: 24px;
		align-items: start;
	}
	.trial-settings[hidden] {
		display: none;
	}
	.trial-task {
		min-width: 0;
	}
	.trial-task label {
		display: grid;
		gap: 8px;
		margin-top: 12px;
	}
	.trial-task summary,
	.trial-change-note summary {
		cursor: pointer;
	}
	@media (min-width: 1280px) {
		.trial-layout.editor-open {
			grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
		}
	}

	.trial-workbench button,
	.trial-save-dialog button {
		min-height: 40px;
		padding: 8px 16px;
		border: 1px solid #d1d5db;
		border-radius: 10px;
		font-size: 14px;
		line-height: 1.5;
		background: white;
		color: #374151;
	}
	.trial-workbench button:hover:not(:disabled),
	.trial-save-dialog button:hover:not(:disabled) {
		background: #f3f4f6;
	}
	.trial-workbench button:focus-visible,
	.trial-save-dialog button:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 3px;
	}
	.trial-workbench button:disabled,
	.trial-save-dialog button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.trial-workbench .trial-primary,
	.trial-save-dialog .trial-primary {
		background: #2563eb;
		color: white;
		border-color: #2563eb;
	}
	.trial-workbench .trial-primary:hover:not(:disabled),
	.trial-save-dialog .trial-primary:hover:not(:disabled) {
		background: #1d4ed8;
	}
	.trial-settings > label {
		display: grid;
		gap: 10px;
	}
	.trial-result-toolbar,
	.trial-model-header,
	.trial-model-footer,
	.trial-running,
	.trial-composer-actions,
	.trial-folded,
	.trial-change-note {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 16px;
	}
	.trial-history {
		display: grid;
		gap: 8px;
		min-width: 0;
		max-width: 100%;
		font-size: 14px;
	}
	.trial-history select {
		width: 100%;
		max-width: 620px;
	}
	.trial-model {
		overflow: hidden;
		background: white;
	}
	.trial-model-header {
		padding: 20px 24px;
		border-bottom: 1px solid #e5e7eb;
		flex-wrap: nowrap;
		align-items: flex-start;
	}
	.trial-workbench .trial-quiet {
		flex-shrink: 0;
		border-color: transparent;
		background: transparent;
	}
	.trial-dialogue {
		max-height: 70vh;
		overflow: auto;
		min-height: 160px;
	}
	.trial-message {
		padding: 24px;
		font-size: 15px;
		line-height: 1.8;
		overflow-wrap: anywhere;
	}
	.trial-message + .trial-message {
		border-top: 1px solid #e5e7eb;
	}
	.trial-message-user {
		background: #f8fafc;
	}
	.trial-message :global(table) {
		min-width: 460px;
	}
	.trial-message :global(th),
	.trial-message :global(td) {
		padding: 12px;
		vertical-align: top;
	}
	.trial-more {
		margin-top: 20px;
		font-size: 12px;
		color: #6b7280;
	}
	.trial-more summary {
		cursor: pointer;
	}
	.trial-more button {
		margin-top: 10px;
	}
	.trial-running {
		padding: 24px;
		font-size: 14px;
	}
	.trial-model-footer {
		padding: 16px 24px;
		border-top: 1px solid #e5e7eb;
		background: #f8fafc;
	}
	.trial-composer-actions {
		margin-top: 16px;
	}
	.trial-recipient {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 12px;
		min-width: 0;
		font-size: 14px;
	}
	.trial-recipient select {
		max-width: 100%;
	}
	.trial-folded {
		justify-content: flex-start;
	}
	.trial-change-note {
		padding: 16px;
		background: #fffbeb;
		font-size: 14px;
	}
	#saved-plans > details {
		border-top: 1px solid #e5e7eb;
		padding-top: 16px;
	}
	#saved-plans summary {
		cursor: pointer;
		padding: 4px 0 12px;
	}
	#saved-plans details > div {
		margin-top: 16px;
		flex-wrap: wrap;
	}
	:global(.dark) .trial-model,
	:global(.dark) .trial-workbench button,
	:global(.dark) .trial-save-dialog button {
		background: #1f2937;
		color: #f3f4f6;
		border-color: #4b5563;
	}
	:global(.dark) .trial-message-user,
	:global(.dark) .trial-model-footer {
		background: #111827;
	}
	:global(.dark) .trial-primary {
		background: #2563eb;
	}
	@media (max-width: 639px) {
		.trial-model-header,
		.trial-message,
		.trial-model-footer {
			padding: 16px;
		}
		.trial-history {
			width: 100%;
		}
	}
</style>
