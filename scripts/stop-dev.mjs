import { execFileSync } from 'node:child_process'

const devPorts = new Set(['5173', '8000'])

// 只处理监听中的开发端口，避免误杀同端口的短暂连接记录。
function listDevListeners() {
  const output = execFileSync('netstat', ['-ano'], { encoding: 'utf8' })
  const listeners = new Map()

  for (const line of output.split(/\r?\n/)) {
    const columns = line.trim().split(/\s+/)
    if (columns.length < 5 || columns[0] !== 'TCP' || columns[3] !== 'LISTENING') continue

    const localPort = columns[1].match(/:(\d+)$/)?.[1]
    const pid = columns[4]
    if (!localPort || !devPorts.has(localPort)) continue

    if (!listeners.has(pid)) listeners.set(pid, new Set())
    listeners.get(pid).add(localPort)
  }

  return listeners
}

// 打印进程名能让端口冲突一眼看出是不是旧的前后端实例。
function describeProcess(pid) {
  try {
    const output = execFileSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], {
      encoding: 'utf8',
    }).trim()
    const name = output.match(/^"([^"]+)"/)?.[1]
    return name ? `${name} pid=${pid}` : `pid=${pid}`
  } catch {
    return `pid=${pid}`
  }
}

// 杀掉进程树，避免 pnpm/cmd/node/python 只停掉其中一层后留下真正监听端口的子进程。
function stopProcessTree(pid, ports) {
  console.log(`Stopping ${describeProcess(pid)} on port(s): ${[...ports].join(', ')}`)

  try {
    execFileSync('taskkill', ['/PID', pid, '/T', '/F'], { stdio: 'inherit' })
  } catch (error) {
    console.warn(`Failed to stop pid=${pid}; verifying ports before failing.`)
  }
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

const listeners = listDevListeners()

if (listeners.size === 0) {
  console.log('No TRPG dev ports are listening.')
  process.exit(0)
}

for (const [pid, ports] of listeners) {
  stopProcessTree(pid, ports)
}

sleep(500)

const remaining = listDevListeners()
if (remaining.size === 0) {
  console.log('TRPG dev ports are free.')
  process.exit(0)
}

console.error('TRPG dev ports are still occupied:')
for (const [pid, ports] of remaining) {
  console.error(`- ${describeProcess(pid)} on port(s): ${[...ports].join(', ')}`)
}
process.exit(1)
