/** Render clearly delimited pipe tables even when a model omits the GFM separator.
 * Only the display string changes; stored responses and fenced examples stay intact.
 */
export function normalizeMarkdownTables(content: string): string {
	const lines = content.split('\n');
	const result: string[] = [];
	let fence: { char: string; length: number } | null = null;
	const cells = (line: string): string[] | null => {
		if (/^(?: {4}|\t)/.test(line)) return null;
		const text = line.trim();
		if (!text.startsWith('|') || !text.endsWith('|') || text.endsWith('\\|')) return null;
		// Protect escaped pipes and inline code before identifying column boundaries.
		const row = text.replace(/`+[^`]*`+/g, (code) => code.replaceAll('|', '\u0000'));
		const parts = row
			.slice(1, -1)
			.split(/(?<!\\)\|/)
			.map((cell) => cell.trim());
		return parts.length >= 2 && parts.every(Boolean) ? parts : null;
	};
	for (let i = 0; i < lines.length; i++) {
		const marker = lines[i].match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
		if (marker) {
			if (!fence) fence = { char: marker[1][0], length: marker[1].length };
			else if (marker[1][0] === fence.char && marker[1].length >= fence.length && !marker[2].trim())
				fence = null;
			result.push(lines[i]);
			continue;
		}
		const header = fence ? null : cells(lines[i]);
		if (!header) {
			result.push(lines[i]);
			continue;
		}
		let end = i + 1;
		while (end < lines.length && cells(lines[end])?.length === header.length) end++;
		const separator = cells(lines[i + 1] ?? '')?.every((cell) => /^:?-+:?$/.test(cell));
		if (end - i >= 3 && !separator) {
			if (result.length && result.at(-1)?.trim()) result.push('');
			result.push(
				lines[i],
				`| ${header.map(() => '---').join(' | ')} |`,
				...lines.slice(i + 1, end)
			);
		} else result.push(...lines.slice(i, end));
		i = end - 1;
	}
	return result.join('\n');
}
