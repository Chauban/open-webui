type Translate = (key: string) => string;
export const readableChatError = (error: unknown, t: Translate): string => {
	let value: unknown = error;
	for (let depth = 0; depth < 5 && value && typeof value === 'object'; depth++) {
		const item = value as Record<string, unknown>;
		value = item.detail ?? item.error ?? item.message ?? item.content;
	}
	if (typeof value !== 'string' || !value.trim())
		return t('Unable to get a reply. Please try again.');
	if (
		/<(?:!doctype|html|head|body|title|h1|center)\b/i.test(value) ||
		/\b50[234]\b|Bad Gateway|Failed to fetch|NetworkError/i.test(value)
	) {
		return t('The connection was interrupted. Please retry your message in a moment.');
	}
	return t(value);
};
