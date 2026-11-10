import { describe, expect, it } from 'vitest';
import { getInstanceName } from './instance-name';

describe('instance names', () => {
	it.each(['localhost', '127.0.0.1', '[::1]', '::1'])('labels the local address %s', (hostname) =>
		expect(getInstanceName('RightWrite', hostname)).toBe('本地 · RightWrite')
	);

	it.each([
		['hitsz.rightwrite.cc', 'HIT · RightWrite'],
		['HITSZ.RIGHTWRITE.CC.', 'HIT · RightWrite'],
		['rightwrite.cc', 'Rightwrite'],
		['www.rightwrite.cc', 'Rightwrite'],
		['another.example', 'RightWrite'],
		['hitsz.rightwrite.cc.example', 'RightWrite'],
		['', 'RightWrite']
	])('resolves %s without mislabelling other sites', (hostname, expected) => {
		expect(getInstanceName('RightWrite', hostname)).toBe(expected);
	});

	it('preserves the configured application name', () => {
		expect(getInstanceName('Writing Lab', 'localhost')).toBe('本地 · Writing Lab');
	});
});
