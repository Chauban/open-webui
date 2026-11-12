import DOMPurify from 'dompurify';

export function writingAlignment(element: HTMLElement): string | null {
	const align = element.style.textAlign;
	if (['left', 'center', 'right', 'justify'].includes(align)) return align;
	if (align === 'start' || align === 'end') {
		const rtl = element.closest('[dir]')?.getAttribute('dir') === 'rtl';
		return (align === 'start') !== rtl ? 'left' : 'right';
	}
	return null;
}

export function safeWritingLink(href: string): boolean {
	try {
		return href.length <= 4096 && ['https:', 'http:', 'mailto:'].includes(new URL(href).protocol);
	} catch {
		return false;
	}
}

/** Normalize newly pasted HTML before TipTap creates document nodes. Never rewrite saved drafts. */
export function prepareWritingPaste(html: string) {
	// Windows/browser clipboards wrap the selected fragment in a complete HTML document.
	// Those wrapper newlines aren't part of the selection, especially for data-pm-slice.
	const fragment = html.match(/<!--StartFragment-->([\s\S]*?)<!--EndFragment-->/i)?.[1] ?? html;
	const document = new DOMParser().parseFromString(DOMPurify.sanitize(fragment), 'text/html');
	let simplified = false;
	for (const element of document.querySelectorAll<HTMLElement>('p,h1,h2,h3,h4,h5,h6')) {
		const alignment = writingAlignment(element);
		if (element.style.textAlign && element.style.textAlign !== alignment) {
			element.style.textAlign = alignment ?? '';
			simplified = true;
		}
	}
	for (const link of document.querySelectorAll<HTMLAnchorElement>('a[href]')) {
		if (!safeWritingLink(link.getAttribute('href')!)) {
			link.removeAttribute('href');
			simplified = true;
		}
	}
	return { html: document.body.innerHTML, simplified };
}
