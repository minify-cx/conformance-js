#!/usr/bin/env node
'use strict';

const fs = require('fs');
const vm = require('vm');

const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const unhandled = new Map();
process.on('unhandledRejection', (reason, promise) => unhandled.set(promise, reason));
process.on('rejectionHandled', promise => unhandled.delete(promise));

function hostFor(context) {
  const host = {
    global: vm.runInContext('this', context),
    evalScript(source) {
      return vm.runInContext(String(source), context);
    },
    createRealm() {
      const childSandbox = {};
      const child = vm.createContext(childSandbox);
      const childHost = hostFor(child);
      childSandbox.$262 = childHost;
      return childHost;
    },
    detachArrayBuffer(buffer) {
      structuredClone(buffer, { transfer: [buffer] });
    },
    gc() {
      if (typeof global.gc === 'function') global.gc();
    }
  };
  return host;
}

async function execute(job) {
  const sandbox = { __Test262Async: Boolean(job.async) };
  const context = vm.createContext(sandbox);
  sandbox.$262 = hostFor(context);
  let timer;
  let doneResolve;
  let doneReject;
  const done = new Promise((resolve, reject) => {
    doneResolve = resolve;
    doneReject = reject;
  });
  sandbox.$DONE = error => error ? doneReject(error) : doneResolve();
  try {
    vm.runInContext(job.code, context, { timeout: job.timeout_ms });
    if (job.async) {
      await Promise.race([
        done,
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('Test262 async timeout')), job.timeout_ms);
        })
      ]);
    }
    await new Promise(resolve => setImmediate(resolve));
    if (unhandled.size) {
      const reason = unhandled.values().next().value;
      unhandled.clear();
      throw reason;
    }
    return { ok: true };
  } catch (error) {
    const message = String(error && error.message || error);
    // Match both "Script execution timed out after 5000ms" (vm.runInContext)
    // and the async $DONE timeout message; the word "timeout" alone misses
    // the vm phrasing.
    const isTimeout = /timeout|timed\s*out/i.test(message);
    return {
      ok: false,
      timeout: isTimeout,
      error: String(error && error.stack || error)
    };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

(async () => {
  const results = [];
  for (const job of jobs) {
    results.push(await execute(job));
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exitCode = 1;
});
