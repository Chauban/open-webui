type SourceModel = {
	id: string;
	owned_by?: string;
	urlIdx?: number;
	base_model_id?: string | null;
	info?: { base_model_id?: string | null };
};

export type AdminModelGroup<T> = {
	key: string;
	label: string;
	models: T[];
};

// Connection URLs can contain credentials; only display the address itself.
const displayAddress = (address: string): string => {
	try {
		const url = new URL(address);
		return `${url.protocol}//${url.host}${url.pathname}`.replace(/\/+$/, '');
	} catch {
		return '';
	}
};

export function groupAdminModels<T extends SourceModel>(
	models: T[],
	catalog: SourceModel[],
	apiUrls: string[],
	t: (key: string, options?: Record<string, unknown>) => string
): AdminModelGroup<T>[] {
	const byId = new Map(catalog.map((model) => [model.id, model]));
	const groups = new Map<string, AdminModelGroup<T>>();
	for (const model of models) {
		const baseId = model.base_model_id ?? model.info?.base_model_id;
		const source = (baseId ? byId.get(baseId) : byId.get(model.id)) ?? model;
		let key = source.owned_by === 'ollama' ? 'ollama' : 'other';
		let label = key === 'ollama' ? 'Ollama' : t('Other models');
		if (source.owned_by === 'openai' && Number.isInteger(source.urlIdx)) {
			const index = source.urlIdx!;
			const address = displayAddress(apiUrls[index] ?? '');
			key = address ? `api:${address}` : `connection:${index}`;
			label = address || t('API connection {{number}}', { number: index + 1 });
		}
		if (!groups.has(key)) groups.set(key, { key, label, models: [] });
		groups.get(key)!.models.push(model);
	}
	return [...groups.values()];
}
