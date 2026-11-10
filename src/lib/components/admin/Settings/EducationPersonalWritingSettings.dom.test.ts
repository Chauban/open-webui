// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import EducationPersonalWritingSettings from './EducationPersonalWritingSettings.svelte';
afterEach(cleanup);
const context = new Map([['i18n', readable({ t: (key: string) => key })]]);

test('independent role choices are saved together and blocked while saving', async () => {
	const onSave = vi.fn();
	const view = render(EducationPersonalWritingSettings, {
		props: { student: false, teacher: false, onSave },
		context
	});
	const student = screen.getByRole('checkbox', {
		name: 'Allow students to use personal writing'
	}) as HTMLInputElement;
	const teacher = screen.getByRole('checkbox', {
		name: 'Allow teachers to use personal writing'
	}) as HTMLInputElement;
	expect(student.checked).toBe(false);
	expect(teacher.checked).toBe(false);
	await fireEvent.click(student);
	expect(teacher.checked).toBe(false);
	expect(onSave).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
	expect(onSave).toHaveBeenCalledWith(true, false);
	await view.rerender({ disabled: true });
	expect(student.closest('fieldset')?.disabled).toBe(true);
});
