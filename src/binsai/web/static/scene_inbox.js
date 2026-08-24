/* Binsai MVP1 — scene_inbox.js  (LPC layered civilians)
   Sprites: LPC Medieval Fantasy (CC-BY-SA 3.0, bluecarrot16 et al.)
   Layers per agent: BODY_male + shirt_white + pants_green + hair + shoes → clothed civilian
   Human: LPC irishdress (832×1344 Universal format), purple-tinted
   64×64 frames, scale 2× → 128×128 display
   Layout: equal panels [HUMAN | ALPHA | BETA | GAMMA]
*/

// ── LPC Walk (576×256): 9 frames/row, 4 rows, 64×64 ──────────────────────────
// Row 0: walk up   (frames  0– 8)
// Row 1: walk left (frames  9–17)
// Row 2: walk down (frames 18–26) ← facing camera = idle
// Row 3: walk right(frames 27–35)
const WALK_SOUTH = { start: 18, end: 26 };
const WALK_SOUTH_FRAMES = [18, 19, 20, 21, 22, 23, 24, 25, 26];

// ── LPC Spellcast (448×256): 7 frames/row, 4 rows, 64×64 ────────────────────
// Row 2: cast south (frames 14–20) — arms reaching forward = typing pose
const CAST_SOUTH = { start: 14, end: 20 };

// ── LPC Hurt (384×64): 6 frames, single row, 64×64 ──────────────────────────
// Frame 5 = lying down = sleep at desk pose (slumped)
const HURT_FRAMES = { start: 0, end: 5 };

// ── LPC Universal irishdress (832×1344): 13 cols × 21 rows, 64×64 ───────────
// Walk: rows 8–11 (directions U/L/D/R), walk-south = row 10
// frame index = row*13 + col; row 10 col 0..8 → frames 130–138
const DRESS_WALK_SOUTH = { start: 130, end: 138 };

const LAYER_SCALE = 2;       // 64×64 → 128×128
const SPRITE_W    = 64 * LAYER_SCALE;
const SPRITE_H    = 64 * LAYER_SCALE;

const ZONE_COLOR_HEX = {
  critical_superavit:   0x2ea043,
  high_superavit:       0x3fb950,
  moderate_superavit:   0x56d364,
  equilibrium:          0x58a6ff,
  moderate_deficit:     0xd29922,
  high_deficit:         0xe36209,
  critical_deficit:     0xf85149,
};
const ZONE_COLOR_CSS = {
  critical_superavit:   '#2ea043',
  high_superavit:       '#3fb950',
  moderate_superavit:   '#56d364',
  equilibrium:          '#58a6ff',
  moderate_deficit:     '#d29922',
  high_deficit:         '#e36209',
  critical_deficit:     '#f85149',
};

// Per-agent hair tints (applied to the hair layer only)
const HAIR_TINTS = [
  0x1a0a00,   // Agent 0: very dark brown / almost black
  0x8b2c00,   // Agent 1: auburn / dark orange
  0x4a2200,   // Agent 2: medium brown
];

const SPARKLINE_LEN   = 1200;    // 10 min at 2 t/s, rendered with downsampling
const SPARKLINE_DRAW_WINDOW = 300; // show last N samples in sparkline
const BUBBLE_LIFETIME = 5000;

// ── Per-agent card vertical layout constants ──────────────────────────────────
const SPRITE_TOP        = 54;                           // px from panel top to sprite top edge
const STATS_BASE_OFFSET = SPRITE_TOP + (64 * 2) + 6;   // = 188 — first stats row below sprite

function zoneToSemaphore(zone) {
  return {
    critical_superavit: 0x2ea043, high_superavit: 0x3fb950, moderate_superavit: 0x56d364,
    equilibrium: 0x58a6ff, moderate_deficit: 0xd29922, high_deficit: 0xe36209, critical_deficit: 0xf85149,
  }[zone] || 0x58a6ff;
}

// Hexagon drawn centered at gfx origin (0,0) so we can rotate/scaleX the whole gfx
function drawHexagonCentered(gfx, r, fillColor, accentColor) {
  gfx.clear();
  // Body
  gfx.fillStyle(fillColor, 0.95);
  var pts = [];
  for (var i = 0; i < 6; i++) {
    var a = (i * Math.PI) / 3 - Math.PI / 6;
    pts.push({ x: r * Math.cos(a), y: r * Math.sin(a) });
  }
  gfx.fillPoints(pts, true);
  // Specular highlight (top half lighter — gives 3D feel)
  gfx.fillStyle(accentColor || 0xffffff, 0.22);
  gfx.fillPoints([pts[0], pts[1], pts[2], { x: 0, y: 0 }], true);
  // Outline
  gfx.lineStyle(1.5, 0x30363d, 1);
  gfx.strokePoints(pts, true);
}

// ── InboxScene ────────────────────────────────────────────────────────────────

class InboxScene extends Phaser.Scene {
  constructor() { super({ key: 'InboxScene' }); }

  // ── Preload ─────────────────────────────────────────────────────────────────

  preload() {
    var BASE = '/static/assets/sprites/lpc/';
    var W64  = { frameWidth: 64, frameHeight: 64 };

    // Walk cycle layers (9 frames × 4 rows)
    this.load.spritesheet('walk_body',  BASE + 'walk_body.png',  W64);
    this.load.spritesheet('walk_shirt', BASE + 'walk_shirt.png', W64);
    this.load.spritesheet('walk_pants', BASE + 'walk_pants.png', W64);
    this.load.spritesheet('walk_hair',  BASE + 'walk_hair.png',  W64);
    this.load.spritesheet('walk_shoes', BASE + 'walk_shoes.png', W64);

    // Spellcast layers (7 frames × 4 rows) — typing/working state
    this.load.spritesheet('cast_body',  BASE + 'cast_body.png',  W64);
    this.load.spritesheet('cast_shirt', BASE + 'cast_shirt.png', W64);
    this.load.spritesheet('cast_pants', BASE + 'cast_pants.png', W64);
    this.load.spritesheet('cast_hair',  BASE + 'cast_hair.png',  W64);
    this.load.spritesheet('cast_shoes', BASE + 'cast_shoes.png', W64);

    // Hurt layers (6 frames, 1 row) — last frame = lying down = sleep
    this.load.spritesheet('hurt_body',  BASE + 'hurt_body.png',  W64);
    this.load.spritesheet('hurt_shirt', BASE + 'hurt_shirt.png', W64);
    this.load.spritesheet('hurt_pants', BASE + 'hurt_pants.png', W64);
    this.load.spritesheet('hurt_hair',  BASE + 'hurt_hair.png',  W64);

    // Human (LPC Universal irishdress 832×1344, 13 cols × 21 rows)
    this.load.spritesheet('human_dress', BASE + 'human_dress.png', W64);

    // Provider logos
    this.load.image('logo_deepseek', '/static/assets/providers/deepseek.png');

    this.load.on('loaderror', function(f) { console.error('[load error]', f.key, f.url); });
    this.load.on('complete',  function()  { console.log('[preload] done'); });
  }

  // ── Create ─────────────────────────────────────────────────────────────────

  create() {
    this.W = this.scale.width;
    this.H = this.scale.height;

    this._tick         = 0;
    this._totalDemands = 0;
    this._demandsSent  = 0;
    this._sparks       = {};
    this._costSparks   = {};
    this._ctxSparks    = {};
    this._panelsBuilt  = false;
    this._panelObjs    = [];
    this._panelBounds  = [];

    this._bgGfx    = this.add.graphics();
    this._sparkGfx = this.add.graphics();
    this._divGfx   = this.add.graphics();

    this._createAnims();
    this._applyNearestFilter();
    this._buildLayout();

    this._waitText = this.add.text(this.W / 2, this.H * 0.6, 'Connecting...', {
      fontFamily: 'monospace', fontSize: '16px', color: '#484f58',
    }).setOrigin(0.5);

    this._bobOffset = 0;
    this.time.addEvent({
      delay: 450, loop: true,
      callback: () => { this._bobOffset = this._bobOffset === 0 ? -3 : 0; },
    });
  }

  // ── NEAREST texture filter (sharp pixels without global pixelArt mode) ──────

  _applyNearestFilter() {
    var keys = [
      'walk_body','walk_shirt','walk_pants','walk_hair','walk_shoes',
      'cast_body','cast_shirt','cast_pants','cast_hair','cast_shoes',
      'hurt_body','hurt_shirt','hurt_pants','hurt_hair','human_dress',
    ];
    var NF = Phaser.Textures.FilterMode.NEAREST;
    var textures = this.textures;
    keys.forEach(function(k) {
      var tex = textures.get(k);
      if (tex && tex.setFilter) tex.setFilter(NF);
    });
  }

  // ── Animations ─────────────────────────────────────────────────────────────

  _createAnims() {
    var A = this.anims;
    // Walk south — all walk layers share the same frame range
    ['walk_body','walk_shirt','walk_pants','walk_hair','walk_shoes'].forEach(function(k) {
      A.create({ key: k + '_south', frames: A.generateFrameNumbers(k, WALK_SOUTH), frameRate: 7, repeat: -1 });
    });
    // Spellcast south — typing/reaching pose
    ['cast_body','cast_shirt','cast_pants','cast_hair','cast_shoes'].forEach(function(k) {
      A.create({ key: k + '_south', frames: A.generateFrameNumbers(k, CAST_SOUTH), frameRate: 8, repeat: -1 });
    });
    // Hurt — play once to last frame (slumped = sleep)
    ['hurt_body','hurt_shirt','hurt_pants','hurt_hair'].forEach(function(k) {
      A.create({ key: k + '_fall', frames: A.generateFrameNumbers(k, HURT_FRAMES), frameRate: 6, repeat: 0 });
    });
    // Human dress walk south
    A.create({ key: 'human_walk', frames: A.generateFrameNumbers('human_dress', DRESS_WALK_SOUTH), frameRate: 7, repeat: -1 });
  }

  // ── Layout (title bar only) ─────────────────────────────────────────────────

  _buildLayout() {
    const W = this.W, H = this.H;
    const topH   = Math.floor(H * 0.09);
    const midH   = Math.floor(H * 0.73);
    const sparkH = H - topH - midH;

    this._topH   = topH;
    this._midH   = midH;
    this._sparkH = sparkH;
    this._midY   = topH;
    this._sparkY = topH + midH;

    this._bgGfx.fillStyle(0x0d1117, 1);
    this._bgGfx.fillRect(0, 0, W, H);
    this._bgGfx.fillStyle(0x161b22, 1);
    this._bgGfx.fillRect(0, this._sparkY, W, sparkH);
    this._bgGfx.lineStyle(1, 0x30363d, 1);
    this._bgGfx.lineBetween(0, topH, W, topH);
    this._bgGfx.lineBetween(0, this._sparkY, W, this._sparkY);

    this._topText = this.add.text(W / 2, topH * 0.38,
      'Binsai MVP1  —  Inbox bajo presión  |  tick 0', {
      fontFamily: 'monospace', fontSize: '13px', color: '#58a6ff',
    }).setOrigin(0.5, 0.5);

    this.add.text(W / 2, topH * 0.76,
      'agents self-regulate token economy via metabolic drive  ·  low δ = proactive & creative  ·  high δ = defer or sleep', {
      fontFamily: 'monospace', fontSize: '12px', color: '#a8b0bb',
    }).setOrigin(0.5, 0.5);

    this._demandText = this.add.text(W - 12, topH * 0.38, 'demands: 0', {
      fontFamily: 'monospace', fontSize: '11px', color: '#8b949e',
    }).setOrigin(1, 0.5);
  }

  // ── Build panels ────────────────────────────────────────────────────────────

  _buildPanels(agents) {
    const W  = this.W;
    const n  = agents.length + 1;   // +1 for human panel
    const pw = Math.floor(W / n);

    this._panelBounds = Array.from({ length: n }, (_, i) => ({
      x: i * pw, y: this._midY, w: pw, h: this._midH,
    }));

    // Panel dividers
    for (var di = 1; di < n; di++) {
      this._bgGfx.lineStyle(1, 0x30363d, 1);
      this._bgGfx.lineBetween(di * pw, this._midY, di * pw, this._midY + this._midH);
      this._bgGfx.lineBetween(di * pw, this._sparkY, di * pw, this._sparkY + this._sparkH);
    }

    // ── Human panel (index 0) ──
    var hb  = this._panelBounds[0];
    var hcx = hb.x + Math.floor(hb.w / 2);
    var hSpriteCY = hb.y + Math.floor(hb.h * 0.33);

    this.add.text(hcx, hb.y + 10, 'HUMAN', {
      fontFamily: 'monospace', fontSize: '11px', color: '#d2a8ff', fontStyle: 'bold',
    }).setOrigin(0.5, 0);
    this.add.text(hcx, hb.y + 23, 'demand source', {
      fontFamily: 'monospace', fontSize: '9px', color: '#484f58',
    }).setOrigin(0.5, 0);

    // Dress sprite — purple tint for manager look
    this._humanSprite = this.add.sprite(hcx, hSpriteCY, 'human_dress', 130)
      .setScale(LAYER_SCALE).setTint(0xd8a8ff);
    this._humanSprite.play('human_walk');

    // "sent" label sits right below sprite
    this._humanDemandText = this.add.text(hcx, hSpriteCY + SPRITE_H / 2 + 6, 'sent: 0', {
      fontFamily: 'monospace', fontSize: '10px', color: '#8b949e',
    }).setOrigin(0.5, 0);

    // ── Legend card: starts well below the bubble zone ──
    var cardTop  = hSpriteCY + SPRITE_H / 2 + 22;
    var cardBot  = hb.y + hb.h - 6;
    var cardH    = cardBot - cardTop;
    var cardX    = hb.x + 6;
    var cardW    = hb.w - 12;
    var legGfx   = this.add.graphics();
    legGfx.fillStyle(0x161b22, 1);
    legGfx.fillRoundedRect(cardX, cardTop, cardW, cardH, 4);
    legGfx.lineStyle(1, 0x30363d, 1);
    legGfx.strokeRoundedRect(cardX, cardTop, cardW, cardH, 4);

    var legX    = cardX + 8;
    var legLH   = 13;
    var lY      = cardTop + 7;

    this.add.text(legX, lY, 'SATIATION', {
      fontFamily: 'monospace', fontSize: '7px', color: '#484f58', fontStyle: 'bold',
    });
    lY += 11;
    var zoneRows = [
      ['#2ea043', 0x2ea043, 'critical_superavit'],
      ['#3fb950', 0x3fb950, 'high_superavit'],
      ['#56d364', 0x56d364, 'moderate_superavit'],
      ['#58a6ff', 0x58a6ff, 'equilibrium'],
      ['#d29922', 0xd29922, 'moderate_deficit'],
      ['#e36209', 0xe36209, 'high_deficit'],
      ['#f85149', 0xf85149, 'critical_deficit'],
    ];
    zoneRows.forEach(function(row) {
      legGfx.fillStyle(row[1], 1);
      legGfx.fillCircle(legX + 4, lY + 5, 4);
      this.add.text(legX + 13, lY, row[2], {
        fontFamily: 'monospace', fontSize: '9px', color: row[0],
      });
      lY += legLH;
    }, this);

    lY += 4;
    this.add.text(legX, lY, 'AGENT STATUS', {
      fontFamily: 'monospace', fontSize: '7px', color: '#484f58', fontStyle: 'bold',
    });
    lY += 11;
    var statusRows = [
      [0x3fb950, '#3fb950', '● active (glow)'],
      [0x3fb950, '#58a6ff', '⚡ working (flash)'],
      [0x484f58, '#484f58', '● suspended'],
      [0xf85149, '#f85149', '● error'],
    ];
    statusRows.forEach(function(row) {
      legGfx.fillStyle(row[0], 0.9);
      legGfx.fillCircle(legX + 4, lY + 5, 4);
      this.add.text(legX + 13, lY, row[2], {
        fontFamily: 'monospace', fontSize: '8px', color: row[1],
      });
      lY += legLH;
    }, this);

    lY += 4;
    this.add.text(legX, lY, 'REGULATION SWITCH', {
      fontFamily: 'monospace', fontSize: '7px', color: '#484f58', fontStyle: 'bold',
    });
    lY += 11;
    this.add.text(legX, lY, '● ON  = regulated agent', {
      fontFamily: 'monospace', fontSize: '8px', color: '#3fb950',
    });
    lY += legLH;
    this.add.text(legX, lY, '○ OFF = unregulated (ablation)', {
      fontFamily: 'monospace', fontSize: '8px', color: '#f85149',
    });

    // Human speech bubble — ABOVE sprite (tail points DOWN at sprite head)
    // Bubble body sits above the sprite; tail hangs down toward sprite top.
    this._humanBubble = {
      gfx:  this.add.graphics().setAlpha(0),
      text: this.add.text(hcx, hb.y + 10, '', {
        fontFamily: 'monospace', fontSize: '10px', color: '#e6edf3', align: 'center',
        wordWrap: { width: hb.w - 24, useAdvancedWrap: true },
        maxLines: 3,
      }).setOrigin(0.5, 0).setAlpha(0),
      hideAt: 0,
      spriteTopY: hSpriteCY - SPRITE_H / 2,
    };

    // ── Agent panels (indices 1..n-1) ──
    var HEX_R = 10;

    this._panelObjs = agents.map(function(ag, i) {
      var b        = this._panelBounds[i + 1];
      var cx       = b.x + Math.floor(b.w / 2);
      var y        = b.y;
      var hairTint = HAIR_TINTS[i % HAIR_TINTS.length];

      // ── Vertical layout ──────────────────────────────────────────────────────
      // y+6:    TOP STRIP — status dot (left) · hex viability (center) · REG switch (right)
      // y+37:   NAMETAG CHIP — above sprite head (sprite top = y+SPRITE_TOP=54)
      // y+54:   Sprite starts; sprite center at y+54+64=y+118
      // y+188:  Stats start (S = y + STATS_BASE_OFFSET)
      var spriteCY = y + SPRITE_TOP + Math.floor(SPRITE_H / 2);
      var S = y + STATS_BASE_OFFSET;

      // Row positions (absolute y)
      var R_action    = S;
      var R_satLbl    = S + 13;
      var R_driveBar  = S + 23;
      var R_zoneLbl   = S + 34;
      var R_zoneBars  = S + 44;
      var R_queue     = S + 57;
      var R_telHdr    = S + 69;
      var R_telLogo   = S + 79;
      var R_telTok    = S + 94;
      var R_telLat    = S + 104;
      var R_sessHdr   = S + 116;
      var R_sessCalls = S + 126;
      var R_sessTok   = S + 136;
      var R_sessCost  = S + 146;
      var R_sessAvg   = S + 156;
      var R_ctxRow    = S + 168;
      var R_kanbanHdr = S + 190;   // board divider
      var R_kanbanRow = S + 212;   // chips START below header text (which is at +10)
      var R_cons      = S + 262;

      // ── Sprites ──
      var walkLayers = this._makeLayers(cx, spriteCY, 'walk', hairTint);
      this._playLayers(walkLayers, 'walk', 'south');
      var castLayers = this._makeLayers(cx, spriteCY, 'cast', hairTint);
      this._hideLayers(castLayers);
      var hurtLayers = this._makeHurtLayers(cx, spriteCY, hairTint);
      this._hideLayers(hurtLayers);

      // Floating Z (sleep)
      var zText = this.add.text(cx + Math.floor(SPRITE_W / 2) + 4, spriteCY - 16, 'z  z  z', {
        fontFamily: 'monospace', fontSize: '11px', color: '#a5d6ff', fontStyle: 'bold',
      }).setOrigin(0, 0.5).setAlpha(0);

      // ── TOP STRIP: status dot (left) · hex viability (center) · switch (right) ──
      var dotX = b.x + 12, dotY = y + 14;
      var dotHalo = this.add.circle(dotX, dotY, 7, 0x3fb950, 0.15);
      var dotCore = this.add.circle(dotX, dotY, 4, 0x3fb950, 0.90);

      // Hex — CENTERED in header strip (replaces the old top-left position)
      var hexGfx = this.add.graphics().setPosition(cx, y + 14);
      this.tweens.add({ targets: hexGfx, scaleX: { from: 1, to: -1 }, duration: 2200, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });

      // Switch top-right
      var SW_W = 32, SW_H = 14;
      var swX = b.x + b.w - SW_W - 6, swY = y + 7;
      var switchGfx = this.add.graphics();
      var switchHit = this.add.rectangle(swX + SW_W / 2, swY + SW_H / 2, SW_W + 14, SW_H + 14)
        .setFillStyle(0x000000, 0).setInteractive({ useHandCursor: true });
      var nameRef = ag.name, aidRef = ag.aid;
      switchHit.on('pointerup', function() {
        var aid = (window._agentAidMap && window._agentAidMap[nameRef]) || aidRef;
        window.send({ cmd: 'toggle_ablation_agent', aid: aid });
      });
      var switchLabel = this.add.text(swX - 3, swY + Math.floor(SW_H / 2), 'REG', {
        fontFamily: 'monospace', fontSize: '7px', color: '#3fb950',
      }).setOrigin(1, 0.5);

      // ── NAMETAG CHIP (above sprite head) ──
      var nametag = this.add.graphics();
      var nametxt = this.add.text(cx, y + 37, ag.name, {
        fontFamily: 'monospace', fontSize: '11px', color: '#e6edf3', fontStyle: 'bold',
      }).setOrigin(0.5, 0.5);
      // Draw chip background (done once; chip width = text width + 12)
      var ntw = Math.max(nametxt.width + 12, 60);
      nametag.fillStyle(0x21262d, 0.92);
      nametag.fillRoundedRect(cx - ntw / 2, y + 29, ntw, 16, 4);
      nametag.lineStyle(1, 0x30363d, 1);
      nametag.strokeRoundedRect(cx - ntw / 2, y + 29, ntw, 16, 4);

      // ── Params label (λ, T, mode) — small line under nametag ──
      var paramsText = this.add.text(cx, y + 47, '', {
        fontFamily: 'monospace', fontSize: '7px', color: '#8b949e',
      }).setOrigin(0.5, 0.5);

      // ── Action kind (below sprite) ──
      var actionText = this.add.text(cx, R_action, '· idle', {
        fontFamily: 'monospace', fontSize: '10px', color: '#58a6ff',
      }).setOrigin(0.5, 0);

      // ── REGULATION SECTION: satiation label + drive bar + zone memberships ──
      this.add.text(b.x + 8, R_satLbl, 'satiation state:', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      var deltaText = this.add.text(b.x + b.w - 8, R_satLbl, '0.300', {
        fontFamily: 'monospace', fontSize: '8px', color: '#a8d8a8',
      }).setOrigin(1, 0);
      var barGfx = this.add.graphics();

      this.add.text(b.x + 8, R_zoneLbl, 'zone memberships:', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      var memberGfx = this.add.graphics();
      var ZONE_ABBR = ['over', 'sat', 'nom', 'load', 'crit'];
      var ZONE_ABBR_CLR = ['#58a6ff', '#7ee787', '#a8d8a8', '#ffa657', '#f85149'];
      var zoneInitLabels = ZONE_ABBR.map(function(label, zi) {
        var zw = Math.floor((b.w - 20) / 5) - 1;
        var zx = b.x + 10 + zi * (zw + 1) + Math.floor(zw / 2);
        return this.add.text(zx, R_zoneBars + 7, label, {
          fontFamily: 'monospace', fontSize: '6px', color: ZONE_ABBR_CLR[zi],
        }).setOrigin(0.5, 0);
      }, this);

      // ── Queue ──
      var queueText = this.add.text(b.x + 8, R_queue, 'queue: 0', {
        fontFamily: 'monospace', fontSize: '9px', color: '#8b949e',
      }).setOrigin(0, 0);

      // ── LAST INFERENCE section ──
      this.add.text(b.x + 8, R_telHdr, '─── last inference', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      // DS logo scaled to 14px height
      var dsLogo = this.add.image(b.x + 8, R_telLogo + 7, 'logo_deepseek')
        .setOrigin(0, 0.5).setAlpha(0);
      if (this.textures.exists('logo_deepseek')) {
        var src = this.textures.get('logo_deepseek').getSourceImage();
        dsLogo.setScale(14 / Math.max(src.height || 14, 1)).setAlpha(1);
      }
      var telemModel = this.add.text(b.x + 28, R_telLogo + 7, '—', {
        fontFamily: 'monospace', fontSize: '9px', color: '#484f58',
      }).setOrigin(0, 0.5);
      var terseBadge = this.add.text(b.x + b.w - 6, R_telLogo + 7, 'TERSE', {
        fontFamily: 'monospace', fontSize: '7px', color: '#ffa657', fontStyle: 'bold',
      }).setOrigin(1, 0.5).setAlpha(0);
      var telemTokCost = this.add.text(b.x + 8, R_telTok, 'tokens: —   cost: —', {
        fontFamily: 'monospace', fontSize: '8px', color: '#484f58',
      }).setOrigin(0, 0);
      var telemLat = this.add.text(b.x + 8, R_telLat, 'latency: —', {
        fontFamily: 'monospace', fontSize: '8px', color: '#484f58',
      }).setOrigin(0, 0);

      // ── SESSION TOTALS section ──
      this.add.text(b.x + 8, R_sessHdr, '─── session totals (since t=0)', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      var sessCallsText = this.add.text(b.x + 8, R_sessCalls, 'calls: 0   deferred: 0', {
        fontFamily: 'monospace', fontSize: '8px', color: '#8b949e',
      }).setOrigin(0, 0);
      var sessTokText = this.add.text(b.x + 8, R_sessTok, 'tokens used: 0', {
        fontFamily: 'monospace', fontSize: '8px', color: '#8b949e',
      }).setOrigin(0, 0);
      var sessCostText = this.add.text(b.x + 8, R_sessCost, 'cost spent: $0.000000', {
        fontFamily: 'monospace', fontSize: '8px', color: '#8b949e',
      }).setOrigin(0, 0);
      var sessAvgText = this.add.text(b.x + 8, R_sessAvg, 'avg/call: — tok  $—', {
        fontFamily: 'monospace', fontSize: '8px', color: '#484f58',
      }).setOrigin(0, 0);

      // ── CONTEXT WINDOW — inline donut right + text left ──
      // "─── context window" header on left; donut drawn each tick top-right of row
      this.add.text(b.x + 8, R_ctxRow, '─── context window', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      var ctxText = this.add.text(b.x + 8, R_ctxRow + 11, '0 / 8k tok  (0%)', {
        fontFamily: 'monospace', fontSize: '8px', color: '#484f58',
      }).setOrigin(0, 0);
      var donutGfx = this.add.graphics();
      var donutCX = b.x + b.w - 12, donutCY = R_ctxRow + 13;
      this.add.text(b.x + b.w - 24, R_ctxRow, 'CTX%', {
        fontFamily: 'monospace', fontSize: '6px', color: '#484f58',
      }).setOrigin(1, 0);

      // ── KANBAN section ──
      this.add.text(b.x + 8, R_kanbanHdr, '─── board', {
        fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
      }).setOrigin(0, 0);
      var colWk     = Math.floor((b.w - 12) / 3);
      var hdrlabels = ['TO DO (0)', 'DOING', 'DONE'];
      var hdrColors = ['#8b949e', '#3fb950', '#58a6ff'];
      var kanbanHdrs = hdrlabels.map(function(lbl, ki) {
        return this.add.text(b.x + 6 + ki * colWk, R_kanbanHdr + 10, lbl, {
          fontFamily: 'monospace', fontSize: '7px', color: hdrColors[ki], fontStyle: 'bold',
        }).setOrigin(0, 0);
      }, this);
      var kanbanChipGfx = this.add.graphics();
      var kanbanTexts = [];
      for (var ki = 0; ki < 3; ki++) {
        var colChips = [];
        for (var ci = 0; ci < 3; ci++) {
          colChips.push(this.add.text(
            b.x + 6 + ki * colWk + 3,
            R_kanbanRow + ci * 15,
            '', { fontFamily: 'monospace', fontSize: '8px', color: hdrColors[ki] }
          ).setOrigin(0, 0));
        }
        kanbanTexts.push(colChips);
      }

      // ── CONSOLIDATION SUMMARY ──
      var consText = this.add.text(b.x + 8, R_cons, '', {
        fontFamily: 'monospace', fontSize: '8px', color: '#a5d6ff',
        wordWrap: { width: b.w - 16 },
      }).setOrigin(0, 0).setAlpha(0);

      // ── LLM bubble: between nametag chip and sprite top ──
      // SPRITE_TOP = 54; nametag at y+37; bubble sits at y+46 (midpoint)
      var bubbleCY = y + SPRITE_TOP - 8;
      var llmBubbleGfx  = this.add.graphics().setAlpha(0);
      var llmBubbleText = this.add.text(cx, bubbleCY, '', {
        fontFamily: 'monospace', fontSize: '9px', color: '#e6edf3', align: 'center',
        wordWrap: { width: b.w - 32 },
      }).setOrigin(0.5, 0.5).setAlpha(0);

      this._sparks[ag.aid]     = new Array(SPARKLINE_LEN).fill(0.30);
      this._costSparks[ag.aid]  = new Array(SPARKLINE_LEN).fill(0);
      this._ctxSparks[ag.aid]   = new Array(SPARKLINE_LEN).fill(0);

      return {
        b, cx, spriteCY,
        llmBubbleY: bubbleCY,
        llmBubbleW: b.w - 32,
        llmBubbleX: b.x + 16,
        walkLayers, castLayers, hurtLayers,
        activeLayerSet: 'walk',
        hairTint,
        zText, paramsText,
        dotCore, dotHalo, dotTween: null, lastDotState: '',
        hexGfx, hexR: HEX_R,
        switchGfx, swX, swY, SW_W, SW_H, switchLabel,
        actionText,
        deltaText, barGfx,
        memberGfx, zoneInitLabels,
        queueText,
        dsLogo, telemModel, terseBadge, telemTokCost, telemLat,
        sessCallsText, sessTokText, sessCostText, sessAvgText,
        ctxText, donutGfx, donutCX, donutCY,
        kanbanHdrs, kanbanChipGfx, kanbanTexts,
        consText,
        llmBubbleGfx, llmBubbleText,
        lastZone: 'nominal',
        R_driveBar, R_zoneBars, R_kanbanRow,
      };
    }, this);

    this._panelsBuilt = true;
  }

  // ── Layer helpers ───────────────────────────────────────────────────────────

  _makeLayers(cx, cy, prefix, hairTint) {
    var keys = [prefix + '_body', prefix + '_shirt', prefix + '_pants', prefix + '_shoes', prefix + '_hair'];
    return keys.map(function(k, idx) {
      var s = this.add.sprite(cx, cy, k).setScale(LAYER_SCALE);
      if (idx === 4) s.setTint(hairTint);  // hair layer
      return s;
    }, this);
  }

  _makeHurtLayers(cx, cy, hairTint) {
    var keys = ['hurt_body', 'hurt_shirt', 'hurt_pants', 'hurt_hair'];
    return keys.map(function(k, idx) {
      var s = this.add.sprite(cx, cy, k).setScale(LAYER_SCALE).setVisible(false);
      if (idx === 3) s.setTint(hairTint);
      return s;
    }, this);
  }

  _playLayers(layers, prefix, suffix) {
    var keys = [prefix + '_body', prefix + '_shirt', prefix + '_pants', prefix + '_shoes', prefix + '_hair'];
    layers.forEach(function(s, i) {
      s.setVisible(true).play(keys[i] + '_' + suffix);
    });
  }

  _hideLayers(layers) {
    layers.forEach(function(s) { s.setVisible(false).stop(); });
  }

  _setLayersTint(layers, tint) {
    layers.forEach(function(s) { s.setTint(tint); });
  }

  _setLayersY(layers, y) {
    layers.forEach(function(s) { s.setY(y); });
  }

  // ── Frame handler ────────────────────────────────────────────────────────────

  onFrame(frame) {
    this._tick          = frame.tick;
    this._totalDemands += frame.demands.length;
    this._topText.setText('Binsai MVP1  —  Inbox bajo presión  |  tick ' + frame.tick);
    this._demandText.setText('demands: ' + this._totalDemands);

    if (!this._panelsBuilt && frame.agents.length > 0) {
      if (this._waitText) { this._waitText.destroy(); this._waitText = null; }
      this._buildPanels(frame.agents);
    }

    var self = this;
    for (var ei = 0; ei < frame.events.length; ei++) {
      var ev = frame.events[ei];
      var t = ev.type, p = ev.payload || {};
      if (t === 'lifecycle') {
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ': ' + p.event + (p.cause ? ' — ' + p.cause : ''), p.event === 'critical' ? 'critical' : 'lifecycle');
      } else if (t === 'action.complete' && p.result) {
        var pidx = frame.agents.findIndex(function(a) { return a.name === p.agent; });
        if (pidx >= 0) self._showLLMBubble(pidx, p.action, p.result);
        if (p.action === 'proact') {
          window.appendLog('[t' + frame.tick + '] ' + p.agent + ': proact ✨ ' + (p.result.inform || '').slice(0, 50), 'proact');
        } else {
          window.appendLog('[t' + frame.tick + '] ' + p.agent + ': ' + p.action + ' — "' + (p.result.response || '').slice(0, 45) + '"', 'action');
        }
        if (p.action === 'defer') {
          if (!self._kpi) self._kpi = { tokens: 0, costUsd: 0, calls: 0, savedCalls: 0 };
          self._kpi.savedCalls++;
        }
      } else if (t === 'sleep.cycle.completed') {
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ': woke up (δ=' + p.delta + ')', 'sleep');
      } else if (t === 'appraisal') {
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ' appraised "' + p.topic + '" → ' + p.kind + ' (' + p.difficulty + ') $' + (p.cost_usd || 0).toFixed(5), 'action');
      } else if (t === 'proact.inform') {
        var pidx2 = frame.agents.findIndex(function(a) { return a.name === p.agent; });
        if (pidx2 >= 0) self._flyEnvelopeToHuman(pidx2, p.message || '');
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ' → human [INFORM] ' + (p.message || '').slice(0, 55), 'proact');
      } else if (t === 'proact.rejected') {
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ' proact REJECTED: ' + (p.reason || '').slice(0, 60), 'lifecycle');
      } else if (t === 'consolidation.summary') {
        window.appendLog('[t' + frame.tick + '] ' + p.agent + ' 💤 consolidated ' + p.n_compressed + ' items → "' + (p.summary || '').slice(0, 40) + '"', 'sleep');
      }
    }

    this._demandsSent += frame.demands.length;
    if (this._humanDemandText) this._humanDemandText.setText('sent: ' + this._demandsSent);

    // Show human's outgoing message as a speech bubble; envelope flies to target
    for (var di = 0; di < frame.demands.length; di++) {
      var d  = frame.demands[di];
      var ti = frame.agents.findIndex(function(a) { return a.aid === d.target_aid; });
      if (ti >= 0) this._flyEnvelope(ti);
      this._showHumanBubble(d.message || d.topic);
      window.appendLog('[t' + frame.tick + '] human → ' + d.target_name + ': ' + d.performative + ' "' + (d.message || d.topic) + '"', 'demand');
    }

    // Telemetry events → log + per-agent overlay
    for (var ei2 = 0; ei2 < frame.events.length; ei2++) {
      var ev2 = frame.events[ei2];
      if (ev2.type === 'telemetry') {
        var pl = ev2.payload || {};
        window.appendLog(
          '[t' + frame.tick + '] ' + pl.agent + ' · ' + pl.tier + ' [' + pl.model + ']  $' +
          (pl.cost_usd).toFixed(5) + '  ' + pl.latency_ms + 'ms  ' +
          (pl.prompt_tokens + pl.completion_tokens) + 'tok  +δ ' + pl.delta_increment,
          'action'
        );
        // KPI accumulation
        if (!self._kpi) self._kpi = { tokens: 0, costUsd: 0, calls: 0, savedCalls: 0 };
        self._kpi.tokens  += (pl.prompt_tokens + pl.completion_tokens) || 0;
        self._kpi.costUsd += pl.cost_usd || 0;
        self._kpi.calls   += 1;
      }
    }

    // Fade out human bubble after its lifetime
    if (this._humanBubble && this._humanBubble.hideAt && frame.tick >= this._humanBubble.hideAt) {
      this._humanBubble.gfx.setAlpha(0);
      this._humanBubble.text.setAlpha(0);
      this._humanBubble.hideAt = 0;
    }

    if (this._panelsBuilt) {
      frame.agents.forEach(function(ag, i) { this._updatePanel(i, ag, frame.tick); }, this);
      this._drawSparklines(frame.agents);
      this._drawCostSparklines(frame.agents);
      this._drawDivergenceChart();
    }
  }

  // ── Panel update ─────────────────────────────────────────────────────────────

  _updatePanel(i, ag, tick) {
    if (i >= this._panelObjs.length) return;
    var obj        = this._panelObjs[i];
    var b          = obj.b;
    var delta      = ag.delta  != null ? ag.delta  : 0.30;
    var zone       = ag.zone   || 'nominal';
    var status     = ag.status || 'active';
    var action     = ag.action || 'idle';
    var members    = ag.memberships || {};
    var isAblated  = !!ag.ablation_off;
    var isSleeping = status === 'suspended';
    var isWorking  = !isSleeping && action !== 'idle';

    // Sparkline data
    var spark = this._sparks[ag.aid];
    if (spark) { spark.shift(); spark.push(delta); }
    // API cost and context usage sparklines
    var costSpark = this._costSparks[ag.aid];
    if (costSpark) { costSpark.shift(); costSpark.push(ag.session_cost_usd || 0); }
    var ctxSpark = this._ctxSparks[ag.aid];
    if (ctxSpark) { ctxSpark.shift(); ctxSpark.push(ag.context_used_tokens || 0); }
    // Cumulative tokens for divergence chart
    if (!this._cumTokens) this._cumTokens = {};
    if (!this._cumTokens[ag.aid]) this._cumTokens[ag.aid] = [];
    var cumArr = this._cumTokens[ag.aid];
    cumArr.push({ tick: tick, tokens: ag.session_tokens, regulated: !isAblated });

    // Aid map for switch
    if (!window._agentAidMap) window._agentAidMap = {};
    window._agentAidMap[ag.name] = ag.aid;

    // ── PARAMS label (λ, T, regulated/ablated) ──
    if (obj.paramsText) {
      var lam = (ag.lambda_rate !== null && ag.lambda_rate !== undefined) ? ag.lambda_rate : 0;
      var tmp = (ag.temperature !== null && ag.temperature !== undefined) ? ag.temperature : 1.0;
      obj.paramsText.setText(
        'λ=' + lam.toFixed(3) + '  T=' + tmp.toFixed(1) + (isAblated ? '  [UNREG]' : '')
      );
    }

    // ── STATUS DOT (top-left) — tween rebuilt only on state change ───────────────
    this._refreshStatusDot(obj, status, action);

    // ── HEX VIABILITY (centered) ──────────────────────────────────────────────
    drawHexagonCentered(obj.hexGfx, obj.hexR,
      isAblated ? 0x30363d : zoneToSemaphore(zone),
      isAblated ? 0x21262d : undefined);

    // ── SWITCH ────────────────────────────────────────────────────────────────
    this._drawSwitch(obj.switchGfx, obj.swX, obj.swY, obj.SW_W, obj.SW_H, !isAblated);
    obj.switchLabel.setText(isAblated ? 'UNREG' : 'REG')
      .setStyle({ color: isAblated ? '#f85149' : '#3fb950' });

    // ── SPRITE ────────────────────────────────────────────────────────────────
    if (isSleeping) {
      if (obj.activeLayerSet !== 'hurt') {
        this._hideLayers(obj.walkLayers);
        this._hideLayers(obj.castLayers);
        obj.hurtLayers.forEach(function(s, idx) {
          s.setVisible(true);
          s.play((['hurt_body','hurt_shirt','hurt_pants','hurt_hair'][idx]) + '_fall');
        });
        obj.activeLayerSet = 'hurt';
      }
      this._setLayersTint(obj.hurtLayers, 0x8ab0cc);
      var zA = 0.5 + 0.4 * Math.sin(tick * 0.18);
      var zD = -6 * ((tick % 30) / 30);
      obj.zText.setAlpha(zA).setY(obj.spriteCY - 20 + zD);
    } else {
      obj.zText.setAlpha(0);
      var useCast = (action === 'respond_fast' || action === 'respond_slow' || action === 'proact');
      var targetSet = useCast ? 'cast' : 'walk';
      if (obj.activeLayerSet !== targetSet) {
        if (targetSet === 'cast') { this._hideLayers(obj.walkLayers); this._hideLayers(obj.hurtLayers); this._playLayers(obj.castLayers, 'cast', 'south'); }
        else                     { this._hideLayers(obj.castLayers); this._hideLayers(obj.hurtLayers); this._playLayers(obj.walkLayers, 'walk', 'south'); }
        obj.activeLayerSet = targetSet;
      }
      var bodyTint = 0xffffff;
      if (!isAblated) {
        if (zone === 'critical_deficit')    bodyTint = 0xffbbbb;
        else if (zone === 'high_deficit')   bodyTint = 0xffddcc;
        else if (zone === 'critical_superavit') bodyTint = 0xbbddff;
      }
      var activeLayers = useCast ? obj.castLayers : obj.walkLayers;
      activeLayers.forEach(function(s, idx) { s.setTint(idx === activeLayers.length - 1 ? obj.hairTint : bodyTint); });
      this._setLayersY(activeLayers, obj.spriteCY + (action === 'idle' ? this._bobOffset : 0));
    }

    // ── ACTION KIND below sprite ───────────────────────────────────────────────
    var AICON = { respond_fast:'⚡ fast reply', respond_slow:'🧠 slow reply', defer:'📥 defer', proact:'✨ proact', idle:'· idle', sleep:'💤 sleeping' };
    obj.actionText.setText(AICON[action] || action)
      .setStyle({ color: isSleeping ? '#a5d6ff' : (isAblated ? '#8b949e' : (isWorking ? '#58a6ff' : '#484f58')) });

    // ── REGULATION SECTION — hidden when ablated ───────────────────────────────
    var showReg = !isAblated;
    obj.deltaText.setVisible(showReg);
    obj.barGfx.setVisible(showReg);
    obj.memberGfx.setVisible(showReg);
    obj.zoneInitLabels.forEach(function(t) { t.setVisible(showReg); });

    if (showReg) {
      obj.deltaText.setText(delta.toFixed(3)).setStyle({ color: ZONE_COLOR_CSS[zone] || '#a8d8a8' });
      this._drawDeltaBar(obj.barGfx, b.x, obj.R_driveBar, b.w, delta, zone);
      this._drawMemberships(obj.memberGfx, b.x, obj.R_zoneBars, b.w, members);
    } else {
      obj.barGfx.clear();
      obj.memberGfx.clear();
    }

    // ── QUEUE ─────────────────────────────────────────────────────────────────
    var ql = 'queue: ' + ag.queue;
    if (isSleeping && ag.buffered > 0) ql += '  buffered: ' + ag.buffered;
    obj.queueText.setText(ql)
      .setStyle({ color: ag.queue > 3 ? '#f85149' : (ag.queue > 0 ? '#ffa657' : '#8b949e') });

    // ── LAST INFERENCE ────────────────────────────────────────────────────────
    if (ag.last_model) {
      var TIER_COLOR = { weak: '#8b949e', main: '#58a6ff', strong: '#d2a8ff' };
      var mn = ag.last_model || '';
      var modelDisplay = mn.replace(/-thinking$/, '') + (mn.includes('thinking') ? ' 🧠' : '');
      obj.telemModel.setText(modelDisplay)
        .setStyle({ color: TIER_COLOR[ag.last_tier || 'main'] || '#8b949e' });
      if (obj.dsLogo.alpha < 0.5 && this.textures.exists('logo_deepseek')) {
        var srcImg = this.textures.get('logo_deepseek').getSourceImage();
        obj.dsLogo.setScale(14 / Math.max(srcImg.height || 14, 1)).setAlpha(1);
        obj.telemModel.setX(obj.dsLogo.x + obj.dsLogo.displayWidth + 4);
      }
      var tokStr  = ag.last_tokens     != null ? ag.last_tokens.toLocaleString()   : '—';
      var costStr = ag.last_cost_usd   != null ? '$' + ag.last_cost_usd.toFixed(5) : '—';
      var latStr  = ag.last_latency_ms != null ? ag.last_latency_ms + ' ms'        : '—';
      obj.telemTokCost.setText('tokens: ' + tokStr + '   cost: ' + costStr);
      obj.telemLat.setText('latency: ' + latStr);
      obj.terseBadge.setAlpha(ag.pressure_mode ? 1 : 0);
    }

    // ── SESSION TOTALS ────────────────────────────────────────────────────────
    var sc    = ag.session_calls    || 0;
    var st    = ag.session_tokens   || 0;
    var scost = ag.session_cost_usd || 0;
    var sd    = ag.session_deferred || 0;
    var sessColor = isAblated ? '#f85149' : '#7ee787';
    obj.sessCallsText.setText('calls: ' + sc + '   deferred: ' + sd).setStyle({ color: '#8b949e' });
    obj.sessTokText.setText('tokens used: ' + st.toLocaleString()).setStyle({ color: sessColor });
    obj.sessCostText.setText('cost spent: $' + scost.toFixed(5)).setStyle({ color: sessColor });
    var avgTok  = sc > 0 ? Math.round(st / sc) : 0;
    var avgCost = sc > 0 ? (scost / sc).toFixed(5) : '—';
    obj.sessAvgText.setText(sc > 0 ? 'avg/call: ' + avgTok + ' tok  $' + avgCost : 'avg/call: —').setStyle({ color: '#484f58' });

    // ── CONTEXT WINDOW DONUT ──────────────────────────────────────────────────
    var ctxUsed   = ag.context_used_tokens   || 0;
    var ctxBudget = ag.context_budget_tokens || 8000;
    var ctxPct    = ctxBudget > 0 ? Math.round((ctxUsed / ctxBudget) * 100) : 0;
    var ctxColor  = ctxPct > 80 ? '#f85149' : (ctxPct > 40 ? '#ffa657' : '#484f58');
    var kStr      = ctxBudget >= 1000 ? Math.round(ctxBudget / 1000) + 'k' : String(ctxBudget);
    var uStr      = ctxUsed >= 1000   ? (ctxUsed / 1000).toFixed(1) + 'k'  : String(ctxUsed);
    obj.ctxText.setText(uStr + ' / ' + kStr + ' tok  (' + ctxPct + '%)').setStyle({ color: ctxColor });
    this._drawDonut(obj.donutGfx, obj.donutCX, obj.donutCY, 7, 3, ctxUsed / ctxBudget, ctxPct);

    // ── KANBAN BOARD ──────────────────────────────────────────────────────────
    var pendingTasks = ag.pending_task_labels || [];
    var doneTasks    = ag.done_task_labels    || [];
    var curTask      = ag.current_task_label  || null;
    // To Do: up to 3 pending tasks
    var todoItems  = pendingTasks.slice(0, 3).map(function(t) { return t.length > 14 ? t.slice(0,13) + '…' : t; });
    // Doing: current task (1 slot)
    var doingItems = curTask ? [curTask.length > 14 ? curTask.slice(0,13) + '…' : curTask] : [];
    // Done: last 3 done (most-recent = last in array)
    var doneItems  = doneTasks.slice(-3).reverse().map(function(t) { return t.length > 14 ? t.slice(0,13) + '…' : t; });

    var colItems   = [todoItems, doingItems, doneItems];
    var colFill    = [0x21262d, 0x0d2014, 0x0d1a2e];   // To Do / Doing / Done bg
    var colBorder  = [0x30363d, 0x1a7f37, 0x1a4a7f];
    var colTextClr = ['#8b949e', '#3fb950', '#58a6ff'];
    var colW       = Math.floor((b.w - 12) / 3);

    obj.kanbanChipGfx.clear();
    colItems.forEach(function(items, ki) {
      var cx2   = b.x + 6 + ki * colW;
      var chipW = colW - 4;
      items.forEach(function(lbl, ci) {
        var cy2 = obj.R_kanbanRow + ci * 15;
        obj.kanbanChipGfx.fillStyle(colFill[ki], 1);
        obj.kanbanChipGfx.fillRoundedRect(cx2, cy2, chipW, 13, 2);
        obj.kanbanChipGfx.lineStyle(1, colBorder[ki], 0.8);
        obj.kanbanChipGfx.strokeRoundedRect(cx2, cy2, chipW, 13, 2);
        if (obj.kanbanTexts[ki] && obj.kanbanTexts[ki][ci]) {
          obj.kanbanTexts[ki][ci].setText(lbl).setStyle({ color: colTextClr[ki] })
            .setPosition(cx2 + 3, cy2 + 2);
        }
      });
      for (var ci = items.length; ci < 3; ci++) {
        if (obj.kanbanTexts[ki] && obj.kanbanTexts[ki][ci]) {
          obj.kanbanTexts[ki][ci].setText('');
        }
      }
    }, this);

    // Update column header counts
    if (obj.kanbanHdrs && obj.kanbanHdrs[0]) {
      obj.kanbanHdrs[0].setText('TO DO (' + todoItems.length + ')');
    }

    // ── CONSOLIDATION SUMMARY ─────────────────────────────────────────────────
    if (ag.consolidation_summary) {
      obj.consText.setText('💤 "' + ag.consolidation_summary.slice(0, 56) + '"').setAlpha(1);
      var consRef = obj.consText;
      this.time.delayedCall(6000, function() { if (consRef) consRef.setAlpha(0); });
    }

    obj.lastZone = zone;
  }

  // ── Status dot: Phaser-tween-based pulse ──────────────────────────────────────
  // Called once per tick from _updatePanel; tween is only rebuilt when dotState changes.

  _refreshStatusDot(obj, status, action) {
    var isWorking = action !== 'idle' && status !== 'suspended';
    var dotState;
    if (status === 'suspended')       dotState = 'suspended';
    else if (status === 'critical')   dotState = 'critical';
    else if (status === 'error')      dotState = 'error';
    else if (status === 'waiting')    dotState = 'waiting';
    else if (status === 'initiated')  dotState = 'initiated';
    else if (isWorking)               dotState = 'working';
    else                              dotState = 'active';

    if (dotState === obj.lastDotState) return;
    obj.lastDotState = dotState;

    // Kill previous tween
    if (obj.dotTween) { obj.dotTween.stop(); obj.dotTween = null; }

    // Color maps per state
    var colors = {
      active:    { c: 0x3fb950, hc: 0x3fb950 },
      initiated: { c: 0x3fb950, hc: 0x3fb950 },
      working:   { c: 0x3fb950, hc: 0x58a6ff },
      suspended: { c: 0x484f58, hc: 0x484f58 },
      critical:  { c: 0xf85149, hc: 0xf85149 },
      error:     { c: 0xf85149, hc: 0xf85149 },
      waiting:   { c: 0xd2a8ff, hc: 0xd2a8ff },
    };
    var col = colors[dotState] || colors.active;
    obj.dotCore.setFillStyle(col.c);
    obj.dotHalo.setFillStyle(col.hc);

    if (dotState === 'suspended') {
      // Static grey — no tween
      obj.dotCore.setAlpha(0.50); obj.dotHalo.setAlpha(0.08);
    } else if (dotState === 'error') {
      // Bright red solid — no tween
      obj.dotCore.setAlpha(1.0);  obj.dotHalo.setAlpha(0.40);
    } else if (dotState === 'working') {
      // Very fast strobe: 0.05 → 1.0, 280 ms — clearly visible
      obj.dotCore.setAlpha(0.05); obj.dotHalo.setAlpha(0.05);
      obj.dotTween = this.tweens.add({
        targets: [obj.dotCore, obj.dotHalo],
        alpha: { from: 0.05, to: 1.0 }, duration: 280, yoyo: true, repeat: -1,
        ease: 'Quad.easeInOut',
      });
    } else if (dotState === 'active') {
      // Wide-range slow breathe: 0.05 → 1.0, 1400 ms
      obj.dotCore.setAlpha(0.05); obj.dotHalo.setAlpha(0.05);
      obj.dotTween = this.tweens.add({
        targets: [obj.dotCore, obj.dotHalo],
        alpha: { from: 0.05, to: 1.0 }, duration: 1400, yoyo: true, repeat: -1,
        ease: 'Sine.easeInOut',
      });
    } else if (dotState === 'initiated') {
      // Very slow deep pulse: 0.05 → 0.85, 2200 ms
      obj.dotCore.setAlpha(0.05); obj.dotHalo.setAlpha(0.05);
      obj.dotTween = this.tweens.add({
        targets: [obj.dotCore, obj.dotHalo],
        alpha: { from: 0.05, to: 0.85 }, duration: 2200, yoyo: true, repeat: -1,
        ease: 'Sine.easeInOut',
      });
    } else if (dotState === 'critical') {
      // Fast red throb: 0.10 → 1.0, 600 ms
      obj.dotCore.setAlpha(0.10); obj.dotHalo.setAlpha(0.10);
      obj.dotTween = this.tweens.add({
        targets: [obj.dotCore, obj.dotHalo],
        alpha: { from: 0.10, to: 1.0 }, duration: 600, yoyo: true, repeat: -1,
        ease: 'Sine.easeInOut',
      });
    } else if (dotState === 'waiting') {
      // Medium flash: 0.05 → 1.0, 500 ms
      obj.dotCore.setAlpha(0.05); obj.dotHalo.setAlpha(0.05);
      obj.dotTween = this.tweens.add({
        targets: [obj.dotCore, obj.dotHalo],
        alpha: { from: 0.05, to: 1.0 }, duration: 500, yoyo: true, repeat: -1,
        ease: 'Quad.easeOut',
      });
    }
  }

  // ── Switch widget (track + sliding thumb) ─────────────────────────────────────

  _drawSwitch(gfx, x, y, w, h, isOn) {
    gfx.clear();
    var r = Math.floor(h / 2);
    // Track
    gfx.fillStyle(isOn ? 0x1a7f37 : 0x4a1515, 1);
    gfx.fillRoundedRect(x, y, w, h, r);
    // Thumb
    var thumbX = isOn ? (x + w - r - 1) : (x + r + 1);
    gfx.fillStyle(isOn ? 0x3fb950 : 0xf85149, 1);
    gfx.fillCircle(thumbX, y + r, r - 1);
  }

  // ── Context window donut gauge ────────────────────────────────────────────────
  // outerR = outer radius, thickness = ring thickness, ratio = [0,1], pct = integer %

  _drawDonut(gfx, cx, cy, outerR, thickness, ratio, pct) {
    gfx.clear();
    var fill  = Math.min(1, Math.max(0, ratio));
    var color = pct > 80 ? 0xf85149 : (pct > 40 ? 0xffa657 : 0x3fb950);
    // Background ring
    gfx.lineStyle(thickness, 0x30363d, 1);
    gfx.strokeCircle(cx, cy, outerR - thickness / 2);
    // Fill arc (clockwise from top)
    if (fill > 0.005) {
      gfx.lineStyle(thickness, color, 0.9);
      gfx.beginPath();
      gfx.arc(cx, cy, outerR - thickness / 2, -Math.PI / 2, -Math.PI / 2 + fill * 2 * Math.PI, false);
      gfx.strokePath();
    }
  }

  // ── Delta bar (barY = absolute y position) ───────────────────────────────────

  _drawDeltaBar(gfx, panelX, barY, panelW, delta, zone) {
    gfx.clear();
    var bx = panelX + 8, by = barY, bw = panelW - 16, bh = 8;
    var sp = 0.30, cx = bx + bw * sp;
    var color = ZONE_COLOR_HEX[zone] || 0xa8d8a8;
    gfx.fillStyle(0x21262d, 1); gfx.fillRect(bx, by, bw, bh);
    gfx.fillStyle(color, 0.85);
    if (delta >= sp) gfx.fillRect(cx, by, Math.min(bw * (delta - sp), bw * (1 - sp)), bh);
    else              gfx.fillRect(cx - bw * (sp - delta), by, bw * (sp - delta), bh);
    gfx.lineStyle(2, 0xffffff, 0.85); gfx.lineBetween(cx, by - 2, cx, by + bh + 2);
    gfx.lineStyle(1, 0x30363d, 1);    gfx.strokeRect(bx, by, bw, bh);
  }

  // ── Zone membership bars (barY = absolute y position) ────────────────────────

  _drawMemberships(gfx, panelX, barY, panelW, members) {
    gfx.clear();
    var zones = ['critical_superavit', 'high_superavit', 'moderate_superavit',
                  'equilibrium', 'moderate_deficit', 'high_deficit', 'critical_deficit'];
    var bx = panelX + 8, by = barY, bw = panelW - 16, bh = 5;
    var zw = Math.floor(bw / zones.length) - 1;
    zones.forEach(function(z, idx) {
      var m = members[z] || 0, zx = bx + idx * (zw + 1);
      gfx.fillStyle(0x21262d, 1); gfx.fillRect(zx, by, zw, bh);
      gfx.fillStyle(ZONE_COLOR_HEX[z] || 0x8b949e, 0.85);
      gfx.fillRect(zx, by + bh * (1 - m), zw, bh * m);
    });
  }

  // ── Sparklines — aligned to agent panel bounds, labeled per agent ────────────

  _drawSparklines(agents) {
    this._sparkGfx.clear();
    var self = this;

    // One-time headers per agent (drawn at sparkY, aligned to agent panel)
    if (!this._sparkHeaderBuilt && agents.length > 0) {
      this._sparkHeaderBuilt = true;
      agents.forEach(function(ag, i) {
        var pb = self._panelBounds[i + 1];
        if (!pb) return;
        self.add.text(pb.x + 6, self._sparkY + 4, ag.name + '  ·  metabolic drive δ(t)', {
          fontFamily: 'monospace', fontSize: '8px', color: '#484f58',
        });
        self.add.text(pb.x + 6, self._sparkY + 14, '— set-point δ=0.30', {
          fontFamily: 'monospace', fontSize: '7px', color: '#30363d',
        });
      });
    }

    // Draw sparkline for each agent inside its panel column
    agents.forEach(function(ag, i) {
      var pb    = self._panelBounds[i + 1];
      if (!pb) return;
      var spark = self._sparks[ag.aid] || [];
      var zone  = (self._panelObjs[i] && self._panelObjs[i].lastZone) || ag.zone || 'nominal';
      var isAbl = !!ag.ablation_off;

      // Use only the draw window (last N samples) for display
      var drawSamples = spark.slice(-SPARKLINE_DRAW_WINDOW);
      var nSamples = drawSamples.length;

      var sx = pb.x + 4, sy = self._sparkY + 24;
      var sw = pb.w - 8, sh = self._sparkH - 40;

      // Background
      self._sparkGfx.fillStyle(0x0d1117, 1);
      self._sparkGfx.fillRect(sx, sy, sw, sh);

      // ── Zone bands (shaded behind trajectory) ──
      var zoneDefs = [
        { name: 'critical_superavit',   y0: 0.00, y1: 0.09, color: 0x2ea043, alpha: 0.12 },
        { name: 'high_superavit',       y0: 0.09, y1: 0.17, color: 0x3fb950, alpha: 0.10 },
        { name: 'moderate_superavit',   y0: 0.17, y1: 0.26, color: 0x56d364, alpha: 0.08 },
        { name: 'equilibrium',          y0: 0.26, y1: 0.35, color: 0x58a6ff, alpha: 0.08 },
        { name: 'moderate_deficit',     y0: 0.35, y1: 0.48, color: 0xd29922, alpha: 0.10 },
        { name: 'high_deficit',         y0: 0.48, y1: 0.68, color: 0xe36209, alpha: 0.12 },
        { name: 'critical_deficit',     y0: 0.68, y1: 1.00, color: 0xf85149, alpha: 0.14 },
      ];
      zoneDefs.forEach(function(zd) {
        var zy = sy + sh * zd.y0;
        var zh = sh * (zd.y1 - zd.y0);
        self._sparkGfx.fillStyle(zd.color, zd.alpha);
        self._sparkGfx.fillRect(sx, zy, sw, zh);
      });

      // Set-point line at delta=0.30
      var setY = sy + sh * 0.30;
      self._sparkGfx.lineStyle(1, 0xffffff, 0.30);
      self._sparkGfx.lineBetween(sx, setY, sx + sw, setY);

      // Line graph
      if (nSamples >= 2) {
        var step  = sw / (nSamples - 1);
        var color = isAbl ? 0x484f58 : (ZONE_COLOR_HEX[zone] || 0x58a6ff);
        self._sparkGfx.lineStyle(2.0, color, 0.95);
        for (var j = 1; j < nSamples; j++) {
          self._sparkGfx.lineBetween(
            sx + (j-1)*step, sy + sh*Math.min(drawSamples[j-1],1),
            sx + j*step,     sy + sh*Math.min(drawSamples[j],1)
          );
        }
      }
      self._sparkGfx.lineStyle(1, 0x30363d, 1);
      self._sparkGfx.strokeRect(sx, sy, sw, sh);
    });

  }

  // ── API cost sparklines (per agent, below delta sparkline) ──────────────────

  _drawCostSparklines(agents) {
    var self = this;
    agents.forEach(function(ag, i) {
      var pb = self._panelBounds[i + 1];
      if (!pb) return;
      var costSpark = self._costSparks[ag.aid] || [];
      var ctxSpark  = self._ctxSparks[ag.aid] || [];
      var drawCost  = costSpark.slice(-SPARKLINE_DRAW_WINDOW);
      var drawCtx   = ctxSpark.slice(-SPARKLINE_DRAW_WINDOW);
      var nCost = drawCost.length, nCtx = drawCtx.length;

      var sx = pb.x + 4, sw = pb.w - 8;
      var sy = self._sparkY + 24 + (self._sparkH - 40) + 10;  // below delta sparkline
      var sh = 28;  // compact
      var budgetCost = 0.005;  // budget ceiling (hardcoded, configurable)

      // Background
      self._sparkGfx.fillStyle(0x0d1117, 1);
      self._sparkGfx.fillRect(sx, sy, sw, sh);

      // Budget ceiling line
      var ceilY = sy + sh * 0.20;
      self._sparkGfx.lineStyle(1, 0xf85149, 0.40);
      self._sparkGfx.lineBetween(sx, ceilY, sx + sw, ceilY);

      // Cost sparkline
      if (nCost >= 2) {
        var step = sw / (nCost - 1);
        var maxCost = budgetCost * 1.5;
        self._sparkGfx.lineStyle(1.5, 0xd29922, 0.9);
        for (var j = 1; j < nCost; j++) {
          self._sparkGfx.lineBetween(
            sx + (j-1)*step, sy + sh * (1 - Math.min(drawCost[j-1]/maxCost, 1)),
            sx + j*step,     sy + sh * (1 - Math.min(drawCost[j]/maxCost, 1))
          );
        }
      }

      // Context usage sparkline (below cost)
      var sy2 = sy + sh + 4;
      self._sparkGfx.fillStyle(0x0d1117, 1);
      self._sparkGfx.fillRect(sx, sy2, sw, sh);
      var ctxBudget = ag.context_budget_tokens || 8000;
      var ceilY2 = sy2 + sh * 0.20;
      self._sparkGfx.lineStyle(1, 0xf85149, 0.40);
      self._sparkGfx.lineBetween(sx, ceilY2, sx + sw, ceilY2);

      if (nCtx >= 2) {
        var step2 = sw / (nCtx - 1);
        self._sparkGfx.lineStyle(1.5, 0x58a6ff, 0.9);
        for (var k = 1; k < nCtx; k++) {
          self._sparkGfx.lineBetween(
            sx + (k-1)*step2, sy2 + sh * (1 - Math.min(drawCtx[k-1]/ctxBudget, 1)),
            sx + k*step2,     sy2 + sh * (1 - Math.min(drawCtx[k]/ctxBudget, 1))
          );
        }
      }
    });
  }

  // ── Divergence chart (regulated vs unregulated cumulative tokens) ────────────

  _drawDivergenceChart() {
    if (!this._cumTokens || !this._divGfx) return;
    this._divGfx.clear();
    var agents = Object.keys(this._cumTokens);
    if (agents.length < 2) return;

    // Collect cumulative series by regulation status
    var regSeries = [], unregSeries = [];
    var maxTick = 0, maxTokens = 0;
    var self = this;
    agents.forEach(function(aid) {
      var arr = self._cumTokens[aid];
      if (!arr || arr.length === 0) return;
      var last = arr[arr.length - 1];
      if (last.regulated) regSeries.push(arr);
      else unregSeries.push(arr);
      if (last.tick > maxTick) maxTick = last.tick;
      if (last.tokens > maxTokens) maxTokens = last.tokens;
    });
    if (regSeries.length === 0 || unregSeries.length === 0) return;

    // Position: draggable, defaults to bottom-right
    var W = self.scale.width, H = self.scale.height;
    if (self._divX === undefined) { self._divX = W - 290; self._divY = H - 100; }
    var dx = self._divX, dy = self._divY, dw = 280, dh = 70;

    // Background
    this._divGfx.fillStyle(0x0d1117, 0.92);
    this._divGfx.fillRoundedRect(dx, dy, dw, dh, 4);
    this._divGfx.lineStyle(1, 0x30363d, 1);
    this._divGfx.strokeRoundedRect(dx, dy, dw, dh, 4);

    // Title
    if (!this._divTitle) {
      this._divTitle = this.add.text(dx + 6, dy + 2, 'cumulative tokens: regulated vs unregulated', {
        fontFamily: 'monospace', fontSize: '7px', color: '#484f58',
      });
    } else {
      this._divTitle.setPosition(dx + 6, dy + 2);
    }

    // Draw lines
    maxTokens = Math.max(maxTokens, 1);
    var drawTicks = SPARKLINE_DRAW_WINDOW;

    // Regulated (green)
    regSeries.forEach(function(arr) {
      var draw = arr.slice(-drawTicks);
      if (draw.length < 2) return;
      var step = dw / (draw.length - 1);
      self._divGfx.lineStyle(2, 0x3fb950, 0.9);
      for (var j = 1; j < draw.length; j++) {
        self._divGfx.lineBetween(
          dx + (j-1)*step, dy + dh - 6 - (dh - 16) * Math.min(draw[j-1].tokens/maxTokens, 1),
          dx + j*step,     dy + dh - 6 - (dh - 16) * Math.min(draw[j].tokens/maxTokens, 1)
        );
      }
    });

    // Unregulated (red)
    unregSeries.forEach(function(arr) {
      var draw = arr.slice(-drawTicks);
      if (draw.length < 2) return;
      var step = dw / (draw.length - 1);
      self._divGfx.lineStyle(2, 0xf85149, 0.9);
      for (var j = 1; j < draw.length; j++) {
        self._divGfx.lineBetween(
          dx + (j-1)*step, dy + dh - 6 - (dh - 16) * Math.min(draw[j-1].tokens/maxTokens, 1),
          dx + j*step,     dy + dh - 6 - (dh - 16) * Math.min(draw[j].tokens/maxTokens, 1)
        );
      }
    });

    // Legend
    if (!this._divLegend) {
      this._divLegend = this.add.text(dx + 6, dy + dh - 12, 'green=regulated  red=unregulated', {
        fontFamily: 'monospace', fontSize: '7px', color: '#8b949e',
      });
    } else {
      this._divLegend.setPosition(dx + 6, dy + dh - 12);
    }

    // Draggable hit zone (invisible, covers the whole chart)
    if (!this._divDragZone) {
      this._divDragZone = this.add.zone(dx, dy, dw, dh)
        .setOrigin(0, 0)
        .setInteractive({ useHandCursor: true });
      this.input.setDraggable(this._divDragZone);
      var self2 = this;
      this.input.on('drag', function(pointer, gameObject, dragX, dragY) {
        if (gameObject === self2._divDragZone) {
          self2._divX = dragX;
          self2._divY = dragY;
        }
      });
    }
    this._divDragZone.setPosition(dx, dy);
  }

  // ── Human speech bubble (outgoing demand) ─────────────────────────────────────

  _showHumanBubble(message) {
    if (!this._humanBubble) return;
    var hb  = this._panelBounds[0];
    var hcx = hb.x + Math.floor(hb.w / 2);
    var bw  = hb.w - 16;
    var bx  = hb.x + 8;
    var text = this._humanBubble.text;
    text.setText(message.slice(0, 120));   // cap length
    var th = Math.min(text.height + 12, 72);           // cap max height
    // Bubble sits ABOVE sprite: body bottom = sprite top - 6 (tail gap)
    var tailY = this._humanBubble.spriteTopY - 6;
    var by    = Math.max(tailY - th, hb.y + 4);        // never above panel top

    var border = 0x58a6ff;
    var g = this._humanBubble.gfx;
    g.clear();
    g.fillStyle(0x1c2128, 0.96);
    g.fillRoundedRect(bx, by, bw, th, 5);
    g.lineStyle(2, border, 1);
    g.strokeRoundedRect(bx, by, bw, th, 5);
    // Speech-bubble tail pointing DOWN at the sprite head
    g.fillStyle(0x1c2128, 0.96);
    g.fillTriangle(hcx - 6, by + th, hcx + 6, by + th, hcx, tailY);
    g.lineStyle(2, border, 1);
    g.lineBetween(hcx - 6, by + th, hcx, tailY);
    g.lineBetween(hcx + 6, by + th, hcx, tailY);

    g.setAlpha(1);
    // Center text vertically within the capped box
    text.setPosition(hcx, by + th / 2).setOrigin(0.5, 0.5).setAlpha(1);
    this._humanBubble.hideAt = this._tick + 6;
  }

  // ── Envelope animation ────────────────────────────────────────────────────────

  _flyEnvelope(targetAgentIdx) {
    if (!this._panelsBuilt) return;
    var hb = this._panelBounds[0];
    var tb = this._panelBounds[targetAgentIdx + 1];
    if (!tb) return;
    var sx = hb.x + Math.floor(hb.w / 2), sy = this._midY + Math.floor(this._midH * 0.4);
    var ex = tb.x + Math.floor(tb.w / 2), ey = this._midY + 60;
    var gfx = this.add.graphics();
    gfx.fillStyle(0xffd700, 1); gfx.fillRect(0, 0, 18, 12);
    gfx.fillStyle(0xbb8800, 1); gfx.fillTriangle(0, 0, 18, 0, 9, 6);
    gfx.lineStyle(1, 0x554400, 1); gfx.strokeRect(0, 0, 18, 12);
    gfx.x = sx; gfx.y = sy;
    this.tweens.add({ targets: gfx, x: ex, y: ey, duration: 480, ease: 'Quad.easeOut', onComplete: function() { gfx.destroy(); } });
  }

  // ── LLM speech bubble (appears in the HEADER band above the sprite) ──────────

  _showLLMBubble(panelIdx, actionKind, result) {
    var obj = this._panelObjs[panelIdx];
    if (!obj || !obj.llmBubbleGfx) return;

    var raw = (actionKind === 'proact'
      ? (result.inform || '')
      : (result.response || result.raw || '')).slice(0, 80);
    if (!raw || result.parse_error) raw = '[parse error]';

    var clr = { proact: '#ffa657', respond_slow: '#7ee787', respond_fast: '#58a6ff' }[actionKind] || '#e6edf3';
    var border = { proact: 0xffa657, respond_slow: 0x7ee787, respond_fast: 0x58a6ff }[actionKind] || 0x30363d;

    var g  = obj.llmBubbleGfx;
    var tx = obj.llmBubbleText;
    var bx = obj.llmBubbleX, bw = obj.llmBubbleW;
    var cy = obj.llmBubbleY;

    tx.setText(raw).setStyle({ color: clr });
    var bh = tx.height + 10;
    var by = cy - bh / 2;

    g.clear();
    g.fillStyle(0x1c2128, 0.97); g.fillRoundedRect(bx, by, bw, bh, 4);
    g.lineStyle(1, border, 1);   g.strokeRoundedRect(bx, by, bw, bh, 4);
    // Tail pointing down toward sprite head
    var tcx = bx + Math.floor(bw / 2);
    g.fillStyle(0x1c2128, 0.97);
    g.fillTriangle(tcx - 5, by + bh, tcx + 5, by + bh, tcx, by + bh + 6);
    g.lineStyle(1, border, 1);
    g.lineBetween(tcx - 5, by + bh, tcx, by + bh + 6);
    g.lineBetween(tcx + 5, by + bh, tcx, by + bh + 6);

    tx.setY(cy).setAlpha(1);
    g.setAlpha(1);

    var self = this;
    this.time.delayedCall(BUBBLE_LIFETIME, function() {
      self.tweens.add({
        targets: [g, tx], alpha: 0, duration: 500,
        onComplete: function() { g.clear(); },
      });
    });
  }

  _flyEnvelopeToHuman(agentIdx, message) {
    if (!this._panelsBuilt) return;
    var ab  = this._panelBounds[agentIdx + 1];
    var hb  = this._panelBounds[0];
    if (!ab || !hb) return;
    var sx = ab.x + Math.floor(ab.w / 2), sy = this._midY + 60;
    var ex = hb.x + Math.floor(hb.w / 2), ey = this._midY + Math.floor(this._midH * 0.38);

    // Slightly different envelope color (green tinted = proact INFORM vs gold = human REQUEST)
    var gfx = this.add.graphics();
    gfx.fillStyle(0x4dbb6d, 1); gfx.fillRect(0, 0, 18, 12);
    gfx.fillStyle(0x1e8a3e, 1); gfx.fillTriangle(0, 0, 18, 0, 9, 6);
    gfx.lineStyle(1, 0x0d4a1e, 1); gfx.strokeRect(0, 0, 18, 12);
    gfx.x = sx; gfx.y = sy;
    var self = this;
    this.tweens.add({
      targets: gfx, x: ex, y: ey, duration: 600, ease: 'Quad.easeOut',
      onComplete: function() {
        gfx.destroy();
        // Flash the human sprite tint briefly
        if (self._humanSprite) {
          self._humanSprite.setTint(0x90ee90);
          self.time.delayedCall(300, function() {
            self._humanSprite.setTint(0xd8a8ff);
          });
        }
        // Show human bubble with the proact insight
        if (message) self._showHumanBubble('← ' + message.slice(0, 60));
      },
    });
  }

  update() {}
}
