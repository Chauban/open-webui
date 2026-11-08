import { describe, expect, it } from 'vitest';
import { groupAdminModels } from './admin-model-groups';

const t = (key: string, options?: Record<string, unknown>) =>
	key.replace('{{number}}', String(options?.number));
const first = { id: 'a.gpt-4o', name: 'GPT-4o', owned_by: 'openai', urlIdx: 0 };
const second = { id: 'b.gpt-4o', name: 'GPT-4o', owned_by: 'openai', urlIdx: 1 };
const urls = ['https://a.example/v1', 'https://b.example/v1'];

describe('admin model API groups', () => {
	it('keeps identically named models from different APIs in separate groups', () => {
		const groups = groupAdminModels([first, second], [first, second], urls, t);
		expect(groups.map((group) => [group.label, group.models.map((model) => model.id)])).toEqual([
			[urls[0], ['a.gpt-4o']],
			[urls[1], ['b.gpt-4o']]
		]);
	});

	it('groups filtered models without losing their configured order or changing the input', () => {
		const third = { ...first, id: 'a.claude' };
		const models = [third, second, first];
		const groups = groupAdminModels(models, models, urls, t);
		expect(groups[0].models).toEqual([third, first]);
		expect(models).toEqual([third, second, first]);
		expect(groupAdminModels([second], models, urls, t)).toHaveLength(1);
		expect(groupAdminModels([], models, urls, t)).toEqual([]);
	});

	it('resolves custom models to the API of their base model', () => {
		const preset = { id: 'writing-coach', info: { base_model_id: second.id } };
		const groups = groupAdminModels([preset], [first, second, preset], urls, t);
		expect(groups[0].label).toBe(urls[1]);
		expect(groups[0].models).toEqual([preset]);
	});

	it('groups connections with the same address together and never displays URL credentials', () => {
		const groups = groupAdminModels(
			[first, second],
			[first, second],
			['https://user:secret@a.example/v1/?key=secret#secret', urls[0]],
			t
		);
		expect(groups).toHaveLength(1);
		expect(groups[0].label).toBe(urls[0]);
		expect(groups[0].key).not.toContain('secret');
	});

	it('keeps connections distinct when addresses are unavailable', () => {
		const groups = groupAdminModels([first, second], [first, second], [], t);
		expect(groups.map((group) => group.label)).toEqual(['API connection 1', 'API connection 2']);
		expect(groupAdminModels([first], [first], ['invalid?key=secret'], t)[0].label).toBe(
			'API connection 1'
		);
	});

	it('does not confuse Ollama or arena models with OpenAI connections', () => {
		const local = { id: 'llama', owned_by: 'ollama', urlIdx: 0 };
		const arena = { id: 'arena', owned_by: 'arena' };
		const groups = groupAdminModels([first, local, arena], [first, local, arena], urls, t);
		expect(groups.map((group) => group.label)).toEqual([urls[0], 'Ollama', 'Other models']);
	});
});
