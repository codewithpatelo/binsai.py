/* Binsai MVP1 — main.js */

const WS_URL = `ws://${location.host}/ws/sim`;

let ws         = null;
let game       = null;
let ablationOff = false;
let simRunning  = false;

function send(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    connectWS();
    return false;
  }
  ws.send(JSON.stringify(obj));
  return true;
}

function setSimState(running) {
  simRunning = running;
  var btnStart = document.getElementById('btn-start');
  var btnPause = document.getElementById('btn-pause');
  var statusBar = document.getElementById('status-bar');
  if (running) {
    btnStart.classList.add('running');
    btnStart.classList.remove('paused');
    btnPause.classList.remove('paused');
    btnPause.classList.remove('running');
    statusBar.textContent = '● Running';
    statusBar.className = 'connected';
  } else {
    btnStart.classList.remove('running');
    btnPause.classList.add('paused');
    statusBar.textContent = '⏸ Paused';
    statusBar.className = 'paused';
  }
}

function connectWS() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    send({ cmd: 'start' });
    setSimState(true);
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'frame') {
      window._lastFrame = msg;   // expose to scene for KPI config access
      const scene = game && game.scene && game.scene.getScene('InboxScene');
      if (scene) scene.onFrame(msg);
    } else if (msg.type === 'control') {
      if (msg.event === 'ablation_toggled') {
        ablationOff = msg.ablation_off;
        document.getElementById('ablation-badge').classList.toggle('active', ablationOff);
        var btnAbl = document.getElementById('btn-ablation');
        if (btnAbl) {
          btnAbl.textContent = ablationOff ? 'Regulation ON' : 'Regulation OFF';
          btnAbl.className = ablationOff ? 'active' : 'danger';
        }
        appendLog('[control] ablation ' + (ablationOff ? 'OFF' : 'ON'), 'critical');
      } else if (msg.event === 'reset') {
        appendLog('[control] reset', 'lifecycle');
      } else if (msg.event === 'agent_ablation_toggled') {
        var state = msg.ablation_off ? 'UNREG' : 'regulated';
        appendLog('[control] agent ' + msg.aid + ' → ' + state, 'critical');
      }
    } else if (msg.type === 'proact.inform') {
      // handled by scene via frame events
    } else if (msg.type === 'error') {
      appendLog('[error] ' + msg.message, 'critical');
    }
  };

  ws.onclose = () => {
    var sb = document.getElementById('status-bar');
    sb.textContent = 'Reconnecting...'; sb.className = '';
    setTimeout(connectWS, 2000);
  };

  ws.onerror = () => {
    var sb = document.getElementById('status-bar');
    sb.textContent = 'Connection error'; sb.className = 'error';
  };
}

// ── Controls ──────────────────────────────────────────────────────────────────
document.getElementById('btn-start').addEventListener('click', () => { if (send({ cmd: 'start' })) setSimState(true); });
document.getElementById('btn-pause').addEventListener('click', () => { if (send({ cmd: 'pause' })) setSimState(false); });
document.getElementById('btn-reset').addEventListener('click', () => { if (send({ cmd: 'reset' })) setSimState(true); });
var _btnAbl = document.getElementById('btn-ablation');
if (_btnAbl) _btnAbl.addEventListener('click', () => send({ cmd: 'toggle_ablation' }));

document.getElementById('speed').addEventListener('input', function() {
  var v = parseFloat(this.value);
  document.getElementById('speed-val').textContent = v;
  send({ cmd: 'set_speed', value: v });
});

document.getElementById('lambda').addEventListener('input', function() {
  var v = parseFloat(this.value);
  document.getElementById('lambda-val').textContent = v.toFixed(1);
  send({ cmd: 'set_lambda_demand', value: v });
});

// ── Regulatory budget sliders ───────────────────────────────────────────────
function pushBudgets() {
  var cost    = parseFloat(document.getElementById('budget-cost').value);
  var latency = parseFloat(document.getElementById('budget-latency').value);
  var tokens  = parseInt(  document.getElementById('budget-tokens').value, 10);
  send({
    cmd:                  'set_budgets',
    cost_per_call_usd:    cost,
    latency_per_call_ms:  latency,
    tokens_per_call:      tokens,
  });
}
document.getElementById('budget-cost').addEventListener('input', function() {
  document.getElementById('budget-cost-val').textContent = parseFloat(this.value).toFixed(4);
  pushBudgets();
});
document.getElementById('budget-latency').addEventListener('input', function() {
  document.getElementById('budget-latency-val').textContent = this.value;
  pushBudgets();
});
document.getElementById('budget-tokens').addEventListener('input', function() {
  document.getElementById('budget-tokens-val').textContent = this.value;
  pushBudgets();
});

// ── Log ───────────────────────────────────────────────────────────────────────
var MAX_LOG = 40;
function appendLog(text, cls) {
  var log  = document.getElementById('log');
  var line = document.createElement('div');
  line.className = 'log-line ' + (cls || '');
  line.textContent = text;
  log.appendChild(line);
  while (log.children.length > MAX_LOG) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}
window.appendLog = appendLog;

// ── Phaser bootstrap ──────────────────────────────────────────────────────────
window.addEventListener('load', function() {
  var col    = document.getElementById('canvas-col');
  var W      = col.clientWidth;
  var H      = col.clientHeight;
  var canvas = document.getElementById('game-canvas');

  // Fix canvas size explicitly — Phaser Scale.RESIZE was overflowing the sidebar
  canvas.width  = W;
  canvas.height = H;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';

  game = new Phaser.Game({
    type:            Phaser.CANVAS,
    canvas:          canvas,
    width:           W,
    height:          H,
    backgroundColor: '#0d1117',
    scene:           [InboxScene],
    scale:           { mode: Phaser.Scale.NONE },
    pixelArt:        false,
  });

  connectWS();
});
