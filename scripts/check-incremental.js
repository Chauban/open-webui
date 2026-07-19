import { spawnSync } from 'node:child_process';

const focusPrefixes = [
	'src/lib/apis/education/',
	'src/lib/components/education/',
	'src/lib/utils/submission-review',
	'src/routes/(app)/teacher/',
	'src/routes/(app)/me/writing/',
	'src/routes/(app)/assignments/',
	'src/routes/(app)/education/',
	'src/routes/(app)/join/',
	'src/lib/components/common/Modal.svelte',
	'src/lib/components/common/SensitiveInput.svelte',
	'src/lib/components/common/Textarea.svelte',
	'src/lib/components/common/Tooltip.svelte',
	'src/lib/constants.ts',
	'src/lib/utils/google-drive-picker.ts',
	'src/lib/utils/onedrive-file-picker.ts',
	'src/lib/utils/text-scale.ts',
	'src/lib/utils/characters/',
	'src/lib/utils/marked/',
	'src/lib/workers/',
	'src/app.d.ts'
];

const filteredStderrPatterns = [
	/^.*vite-plugin-svelte.*missing exports condition.*$/i,
	/^.*The following packages have a svelte field in their package\.json but no exports condition for svelte\..*$/i,
	/^.*@sveltejs\/svelte-virtual-list@3\.0\.1.*$/i,
	/^.*Please see https:\/\/github\.com\/sveltejs\/vite-plugin-svelte\/blob\/main\/docs\/faq\.md#missing-exports-condition.*$/i
];

const run = (command, args) => {
	const isWindows = process.platform === 'win32';
	const executable = isWindows ? 'cmd.exe' : command;
	const executableArgs = isWindows ? ['/d', '/s', '/c', command, ...args] : args;

	const result = spawnSync(executable, executableArgs, {
		cwd: process.cwd(),
		encoding: 'utf8',
		shell: false
	});

	if (result.error) {
		throw result.error;
	}

	return result;
};

const syncResult = run('.\\node_modules\\.bin\\svelte-kit.cmd', ['sync']);
if (syncResult.status !== 0) {
	process.stdout.write(syncResult.stdout || '');
	process.stderr.write(syncResult.stderr || '');
	process.exit(syncResult.status ?? 1);
}

const checkResult = run('.\\node_modules\\.bin\\svelte-check.cmd', [
	'--tsconfig',
	'./tsconfig.json',
	'--output',
	'machine'
]);

const stdout = checkResult.stdout || '';
const stderr = (checkResult.stderr || '')
	.split(/\r?\n/)
	.filter(
		(line) => line.trim() === '' || !filteredStderrPatterns.some((pattern) => pattern.test(line))
	)
	.join('\n');
const diagnosticLines = stdout
	.split(/\r?\n/)
	.filter((line) => /\s(ERROR|WARNING)\s"/.test(line));

const relevantDiagnostics = diagnosticLines.filter((line) =>
	focusPrefixes.some((prefix) => line.includes(`"${prefix}`))
);

const relevantErrors = relevantDiagnostics.filter((line) => line.includes(' ERROR '));
const relevantWarnings = relevantDiagnostics.filter((line) => line.includes(' WARNING '));

if (relevantDiagnostics.length > 0) {
	process.stdout.write(relevantDiagnostics.join('\n'));
	process.stdout.write('\n');
}

const ignoredCount = diagnosticLines.length - relevantDiagnostics.length;
if (ignoredCount > 0) {
	process.stdout.write(
		`Incremental check ignored ${ignoredCount} legacy diagnostics outside the education scope. Run \`npm run check:full\` for the full scan.\n`
	);
}

if (stderr.trim()) {
	process.stderr.write(stderr);
}

if (relevantErrors.length > 0) {
	process.exit(1);
}

process.stdout.write(
	`Incremental check passed with ${relevantWarnings.length} scoped warnings.\n`
);
