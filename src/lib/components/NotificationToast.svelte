<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { settings, playingNotificationSound, isLastActiveTab, WEBUI_NAME } from '$lib/stores';
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	import { createEventDispatcher, onMount } from 'svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const dispatch = createEventDispatcher();

	export let onClick: Function = () => {};
	export let title: string = 'HI';
	export let content: string;

	let startX = 0,
		startY = 0;
	let moved = false;
	let closeButtonElement: HTMLButtonElement;
	const DRAG_THRESHOLD_PX = 6;

	const clickHandler = () => {
		onClick();
		dispatch('closeToast');
	};

	const closeHandler = () => {
		dispatch('closeToast');
	};

	function onPointerDown(e: PointerEvent) {
		startX = e.clientX;
		startY = e.clientY;
		moved = false;
		// Ensure we continue to get events even if the toast moves under the pointer.
		(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
	}

	function onPointerMove(e: PointerEvent) {
		if (moved) return;
		const dx = e.clientX - startX;
		const dy = e.clientY - startY;
		if (dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
			moved = true;
		}
	}

	function onPointerUp(e: PointerEvent) {
		// Release capture if taken
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);

		// Skip if clicking the close button
		if (
			closeButtonElement &&
			(e.target === closeButtonElement || closeButtonElement.contains(e.target as Node))
		) {
			return;
		}

		// Only treat as a click if there wasn't a drag
		if (!moved) {
			clickHandler();
		}
	}

	onMount(() => {
		if (!navigator.userActivation.hasBeenActive) {
			return;
		}

		if ($settings?.notificationSound ?? true) {
			if (!$playingNotificationSound && $isLastActiveTab) {
				playingNotificationSound.set(true);

				const audio = new Audio(`/audio/notification.mp3`);
				audio.play().finally(() => {
					// Ensure the global state is reset after the sound finishes
					playingNotificationSound.set(false);
				});
			}
		}
	});
</script>

<div
	role="status"
	aria-live="polite"
	class="rw-notification-toast group relative flex gap-2.5 text-left w-full cursor-pointer select-none"
	on:dragstart|preventDefault
	on:pointerdown={onPointerDown}
	on:pointermove={onPointerMove}
	on:pointerup={onPointerUp}
	on:pointercancel={() => (moved = true)}
	on:keydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			clickHandler();
		}
	}}
>
	<!-- Keep dismissal visible for mouse, touch and keyboard users. -->
	<button
		bind:this={closeButtonElement}
		class="rw-notification-close"
		on:click|stopPropagation={closeHandler}
		aria-label="Dismiss notification"
	>
		<XMark className="size-3" />
	</button>

	<div class="shrink-0 self-top -translate-y-0.5">
		<!-- LICENSE covers this Open WebUI notification logo.
		Do not alter, remove, obscure, or replace it except as LICENSE permits:
		https://docs.openwebui.com/license. -->
		<img
			src="{WEBUI_BASE_URL}/static/logo.png"
			alt="{$WEBUI_NAME} logo"
			class="size-6 rounded-md"
		/>
	</div>

	<div>
		{#if title}
			<div class=" text-[0.8125rem] font-normal mb-0.5 line-clamp-1">{title}</div>
		{/if}

		<div class=" line-clamp-2 text-xs self-center dark:text-gray-300 font-normal">
			{@html DOMPurify.sanitize(marked(DOMPurify.sanitize(content, { ALLOWED_TAGS: [] })))}
		</div>
	</div>
</div>
