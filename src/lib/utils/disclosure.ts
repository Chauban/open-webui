import { slide } from 'svelte/transition';
import { cubicOut } from 'svelte/easing';

export const disclosureDuration = () =>
	window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : 220;

export const disclosureSlide = (node: Element) => {
	const duration = disclosureDuration();
	return duration && node.animate ? slide(node, { duration, easing: cubicOut }) : { duration: 0 };
};

/** Keep form controls mounted, and remove collapsed content from keyboard navigation. */
export function disclosure(node: HTMLElement, open: boolean) {
	let animation: Animation | undefined;
	let expanded = open;
	node.hidden = !open;
	node.inert = !open;
	node.setAttribute('aria-hidden', String(!open));

	const settle = () => {
		node.hidden = !expanded;
		node.style.removeProperty('overflow');
		animation?.cancel();
		animation = undefined;
	};

	return {
		update(next: boolean) {
			if (next === expanded) return;
			const height = node.getBoundingClientRect().height;
			animation?.cancel();
			expanded = next;
			node.hidden = false;
			node.inert = !next;
			node.setAttribute('aria-hidden', String(!next));
			const duration = disclosureDuration();
			if (!duration || !node.animate) {
				settle();
				return;
			}
			const target = next ? node.getBoundingClientRect().height : 0;
			node.style.overflow = 'hidden';
			animation = node.animate([{ height: `${height}px` }, { height: `${target}px` }], {
				duration,
				easing: 'cubic-bezier(0.22, 1, 0.36, 1)'
			});
			animation.onfinish = settle;
		},
		destroy() {
			animation?.cancel();
		}
	};
}
