const packages = [
	'micropip',
	'packaging',
	'requests',
	'beautifulsoup4',
	'numpy',
	'pandas',
	'matplotlib',
	'scikit-learn',
	'scipy',
	'regex',
	'sympy',
	'tiktoken',
	'seaborn',
	'pytz',
	'black',
	'openai',
	'openpyxl'
];

// Pure-Python packages whose wheels must be downloaded from PyPI and saved into
// static/pyodide/ so that the browser can install them offline via micropip.
// Packages already provided by the Pyodide distribution (click, platformdirs,
// typing_extensions, etc.) do NOT need to be listed here.
const pypiPackages = ['black', 'pathspec', 'mypy_extensions', 'pytokens'];

import { loadPyodide } from 'pyodide';
import { setGlobalDispatcher, ProxyAgent } from 'undici';
import { writeFile, readFile, copyFile, readdir, rmdir, access } from 'fs/promises';
import { createHash } from 'crypto';

/**
 * Loading network proxy configurations from the environment variables.
 * And the proxy config with lowercase name has the highest priority to use.
 */
function initNetworkProxyFromEnv() {
	// we assume all subsequent requests in this script are HTTPS:
	// https://cdn.jsdelivr.net
	// https://pypi.org
	// https://files.pythonhosted.org
	const allProxy = process.env.all_proxy || process.env.ALL_PROXY;
	const httpsProxy = process.env.https_proxy || process.env.HTTPS_PROXY;
	const httpProxy = process.env.http_proxy || process.env.HTTP_PROXY;
	const preferedProxy = httpsProxy || allProxy || httpProxy;
	/**
	 * use only http(s) proxy because socks5 proxy is not supported currently:
	 * @see https://github.com/nodejs/undici/issues/2224
	 */
	if (!preferedProxy || !preferedProxy.startsWith('http')) return;
	let preferedProxyURL;
	try {
		preferedProxyURL = new URL(preferedProxy).toString();
	} catch {
		console.warn(`Invalid network proxy URL: "${preferedProxy}"`);
		return;
	}
	const dispatcher = new ProxyAgent({ uri: preferedProxyURL });
	setGlobalDispatcher(dispatcher);
	console.log(`Initialized network proxy "${preferedProxy}" from env`);
}

async function downloadPackages() {
	console.log('Setting up pyodide + micropip');

	let pyodide;
	try {
		pyodide = await loadPyodide({
			packageCacheDir: 'static/pyodide'
		});
	} catch (err) {
		console.error('Failed to load Pyodide:', err);
		return;
	}

	const packageJson = JSON.parse(await readFile('package.json'));
	const pyodideVersion = packageJson.dependencies.pyodide.replace('^', '');

	try {
		const pyodidePackageJson = JSON.parse(await readFile('static/pyodide/package.json'));
		const pyodidePackageVersion = pyodidePackageJson.version.replace('^', '');

		if (pyodideVersion !== pyodidePackageVersion) {
			console.log('Pyodide version mismatch, removing static/pyodide directory');
			await rmdir('static/pyodide', { recursive: true });
		}
	} catch (err) {
		console.log('Pyodide package not found, proceeding with download.', err);
	}

	try {
		console.log('Loading micropip package');
		await pyodide.loadPackage('micropip');

		const micropip = pyodide.pyimport('micropip');
		console.log('Downloading Pyodide packages:', packages);

		try {
			for (const pkg of packages) {
				console.log(`Installing package: ${pkg}`);
				await micropip.install(pkg);
			}
		} catch (err) {
			console.error('Package installation failed:', err);
			return;
		}

		console.log('Pyodide packages downloaded, freezing into lock file');

		try {
			const lockFile = await micropip.freeze();
			await writeFile('static/pyodide/pyodide-lock.json', lockFile);
		} catch (err) {
			console.error('Failed to write lock file:', err);
		}
	} catch (err) {
		console.error('Failed to load or install micropip:', err);
	}
}

async function copyPyodide() {
	console.log('Copying Pyodide files into static directory');
	// Copy all files from node_modules/pyodide to static/pyodide
	for await (const entry of await readdir('node_modules/pyodide')) {
		await copyFile(`node_modules/pyodide/${entry}`, `static/pyodide/${entry}`);
	}
}

/**
 * Resolve the latest pure-Python wheel for `pkg` on PyPI and make sure it is saved
 * into static/pyodide/. Throws on network failure; returns null when PyPI answers
 * but has no usable wheel.
 */
async function fetchPyPIWheel(pkg) {
	const res = await fetch(`https://pypi.org/pypi/${pkg}/json`);
	if (!res.ok) {
		console.error(`Failed to fetch PyPI metadata for ${pkg}: ${res.status}`);
		return null;
	}
	const meta = await res.json();
	const version = meta.info.version;
	const files = meta.urls || [];
	// Find the pure-Python wheel (py3-none-any)
	const wheel = files.find(
		(f) => f.filename.endsWith('.whl') && f.filename.includes('py3-none-any')
	);
	if (!wheel) {
		console.warn(`No pure-Python wheel found for ${pkg}==${version}, skipping`);
		return null;
	}
	const dest = `static/pyodide/${wheel.filename}`;
	// Download wheel if not already present
	try {
		await access(dest);
		console.log(`  Already exists: ${wheel.filename}`);
	} catch {
		console.log(`  Downloading: ${wheel.filename}`);
		const wheelRes = await fetch(wheel.url);
		if (!wheelRes.ok) {
			console.error(`  Failed to download ${wheel.filename}: ${wheelRes.status}`);
			return null;
		}
		const buffer = Buffer.from(await wheelRes.arrayBuffer());
		await writeFile(dest, buffer);
		console.log(`  Saved: ${dest} (${buffer.length} bytes)`);
	}
	return { version, filename: wheel.filename, sha256: wheel.digests?.sha256 || '' };
}

/** Offline fallback: the newest `<name>-<version>-py3-none-any.whl` already in static/pyodide/. */
async function findLocalWheel(normalizedName) {
	const candidates = (await readdir('static/pyodide'))
		.filter((file) => file.startsWith(`${normalizedName}-`) && file.endsWith('-py3-none-any.whl'))
		.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
	const filename = candidates.at(-1);
	if (!filename) return null;
	const sha256 = createHash('sha256')
		.update(await readFile(`static/pyodide/${filename}`))
		.digest('hex');
	return { version: filename.split('-')[1], filename, sha256 };
}

/**
 * Download pure-Python wheels from PyPI and save them into static/pyodide/.
 * Also injects entries into pyodide-lock.json so that micropip resolves these
 * packages from the local server instead of fetching them from the internet.
 */
async function downloadPyPIWheels() {
	const lockPath = 'static/pyodide/pyodide-lock.json';
	let lockData;
	try {
		lockData = JSON.parse(await readFile(lockPath, 'utf-8'));
	} catch {
		console.warn('Could not read pyodide-lock.json, skipping PyPI wheel download');
		return;
	}

	for (const pkg of pypiPackages) {
		const normalizedName = pkg.replace(/-/g, '_');
		console.log(`Fetching PyPI metadata for: ${pkg}`);
		let wheel;
		try {
			wheel = await fetchPyPIWheel(pkg);
		} catch (err) {
			// 连不上 PyPI（断网、TLS 被重置）时改用本地已下载的 wheel 登记。
			// 不接住的话异常会让整个脚本退出，`npm run dev` 后面的 vite 根本起不来；
			// 只跳过不登记的话，copyPyodide 刚用原版 lock 覆盖过，这几个包就从 lock 里丢了。
			console.warn(`  Could not reach PyPI for ${pkg}: ${err.cause?.code ?? err.message ?? err}`);
			wheel = await findLocalWheel(normalizedName);
			if (!wheel) {
				console.warn(`  No local wheel for ${pkg} either, skipping`);
				continue;
			}
			console.log(`  Using local wheel: ${wheel.filename}`);
		}
		if (!wheel) continue;

		// Inject into pyodide-lock.json so micropip resolves locally
		if (!lockData.packages[normalizedName]) {
			lockData.packages[normalizedName] = {
				name: normalizedName,
				version: wheel.version,
				file_name: wheel.filename,
				install_dir: 'site',
				sha256: wheel.sha256,
				package_type: 'package',
				imports: [normalizedName],
				depends: []
			};
			console.log(`  Added ${normalizedName}==${wheel.version} to pyodide-lock.json`);
		}
	}

	await writeFile(lockPath, JSON.stringify(lockData, null, 2));
	console.log('Updated pyodide-lock.json with PyPI packages');
}

initNetworkProxyFromEnv();
await downloadPackages();
await copyPyodide();
await downloadPyPIWheels();
