'use strict'

const { app, BrowserWindow, dialog, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')

const isDev = !app.isPackaged
const BACKEND_PORT = 8001

let mainWindow = null
let backendProcess = null

// ── Backend binary location ──────────────────────────────────────────────────

function getBackendBin() {
  // Packaged: resources/backend/trading_server (PyInstaller onedir)
  return path.join(process.resourcesPath, 'backend', 'trading_server')
}

function getUserDataDir() {
  return app.getPath('userData')
}

// ── Env file bootstrap ───────────────────────────────────────────────────────

function ensureEnvFile() {
  const userDataDir = getUserDataDir()
  const destEnv = path.join(userDataDir, '.env')

  if (!fs.existsSync(destEnv)) {
    const srcEnv = path.join(process.resourcesPath, '.env')
    if (fs.existsSync(srcEnv)) {
      fs.copyFileSync(srcEnv, destEnv)
    }
  }

  return destEnv
}

// ── Start the Python backend ─────────────────────────────────────────────────

function startBackend() {
  const userDataDir = getUserDataDir()
  const dbPath = path.join(userDataDir, 'trading.db')

  let bin, args, cwd

  if (isDev) {
    const backendDir = path.join(__dirname, '../../backend')
    const venv = path.join(backendDir, '.venv')
    const python = path.join(venv, 'bin', 'python3')
    bin = python
    args = ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)]
    cwd = backendDir
  } else {
    const envFile = ensureEnvFile()
    bin = getBackendBin()
    args = []
    cwd = path.dirname(bin)
    process.env.ENV_FILE_PATH = envFile
  }

  const env = {
    ...process.env,
    DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
    PORT: String(BACKEND_PORT),
  }

  backendProcess = spawn(bin, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] })
  backendProcess.stdout.on('data', d => console.log('[backend]', d.toString().trim()))
  backendProcess.stderr.on('data', d => console.error('[backend]', d.toString().trim()))
  backendProcess.on('error', err => console.error('[backend] spawn error:', err))
  backendProcess.on('exit', code => console.log('[backend] exited with code', code))
}

// ── Poll until the backend health endpoint responds ──────────────────────────

function waitForBackend(retries = 40, delayMs = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0

    function attempt() {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/health`, res => {
        if (res.statusCode === 200) return resolve()
        retry()
      })
      req.on('error', retry)
      req.setTimeout(400, () => { req.destroy(); retry() })
    }

    function retry() {
      attempts++
      if (attempts >= retries) return reject(new Error('Backend did not start in time'))
      setTimeout(attempt, delayMs)
    }

    attempt()
  })
}

// ── Create the main window ───────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'Trading App',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:3000')
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // Open external links in the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── App lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend()

  try {
    await waitForBackend()
  } catch {
    dialog.showErrorBox(
      'Startup Error',
      'The trading server failed to start.\nPlease restart the app or check the logs.'
    )
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => {
  if (backendProcess) {
    backendProcess.kill('SIGTERM')
    backendProcess = null
  }
})
