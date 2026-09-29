/** Parse first-party JavaScript without executing browser or worker code. */
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const files = [...new Set(execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    { encoding: 'utf8' }).split('\0'))];
let checked = 0;
let failed = false;
for (const file of files) {
    if (!/\.(?:js|mjs)$/.test(file) || !existsSync(file)
        || /^(?:static\/vendor\/|static\/foliate-js\/|static\/marked\.min\.js)/.test(file)) continue;
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    checked++;
    if (result.status !== 0) {
        process.stderr.write(result.stderr || String(result.error));
        failed = true;
    }
}
console.log(`Parsed ${checked} first-party JavaScript files.`);
process.exitCode = failed ? 1 : 0;
