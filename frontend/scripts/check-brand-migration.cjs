/* Validate persisted-state compatibility without a browser or external packages. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/lib/brandedStorage.ts'), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const context = { exports: {} };
vm.runInNewContext(js, context);
const { readBrandedStorage, SESSION_STORAGE_KEY, LEGACY_SESSION_STORAGE_KEY, ITINERARY_STORAGE_KEY, LEGACY_ITINERARY_STORAGE_KEY } = context.exports;
for (const [key, legacy] of [[SESSION_STORAGE_KEY, LEGACY_SESSION_STORAGE_KEY], [ITINERARY_STORAGE_KEY, LEGACY_ITINERARY_STORAGE_KEY]]) {
  const values = new Map([[legacy, 'old-value']]);
  const storage = { getItem: name => values.get(name) ?? null, setItem: (name, value) => values.set(name, value) };
  assert.equal(readBrandedStorage(storage, key, legacy), 'old-value');
  assert.equal(values.get(key), 'old-value');
  assert.equal(values.get(legacy), 'old-value');
  values.set(key, 'new-value');
  assert.equal(readBrandedStorage(storage, key, legacy), 'new-value');
  values.clear();
  assert.equal(readBrandedStorage(storage, key, legacy), null);
  values.set(legacy, 'backup');
  assert.equal(readBrandedStorage({ ...storage, setItem: () => { throw new Error('quota'); } }, key, legacy), 'backup');
}
const sessionSource = fs.readFileSync(require('node:path').join(__dirname, '../app/lib/session.ts'), 'utf8');
const sessionJs = ts.transpileModule(sessionSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const sessionValues = new Map([[LEGACY_SESSION_STORAGE_KEY, 'existing-session']]);
const sessionContext = { exports: {}, window: {}, require: () => context.exports,
  localStorage: { getItem: key => sessionValues.get(key) ?? null, setItem: (key, value) => sessionValues.set(key, value), removeItem: key => sessionValues.delete(key) } };
vm.runInNewContext(sessionJs, sessionContext);
assert.equal(sessionContext.exports.getSessionId(), 'existing-session');
assert.equal(sessionContext.exports.hasSessionId(), true);
sessionContext.exports.clearSessionId();
assert.equal(sessionValues.has(LEGACY_SESSION_STORAGE_KEY), false);
assert.equal(sessionContext.exports.hasSessionId(), false);
assert.notEqual(sessionContext.exports.getSessionId(), 'existing-session');
console.log('Brand storage migration: PASS (copy, precedence, empty, quota fallback, session continuity and clearing)');
