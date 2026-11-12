<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { v4 as uuidv4 } from 'uuid';
	import { dialogLayer } from '$lib/utils/dialog-layer';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let show = true;
	export let size = 'md';
	export let containerClassName = '';
	export let className = '';
	export let title = '';
	export let description = '';
	export let dismissible = true;
	export let busy = false;
	export let placement: 'center' | 'bottom' = 'center';
	export let bodyClassName = '';
	export let ariaLabel = '';
	const i18n: any = getContext('i18n');
	const dispatch = createEventDispatcher();
	const id = `dialog-${uuidv4()}`;
	const widths: Record<string, string> = {
		xs: '24rem',
		sm: '30rem',
		md: '42rem',
		lg: '56rem',
		xl: '70rem',
		'2xl': '84rem',
		'3xl': '100rem',
		full: '100%'
	};
	function close() {
		if (!dismissible || busy) return;
		show = false;
		dispatch('close');
	}
</script>

{#if show}
	<div
		class="modal rw-dialog-overlay {placement === 'bottom'
			? 'rw-dialog-bottom'
			: ''} {containerClassName}"
		use:dialogLayer={{ dismissible: dismissible && !busy, onDismiss: close }}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-label={!title ? ariaLabel || $i18n?.t('Dialog') || 'Dialog' : undefined}
			aria-labelledby={title ? `${id}-title` : undefined}
			aria-describedby={description ? `${id}-description` : undefined}
			aria-busy={busy}
			tabindex="-1"
			class="modal-content rw-dialog-surface {title ? 'rw-dialog-framed' : ''} {className}"
			style:--dialog-width={widths[size] ?? widths.md}
		>
			{#if title}
				<header class="rw-dialog-header">
					<div class="min-w-0 flex-1">
						<h2 id={`${id}-title`} class="rw-dialog-title">{title}</h2>
						{#if description}<p id={`${id}-description`} class="rw-dialog-description">
								{description}
							</p>{/if}
					</div>
					{#if dismissible}
						<button
							type="button"
							class="rw-dialog-close"
							aria-label={$i18n.t('Close')}
							disabled={busy}
							on:click={close}
						>
							<XMark className="size-5" />
						</button>
					{/if}
				</header>
				<div class="rw-dialog-body {bodyClassName}"><slot /></div>
				{#if $$slots.footer}<footer class="rw-dialog-footer"><slot name="footer" /></footer>{/if}
			{:else}
				<slot />
			{/if}
		</div>
	</div>
{/if}
