const { spawnSync } = require('node:child_process');
const path = require('node:path');

const tests = [
  'welcome-intro', 'compact-intent-ui', 'live-intent-retention', 'search-picker-ui',
  'weather-hud-ui', 'robot-progress', 'route-progress-ui', 'route-transparency-ui', 'floating-routes', 'place-candidates',
];
let failures = 0;
for (const name of tests) {
  console.log(`\nBrowser test: ${name}`);
  const result = spawnSync(process.execPath, [path.join(__dirname, `${name}.e2e.cjs`)], {
    cwd: path.resolve(__dirname, '../..'), stdio: 'inherit', timeout: 180000,
  });
  if (result.error || result.status !== 0) {
    failures++;
    console.error(`${name}: FAILED`, result.error?.message || `exit ${result.status}`);
  }
}
console.log(`\nBrowser tests: ${tests.length - failures} passed, ${failures} failed`);
process.exitCode = failures ? 1 : 0;
