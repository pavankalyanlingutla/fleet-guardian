import { useEffect, useState } from 'react'
import './App.css'

// Where the Flask control API lives (api.py runs on port 7000).
const API = 'http://127.0.0.1:7000'

export default function App() {
  // State = data this component owns. When it changes, React re-renders.
  const [devices, setDevices] = useState([])   // from GET /devices
  const [history, setHistory] = useState([])   // from GET /automation/history
  const [lastRun, setLastRun] = useState(null) // from POST /automation/run
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  // Read current device status from Flask.
  async function loadDevices() {
    try {
      const res = await fetch(`${API}/devices`)
      if (!res.ok) throw new Error(`GET /devices failed: ${res.status}`)
      setDevices(await res.json())
      setError('')
    } catch (err) {
      setError(`Can't reach the API at ${API}. Is "python3 -m app.api" running?`)
    }
  }

  // Read past runs (stored in SQLite) from Flask.
  async function loadHistory() {
    try {
      const res = await fetch(`${API}/automation/history`)
      if (res.ok) setHistory(await res.json())
    } catch {
      // loadDevices already shows the connection error
    }
  }

  // Trigger one detect -> analyze -> remediate -> validate cycle.
  async function runAutomation() {
    setRunning(true)
    try {
      const res = await fetch(`${API}/automation/run`, { method: 'POST' })
      if (!res.ok) throw new Error(`POST /automation/run failed: ${res.status}`)
      setLastRun(await res.json())
      await Promise.all([loadDevices(), loadHistory()]) // refresh after the fix
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  // useEffect with [] runs once when the page loads,
  // then polls device status every 5 seconds.
  useEffect(() => {
    loadDevices()
    loadHistory()
    const timer = setInterval(loadDevices, 5000)
    return () => clearInterval(timer) // cleanup when the component unmounts
  }, [])

  const unhealthy = devices.filter((d) => d.healthy === false).length

  return (
    <main className="page">
      <header className="top">
        <div>
          <h1>fleet-guardian</h1>
          <p className="sub">
            {devices.length} devices · {unhealthy === 0 ? 'all healthy' : `${unhealthy} unhealthy`}
          </p>
        </div>
        <button onClick={runAutomation} disabled={running}>
          {running ? 'Running…' : 'Run automation'}
        </button>
      </header>

      {error && <p className="error">{error}</p>}

      <section>
        <h2>Devices</h2>
        <table>
          <thead>
            <tr><th>Device</th><th>Status</th><th>CPU</th><th>Connections</th></tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              // key tells React which row is which between re-renders
              <tr key={d.device_id} className={d.error ? 'down' : d.healthy ? 'ok' : 'bad'}>
                <td>{d.device_id}</td>
                <td>{d.error ? 'Unreachable' : d.healthy ? 'Healthy' : 'Unhealthy'}</td>
                <td>{d.cpu_load != null ? `${d.cpu_load.toFixed(1)}%` : '—'}</td>
                <td>{d.active_connections ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {lastRun && (
        <section>
          <h2>Last run (#{lastRun.run_id})</h2>
          <p>
            Checked {lastRun.devices_checked}, found {lastRun.devices_unhealthy} unhealthy
            {lastRun.unreachable.length > 0 && `, ${lastRun.unreachable.length} unreachable`}.
          </p>
          <ul className="plain">
            {lastRun.remediations.map((r) => (
              <li key={r.device_id}>
                {r.device_id}: {r.action_taken ?? 'no action'} →{' '}
                <strong className={r.validated ? 'okText' : 'badText'}>
                  {r.validated ? 'fixed and validated' : 'not validated, needs a person'}
                </strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>Run history</h2>
        {history.length === 0 ? (
          <p className="sub">No runs yet. Use Run automation to start the first one.</p>
        ) : (
          <ul className="plain">
            {history.map((run) => (
              <li key={run.run_id}>
                Run #{run.run_id} · {new Date(run.started_at).toLocaleString()} ·{' '}
                {run.events.length} events
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
