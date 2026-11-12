<script lang="ts">
	import DOMPurify from 'dompurify';
	import { createEventDispatcher, getContext, onDestroy } from 'svelte';
	import { marked } from 'marked';
	import Modal from './Modal.svelte';
	import SensitiveInput from './SensitiveInput.svelte';
	import NativeSelect from './NativeSelect.svelte';

	const i18n: any = getContext('i18n');
	const dispatch = createEventDispatcher();
	export let title = '';
	export let message = '';
	export let cancelLabel = $i18n.t('Cancel');
	export let confirmLabel = $i18n.t('Confirm');
	export let onConfirm: () => unknown | Promise<unknown> = () => {};
	export let variant: 'primary' | 'danger' = 'primary';
	export let plainText = false;
	export let input = false;
	export let inputPlaceholder = '';
	export let inputValue = '';
	export let inputType = '';
	export let inputOptions: ({ label?: string; value: string } | string)[] = [];
	export let show = false;
	let _inputValue = inputValue;
	let busy = false;
	let error = '';
	let resolveAnswer: ((answer: boolean) => void) | null = null;
	$: if (show) {
		_inputValue = inputValue;
		error = '';
	}
	$: if (!show && resolveAnswer) settle(false);

	/** Component-scoped confirmation: unmounting cancels the pending action. */
	export function ask(options: {
		title: string;
		message: string;
		confirmLabel?: string;
		variant?: 'primary' | 'danger';
	}): Promise<boolean> {
		if (show) return Promise.resolve(false);
		title = options.title;
		message = options.message;
		confirmLabel = options.confirmLabel ?? $i18n.t('Confirm');
		variant = options.variant ?? 'primary';
		plainText = true;
		show = true;
		return new Promise((resolve) => {
			resolveAnswer = resolve;
		});
	}
	function settle(answer: boolean) {
		const resolve = resolveAnswer;
		resolveAnswer = null;
		resolve?.(answer);
	}
	function cancel() {
		if (busy) return;
		settle(false);
		show = false;
		dispatch('cancel');
	}
	async function confirm() {
		if (busy) return;
		busy = true;
		error = '';
		try {
			await onConfirm();
			settle(true);
			show = false;
			dispatch('confirm', _inputValue);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : $i18n.t('Please try again.');
		} finally {
			busy = false;
		}
	}
	onDestroy(() => settle(false));
</script>

<Modal bind:show size="sm" title={title || $i18n.t('Confirm your action')} {busy} on:close={cancel}>
	<slot>
		<div class="rw-dialog-message">
			{#if plainText}
				{message}
			{:else}
				{@html DOMPurify.sanitize(
					marked.parse(
						message || $i18n.t('This action cannot be undone. Do you wish to continue?')
					) as string
				)}
			{/if}
		</div>
		{#if input}
			{#if inputType === 'password'}
				<div class="rw-dialog-input">
					<SensitiveInput
						id="event-confirm-input"
						placeholder={inputPlaceholder || $i18n.t('Enter your message')}
						bind:value={_inputValue}
						required={true}
					/>
				</div>
			{:else if inputType === 'select' && inputOptions.length}
				<NativeSelect
					className="rw-dialog-input"
					bind:value={_inputValue}
					options={inputOptions}
					placeholder={inputPlaceholder || $i18n.t('Select an option')}
					required
				/>
			{:else}
				<textarea
					bind:value={_inputValue}
					aria-label={inputPlaceholder || $i18n.t('Enter your message')}
					placeholder={inputPlaceholder || $i18n.t('Enter your message')}
					class="rw-dialog-input resize-none"
					rows="3"
					required
				/>
			{/if}
		{/if}
	</slot>
	{#if error}<p role="alert" class="rw-dialog-error">{error}</p>{/if}
	<svelte:fragment slot="footer">
		<button class="rw-dialog-button" type="button" disabled={busy} on:click={cancel}
			>{cancelLabel}</button
		>
		<button
			class="rw-dialog-button rw-dialog-button-{variant}"
			type="button"
			disabled={busy}
			on:click={confirm}
		>
			{busy ? $i18n.t('Processing...') : confirmLabel}
		</button>
	</svelte:fragment>
</Modal>
