import { goto } from '$app/navigation';

export const navigateTableRow = (event: MouseEvent, href: string) => {
	// Let links bubble to SvelteKit and leave controls to their own handlers.
	if (
		event.defaultPrevented ||
		event.button !== 0 ||
		event.metaKey ||
		event.ctrlKey ||
		event.shiftKey ||
		event.altKey ||
		(event.target instanceof Element &&
			event.target.closest('a, button, input, select, textarea, label, [role="button"]'))
	) {
		return;
	}

	return goto(href);
};
