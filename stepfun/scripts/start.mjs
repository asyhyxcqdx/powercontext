import { spawn } from 'node:child_process';
const env = { ...process.env };
// Linux's dlopen TLS reserve can be smaller than libseekdb's static TLS block.
// Reserve space for this child process only; no system settings are changed.
if (process.platform === 'linux' && !env.SEEKDB_HOST && !env.GLIBC_TUNABLES?.includes('glibc.rtld.optional_static_tls=')) {
  env.GLIBC_TUNABLES = [env.GLIBC_TUNABLES, 'glibc.rtld.optional_static_tls=65536'].filter(Boolean).join(':');
}
const child = spawn(process.execPath, ['--disable-sigusr1', 'server.mjs'], { stdio: 'inherit', env, cwd: new URL('..', import.meta.url) });
for (const signal of ['SIGINT','SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
