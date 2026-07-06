import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');

const candidates = process.platform === 'win32'
	? [path.join(repoRoot, 'backend', '.venv', 'Scripts', 'python.exe')]
	: [
			path.join(repoRoot, 'backend', '.venv', 'bin', 'python'),
			path.join(repoRoot, '.venv', 'bin', 'python')
		];

const python = candidates.find((candidate) => existsSync(candidate));

if (!python) {
	console.error('No project Python interpreter found under backend/.venv.');
	process.exit(1);
}

const pythonArgs = process.argv.slice(2);
const pytestCacheDir = path.join('.tmp', 'pytest-cache');
const tempRoot = mkdtempSync(path.join(os.tmpdir(), 'open-webui-backend-python-'));

mkdirSync(pytestCacheDir, { recursive: true });

if (pythonArgs.length === 0) {
	console.error('Usage: node scripts/run-backend-python.js <script-or-python-args> [...]');
	process.exit(1);
}

const result = spawnSync(python, pythonArgs, {
	cwd: repoRoot,
	env: {
		...process.env,
		TMP: tempRoot,
		TEMP: tempRoot,
		TMPDIR: tempRoot,
		PYTEST_ADDOPTS: process.env.PYTEST_ADDOPTS
			? `${process.env.PYTEST_ADDOPTS} -o cache_dir=${pytestCacheDir}`
			: `-o cache_dir=${pytestCacheDir}`
	},
	stdio: 'inherit'
});

try {
	rmSync(tempRoot, { recursive: true, force: true });
} catch {}

if (result.error) {
	console.error(result.error.message);
	process.exit(1);
}

process.exit(result.status ?? 1);
