// scenes/AgentScene.js

/**
 * AgentScene - Displays and manages multiple player agents with animations
 *
 * Supports up to 10 selectable characters in SocialRoom
 * Click to select, arrow keys to move selected character
 */
class AgentScene extends Phaser.Scene {
  constructor() {
    super({ key: 'AgentScene' });
  }

  init(data) {
    // Receive map data from MapScene
    this.mapScene = data.mapScene;
    this.map = data.map;
    this.wallLayer = data.wallLayer;
    this.moneyLayer = data.moneyLayer;
    this.rooms = data.rooms || {};
    
    // Multi-character support
    this.players = [];          // Array of all player objects
    this.selectedPlayer = null; // Currently selected/controlled player
    this.maxCharacters = 10;
    this.characterCounter = 1;
    this.usedCharacters = [];   // Track which character indices have been used
    this.availableCharacters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    this.characterNameMap = {
      1: 'A',
      2: 'B',
      3: 'C',
      4: 'D',
      5: 'E',
      6: 'F',
      7: 'G',
      8: 'H',
      9: 'I',
      10: 'J'
    };
    
    // Game state (ON/OFF)
    this.isGameOn = false;      // Game state toggle
    
    // Money Prize System
    this.moneyPrizePool = 1000; // Starting prize pool

    // Behavior system
    this.moneyTarget = null;
    this.moneyTurnIndex = 0;

    // Navigation system (derived from tilemap JSON + wall layer)
    this.walkableGrid = [];
    this.pathRecalcInterval = 300;
  }

  preload() {
    // Load all 11 character spritesheets
    // 16 wide × 32 tall frames, 28 columns per row, no margin or spacing
    for (let i = 1; i <= 11; i++) {
      const paddedNum = i.toString().padStart(2, '0');
      this.load.spritesheet(
        `character_${paddedNum}`,
        `phaser/assets/agents/Premade_Character_${paddedNum}.png`,
        {
          frameWidth: 16,
          frameHeight: 32,
          margin: 0,
          spacing: 0
        }
      );
    }

    this.load.image('talking_indicator', 'phaser/assets/talkingbig.gif');
    console.log('AgentScene preload - All 11 character spritesheets loaded');
  }

  create() {
    console.log('AgentScene create - Creating player with animations');

    const { width, height } = this.scale;

    this.currentCharacter = 'player';

    // Draw room boundaries as green boxes
    this.drawRoomBoundaries();

    // Enable physics debug display
    this.debugGraphics = this.add.graphics();
    this.debugGraphics.setDepth(100);

    // Animations will be created per-character when spawned

    // Set up camera
    this.setupCamera();

    // Set up keyboard controls
    this.cursors = this.input.keyboard.createCursorKeys();
    this.wasd = this.input.keyboard.addKeys({
      up:    Phaser.Input.Keyboard.KeyCodes.W,
      down:  Phaser.Input.Keyboard.KeyCodes.S,
      left:  Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D
    });

    // Create the first player
    this.addNewCharacter();

    this.buildWalkableGridFromMap();
    this.moneyTarget = this.findMoneyTarget();
    
    // Set up UI button listeners
    const addBtn = document.getElementById('add-character-btn');
    if (addBtn) {
      addBtn.addEventListener('click', () => this.addNewCharacter());
    }

    const gameStateBtn = document.getElementById('game-state-btn');
    if (gameStateBtn) {
      gameStateBtn.addEventListener('click', () => this.toggleGameState());
    }

    const playerInfoBtn = document.getElementById('see-player-info-btn');
    if (playerInfoBtn) {
      playerInfoBtn.addEventListener('click', () => this.togglePlayerInfoPanel());
    }

    const closePlayerInfoBtn = document.getElementById('close-player-info-btn');
    if (closePlayerInfoBtn) {
      closePlayerInfoBtn.addEventListener('click', () => this.closePlayerInfoPanel());
    }

    // Set up player-to-player collisions (for greeting)
    for (let i = 0; i < this.players.length; i++) {
      for (let j = i + 1; j < this.players.length; j++) {
        this.physics.add.collider(
          this.players[i].sprite,
          this.players[j].sprite,
          (sprite1, sprite2) => this.onPlayerCollide(sprite1, sprite2),
          null,
          this
        );
      }
    }

    console.log('AgentScene created - Player sprite ready with animations');
    this.updatePlayerInfoPanel();
  }

  addNewCharacter() {
    if (this.players.length >= this.maxCharacters) {
      console.log('Maximum 10 characters reached!');
      return;
    }

    // Pick the next unused character in order (1..10)
    const remaining = this.availableCharacters.filter(idx => !this.usedCharacters.includes(idx));
    if (remaining.length === 0) {
      console.log('No more unique characters available!');
      return;
    }

    const selectedCharNum = remaining[0];
    const playerName = this.characterNameMap[selectedCharNum] || `P${selectedCharNum}`;
    this.usedCharacters.push(selectedCharNum);
    const characterKey = `character_${selectedCharNum.toString().padStart(2, '0')}`;

    // Create animations for this character if not already created
    if (!this.anims.exists(`${characterKey}_walk_right`)) {
      this.createPlayerAnimations(characterKey);
    }

    const socialRoom = this.rooms['SocialRoom'];
    let startX, startY;
    
    if (socialRoom) {
      // Spread characters in the room with some randomness, ensuring they stay within bounds
      const padding = 20;
      const minX = Math.max(socialRoom.minX, socialRoom.minX + padding);
      const maxX = Math.min(socialRoom.maxX, socialRoom.maxX - padding);
      const minY = Math.max(socialRoom.minY, socialRoom.minY + padding);
      const maxY = Math.min(socialRoom.maxY, socialRoom.maxY - padding);
      
      startX = minX + Math.random() * (maxX - minX);
      startY = minY + Math.random() * (maxY - minY);
    } else {
      startX = 100 + this.players.length * 30;
      startY = 150;
    }

    // Create player sprite with the selected character
    const player = this.physics.add.sprite(startX, startY, characterKey);
    player.setScale(1.5);
    player.setDepth(20);
    player.setCollideWorldBounds(true);
    player.setBounce(0.2);

    // Physics body sized to the character's feet area
    player.body.setSize(14, 8);
    player.body.setOffset(1, 22);

    // Set up collision with wall layer
    if (this.wallLayer) {
      this.physics.add.collider(player, this.wallLayer);
    }

    // Player data
    const playerData = {
      sprite: player,
      characterKey: characterKey,
      characterNum: selectedCharNum,
      id: this.characterCounter++,
      name: playerName,
      lastDirection: 'down',
      currentRoom: 'SocialRoom',
      wasOnMoney: false,
      isSelected: false,
      idleFrames: this.getIdleFrames(characterKey),
      socialRoom: socialRoom,
      money: 0,
      lastTalkTime: 0,
      talkBubble: null,
      greetedAgents: new Set(),
      homeX: startX,
      homeY: startY,
      turnState: 'waiting',
      pathCache: null,
      pathCacheKey: '',
      nextPathRecalcAt: 0
    };

    // Make sprite interactive for selection
    player.setInteractive({ useHandCursor: true });
    player.on('pointerdown', () => this.selectPlayer(playerData));

    this.players.push(playerData);

    // Set up collision with newly added player against all existing players
    for (let i = 0; i < this.players.length - 1; i++) {
      this.physics.add.collider(
        this.players[i].sprite,
        player,
        (sprite1, sprite2) => this.onPlayerCollide(sprite1, sprite2),
        null,
        this
      );
    }

    // Auto-select first player if none selected
    if (!this.selectedPlayer) {
      this.selectPlayer(playerData);
    }

    this.updateUI();
    console.log(`Character ${playerData.id} (Name: ${playerName}) spawned (Type: ${selectedCharNum}). Total: ${this.players.length}`);
  }

  selectPlayer(playerData) {
    // Deselect previous
    if (this.selectedPlayer) {
      this.selectedPlayer.isSelected = false;
      this.selectedPlayer.sprite.setTint(0xffffff);
    }

    // Select new
    this.selectedPlayer = playerData;
    playerData.isSelected = true;
    playerData.sprite.setTint(0x3498db); // Blue tint for selected

    this.updateUI();
    console.log(`Selected character ${playerData.id}`);
  }

  updateUI() {
    const selectedDisplay = document.getElementById('selected-character-display');
    const countDisplay = document.getElementById('character-count');
    const prizePoolDisplay = document.getElementById('prize-pool-display');

    if (selectedDisplay) {
      selectedDisplay.textContent = this.selectedPlayer 
        ? `Selected: Player ${this.selectedPlayer.name}` 
        : 'Selected: None';
    }

    if (countDisplay) {
      countDisplay.textContent = `Characters: ${this.players.length}/${this.maxCharacters}`;
    }

    if (prizePoolDisplay) {
      prizePoolDisplay.textContent = `Prize Pool: $${this.moneyPrizePool.toFixed(2)}`;
    }

    this.updateLeaderboard();
  }

  updateLeaderboard() {
    const leaderboardDisplay = document.getElementById('leaderboard-display');
    if (!leaderboardDisplay) return;

    // Sort players by money (descending)
    const sortedPlayers = [...this.players].sort((a, b) => b.money - a.money);

    let leaderboardHTML = '<div class="ui-section-title">Leaderboard</div>';
    sortedPlayers.forEach((player, index) => {
      const rank = index + 1;
      const className = player.isSelected ? 'leaderboard-entry selected' : 'leaderboard-entry';
      leaderboardHTML += `<div class="${className}">${rank}. Player ${player.name}: $${player.money.toFixed(2)}</div>`;
    });

    leaderboardDisplay.innerHTML = leaderboardHTML;
    this.updatePlayerInfoPanel();
  }

  togglePlayerInfoPanel() {
    const panel = document.getElementById('player-info-panel');
    if (!panel) return;

    panel.classList.toggle('open');
    panel.setAttribute('aria-hidden', panel.classList.contains('open') ? 'false' : 'true');
    if (panel.classList.contains('open')) {
      this.updatePlayerInfoPanel();
    }
  }

  closePlayerInfoPanel() {
    const panel = document.getElementById('player-info-panel');
    if (!panel) return;

    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
  }

  updatePlayerInfoPanel() {
    const infoList = document.getElementById('player-info-list');
    if (!infoList) return;

    // Row 1, col 20 — one static frame (16×32 natural, displayed 2×)
    const FW = 16, FH = 16, COLS = 28, ROW = 2, COL = 2;
    const scale = 4;
    const bx = COL * FW * scale;
    const by = ROW * FH * scale;
    const bsw = COLS * FW * scale;

    let infoHtml = '';
    for (let i = 1; i <= this.maxCharacters; i++) {
      const name = this.characterNameMap[i] || `P${i}`;
      const player = this.players.find(p => p.characterNum === i);
      const selectedClass = player && player.isSelected ? ' selected' : '';
      const padded = i.toString().padStart(2, '0');
      const avatarStyle = `background-image:url('phaser/assets/agents/Premade_Character_${padded}.png');background-size:${bsw}px auto;background-position:-${bx}px -${by}px`;

      infoHtml += `<div class="player-info-row${selectedClass}"><span class="player-info-avatar" style="${avatarStyle}"></span><span>Player ${name}</span></div>`;
    }

    infoList.innerHTML = infoHtml;
  }

  toggleGameState() {
    this.isGameOn = !this.isGameOn;
    const gameStateBtn = document.getElementById('game-state-btn');
    if (gameStateBtn) {
      gameStateBtn.textContent = this.isGameOn ? 'GAME: ON' : 'GAME: OFF';
      gameStateBtn.style.background = this.isGameOn ? '#27ae60' : '#e74c3c';
    }

    if (this.isGameOn) {
      this.moneyTurnIndex = 0;
      this.players.forEach((player, index) => {
        player.turnState = index === this.moneyTurnIndex ? 'going_money' : 'waiting';
      });
    } else {
      this.players.forEach(player => {
        player.turnState = 'waiting';
      });
    }

    console.log(`Game state: ${this.isGameOn ? 'ON' : 'OFF'}`);
  }

  createPlayerAnimations(key) {
    // Sheet is 28 columns wide at 32px each
    const COLS_PER_ROW = 28;

    // Walk animations are on logical row 4  (y = 4 × 64 = 256px)
    const WALK_ROW = 4;

    // f(row, col) → linear frame index
    const f = (row, col) => row * COLS_PER_ROW + col;

    const makeAnim = (startCol, endCol) => ({
      frames: this.anims.generateFrameNumbers(key, {
        start: f(WALK_ROW, startCol),
        end:   f(WALK_ROW, endCol)
      }),
      frameRate: 10,
      repeat: -1
    });

    this.anims.create({ key: `${key}_walk_right`, ...makeAnim(0,  5)  });
    this.anims.create({ key: `${key}_walk_up`,    ...makeAnim(6,  11) });
    this.anims.create({ key: `${key}_walk_left`,  ...makeAnim(12, 17) });
    this.anims.create({ key: `${key}_walk_down`,  ...makeAnim(18, 23) });
  }

  getIdleFrames(characterKey) {
    // Idle = first frame of each direction's group
    const COLS_PER_ROW = 28;
    const WALK_ROW = 4;
    const f = (row, col) => row * COLS_PER_ROW + col;
    
    return {
      right: f(WALK_ROW, 1),
      up:    f(WALK_ROW, 6),
      left:  f(WALK_ROW, 12),
      down:  f(WALK_ROW, 18)
    };
  }

  setupCamera() {
    const { width, height } = this.scale;

    this.cameras.main.setViewport(0, 0, width, height);
    this.cameras.main.setZoom(1.0);

    // Fixed camera: do not follow player
    this.cameras.main.setScroll(0, 0);
  }

  update() {
    if (!this.players || this.players.length === 0) return;

    const speed = 160;

    if (this.isGameOn) {
      this.ensureActiveMoneyTurn();
    }

    // Update all players
    this.players.forEach(playerData => {
      const player = playerData.sprite;
      if (!player) return;

      const key = playerData.characterKey;

      // If game is OFF, keep player within social room bounds only
      // If game is ON, they can move freely to other rooms
      if (!this.isGameOn && playerData.socialRoom) {
        const padding = 10;
        if (player.x < playerData.socialRoom.minX + padding) player.x = playerData.socialRoom.minX + padding;
        if (player.x > playerData.socialRoom.maxX - padding) player.x = playerData.socialRoom.maxX - padding;
        if (player.y < playerData.socialRoom.minY + padding) player.y = playerData.socialRoom.minY + padding;
        if (player.y > playerData.socialRoom.maxY - padding) player.y = playerData.socialRoom.maxY - padding;
      }

      // Check room for all players
      this.checkPlayerRoom(playerData);

      // Draw debug collision boxes
      this.debugGraphics.clear();
      this.debugGraphics.lineStyle(2, 0xff0000, 1);
      this.debugGraphics.strokeRect(
        player.body.x,
        player.body.y,
        player.body.width,
        player.body.height
      );

      player.body.setVelocity(0, 0);
      let isMoving = false;

      if (playerData.isSelected && this.hasManualMovementInput()) {
        isMoving = this.updateSelectedManualMovement(playerData, speed);
      } else if (this.isGameOn) {
        isMoving = this.updateMoneyTurnMovement(playerData, speed * 0.9);
      } else {
        isMoving = this.updateSocialMovement(playerData, speed * 0.7);
      }

      this.checkPlayerMoneyTouch(playerData);

      // Idle animation
      if (!isMoving) {
        player.anims.stop();
        if (playerData.idleFrames) {
          player.setFrame(playerData.idleFrames[playerData.lastDirection]);
        }
      }
    });
  }

  updateSocialMovement(playerData, speed) {
    const player = playerData.sprite;

    const targetPlayer = this.getNearestUngreetedAgent(playerData);
    if (targetPlayer) {
      return this.movePlayerTowardByPath(playerData, targetPlayer.sprite.x, targetPlayer.sprite.y, speed);
    }

    return this.movePlayerTowardByPath(playerData, playerData.homeX, playerData.homeY, speed * 0.7);
  }

  ensureActiveMoneyTurn() {
    if (this.players.length === 0 || this.moneyPrizePool <= 0) return;

    const hasActiveTurn = this.players.some(player => player.turnState === 'going_money' || player.turnState === 'returning_social');
    if (!hasActiveTurn) {
      this.players.forEach(player => {
        player.turnState = 'waiting';
      });

      const activePlayer = this.players[this.moneyTurnIndex % this.players.length];
      if (activePlayer) {
        activePlayer.turnState = 'going_money';
      }
    }
  }

  hasManualMovementInput() {
    return this.cursors.up.isDown || this.wasd.up.isDown ||
      this.cursors.down.isDown || this.wasd.down.isDown ||
      this.cursors.left.isDown || this.wasd.left.isDown ||
      this.cursors.right.isDown || this.wasd.right.isDown;
  }

  updateSelectedManualMovement(playerData, speed) {
    const player = playerData.sprite;
    const key = playerData.characterKey;

    if (this.cursors.up.isDown || this.wasd.up.isDown) {
      player.body.setVelocity(0, -speed);
      player.anims.play(`${key}_walk_up`, true);
      playerData.lastDirection = 'up';
      return true;
    }

    if (this.cursors.down.isDown || this.wasd.down.isDown) {
      player.body.setVelocity(0, speed);
      player.anims.play(`${key}_walk_down`, true);
      playerData.lastDirection = 'down';
      return true;
    }

    if (this.cursors.left.isDown || this.wasd.left.isDown) {
      player.body.setVelocity(-speed, 0);
      player.anims.play(`${key}_walk_left`, true);
      playerData.lastDirection = 'left';
      return true;
    }

    if (this.cursors.right.isDown || this.wasd.right.isDown) {
      player.body.setVelocity(speed, 0);
      player.anims.play(`${key}_walk_right`, true);
      playerData.lastDirection = 'right';
      return true;
    }

    return false;
  }

  movePlayerToward(playerData, targetX, targetY, speed) {
    return this.movePlayerTowardByPath(playerData, targetX, targetY, speed);
  }

  movePlayerTowardByPath(playerData, targetX, targetY, speed) {
    const player = playerData.sprite;
    const now = this.time.now;

    const startTile = this.worldToTile(player.x, player.y);
    const targetTile = this.worldToTile(targetX, targetY);
    if (!this.isTileInBounds(startTile.tx, startTile.ty) || !this.isTileInBounds(targetTile.tx, targetTile.ty)) {
      return this.movePlayerCardinal(playerData, targetX, targetY, speed);
    }

    const cacheKey = `${startTile.tx},${startTile.ty}->${targetTile.tx},${targetTile.ty}`;
    const shouldRecalc = !playerData.pathCache || playerData.pathCacheKey !== cacheKey || now >= playerData.nextPathRecalcAt;

    if (shouldRecalc) {
      playerData.pathCache = this.findPathTiles(startTile.tx, startTile.ty, targetTile.tx, targetTile.ty);
      playerData.pathCacheKey = cacheKey;
      playerData.nextPathRecalcAt = now + this.pathRecalcInterval;
    }

    const path = playerData.pathCache;
    if (!path || path.length === 0) {
      return this.movePlayerCardinal(playerData, targetX, targetY, speed);
    }

    if (path.length === 1) {
      return this.movePlayerCardinal(playerData, targetX, targetY, speed);
    }

    const nextTile = path[1];
    const nextWorld = this.tileToWorldCenter(nextTile.tx, nextTile.ty);
    return this.movePlayerCardinal(playerData, nextWorld.x, nextWorld.y, speed);
  }

  movePlayerCardinal(playerData, targetX, targetY, speed) {
    const player = playerData.sprite;
    const key = playerData.characterKey;

    const dx = targetX - player.x;
    const dy = targetY - player.y;
    const threshold = 6;

    if (Math.abs(dx) <= threshold && Math.abs(dy) <= threshold) {
      return true;
    }

    if (Math.abs(dx) > threshold) {
      const vx = dx > 0 ? speed : -speed;
      player.body.setVelocity(vx, 0);
      if (vx > 0) {
        player.anims.play(`${key}_walk_right`, true);
        playerData.lastDirection = 'right';
      } else {
        player.anims.play(`${key}_walk_left`, true);
        playerData.lastDirection = 'left';
      }
      return false;
    }

    const vy = dy > 0 ? speed : -speed;
    player.body.setVelocity(0, vy);
    if (vy > 0) {
      player.anims.play(`${key}_walk_down`, true);
      playerData.lastDirection = 'down';
    } else {
      player.anims.play(`${key}_walk_up`, true);
      playerData.lastDirection = 'up';
    }
    return false;
  }

  buildWalkableGridFromMap() {
    if (!this.map || !this.wallLayer) return;

    const width = this.map.width;
    const height = this.map.height;
    this.walkableGrid = new Array(height);

    for (let ty = 0; ty < height; ty++) {
      this.walkableGrid[ty] = new Array(width);
      for (let tx = 0; tx < width; tx++) {
        const wallTile = this.wallLayer.getTileAt(tx, ty);
        const blocked = !!(wallTile && wallTile.index > 0);
        this.walkableGrid[ty][tx] = !blocked;
      }
    }
  }

  worldToTile(worldX, worldY) {
    return {
      tx: this.map.worldToTileX(worldX),
      ty: this.map.worldToTileY(worldY)
    };
  }

  tileToWorldCenter(tx, ty) {
    return {
      x: this.map.tileToWorldX(tx) + this.map.tileWidth / 2,
      y: this.map.tileToWorldY(ty) + this.map.tileHeight / 2
    };
  }

  isTileInBounds(tx, ty) {
    return ty >= 0 && ty < this.walkableGrid.length && tx >= 0 && tx < (this.walkableGrid[ty] ? this.walkableGrid[ty].length : 0);
  }

  isTileWalkable(tx, ty) {
    if (!this.isTileInBounds(tx, ty)) return false;
    return !!this.walkableGrid[ty][tx];
  }

  findPathTiles(startTx, startTy, endTx, endTy) {
    if (!this.isTileWalkable(startTx, startTy) || !this.isTileWalkable(endTx, endTy)) {
      return null;
    }

    if (startTx === endTx && startTy === endTy) {
      return [{ tx: startTx, ty: startTy }];
    }

    const queue = [{ tx: startTx, ty: startTy }];
    const visited = new Set([`${startTx},${startTy}`]);
    const cameFrom = new Map();
    const directions = [
      { dx: 1, dy: 0 },
      { dx: -1, dy: 0 },
      { dx: 0, dy: 1 },
      { dx: 0, dy: -1 }
    ];

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current) break;

      if (current.tx === endTx && current.ty === endTy) {
        const path = [{ tx: endTx, ty: endTy }];
        let key = `${endTx},${endTy}`;

        while (cameFrom.has(key)) {
          const prev = cameFrom.get(key);
          if (!prev) break;
          path.push({ tx: prev.tx, ty: prev.ty });
          key = `${prev.tx},${prev.ty}`;
        }

        path.reverse();
        return path;
      }

      for (const direction of directions) {
        const nextTx = current.tx + direction.dx;
        const nextTy = current.ty + direction.dy;
        const nextKey = `${nextTx},${nextTy}`;

        if (visited.has(nextKey)) continue;
        if (!this.isTileWalkable(nextTx, nextTy)) continue;

        visited.add(nextKey);
        cameFrom.set(nextKey, { tx: current.tx, ty: current.ty });
        queue.push({ tx: nextTx, ty: nextTy });
      }
    }

    return null;
  }

  updateMoneyTurnMovement(playerData, speed) {
    if (playerData.turnState === 'going_money') {
      if (!this.moneyTarget) {
        return false;
      }

      const reachedMoney = this.movePlayerTowardByPath(
        playerData,
        this.moneyTarget.x,
        this.moneyTarget.y,
        speed
      );

      if (!reachedMoney) {
        return true;
      }

      playerData.turnState = 'returning_social';
      return false;
    }

    if (playerData.turnState === 'returning_social') {
      const reachedHome = this.movePlayerTowardByPath(
        playerData,
        playerData.homeX,
        playerData.homeY,
        speed
      );

      if (!reachedHome) {
        return true;
      }

      playerData.turnState = 'done';
      this.advanceMoneyTurn();
      return false;
    }

    return false;
  }

  getNearestUngreetedAgent(playerData) {
    let nearest = null;
    let nearestDistance = Number.MAX_VALUE;

    this.players.forEach(otherPlayer => {
      if (otherPlayer.id === playerData.id) return;
      if (playerData.greetedAgents.has(otherPlayer.id)) return;

      const dx = otherPlayer.sprite.x - playerData.sprite.x;
      const dy = otherPlayer.sprite.y - playerData.sprite.y;
      const distance = Math.hypot(dx, dy);

      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = otherPlayer;
      }
    });

    return nearest;
  }

  advanceMoneyTurn() {
    if (this.players.length === 0 || this.moneyPrizePool <= 0) {
      return;
    }

    this.moneyTurnIndex = (this.moneyTurnIndex + 1) % this.players.length;
    this.players.forEach(player => {
      player.turnState = 'waiting';
    });

    const nextPlayer = this.players[this.moneyTurnIndex];
    if (nextPlayer) {
      nextPlayer.turnState = 'going_money';
    }
  }

  findMoneyTarget() {
    if (!this.moneyLayer) return null;

    for (let y = 0; y < this.moneyLayer.layer.height; y++) {
      for (let x = 0; x < this.moneyLayer.layer.width; x++) {
        const tile = this.moneyLayer.getTileAt(x, y);
        if (tile && tile.index > 0) {
          return {
            x: tile.getCenterX(),
            y: tile.getCenterY()
          };
        }
      }
    }

    return null;
  }

  checkPlayerRoom(playerData) {
    const x = playerData.sprite.x;
    const y = playerData.sprite.y;
    let room = 'Unknown';

    for (const [roomName, bounds] of Object.entries(this.rooms)) {
      if (x >= bounds.minX && x <= bounds.maxX && y >= bounds.minY && y <= bounds.maxY) {
        room = roomName;
        break;
      }
    }

    if (room !== playerData.currentRoom) {
      playerData.currentRoom = room;
      console.log(`🎮 Character ${playerData.id}: I am in ${room}`);
    }
  }

  checkPlayerMoneyTouch(playerData) {
    if (!this.moneyLayer) return;

    const tile = this.moneyLayer.getTileAtWorldXY(playerData.sprite.x, playerData.sprite.y, true);
    const isOnMoney = !!(tile && tile.index > 0);

    if (isOnMoney && !playerData.wasOnMoney) {
      // Agent reaches the money prize
      console.log(`Character ${playerData.id}: I found money! Prize pool has $${this.moneyPrizePool.toFixed(2)}`);
      
      if (this.moneyPrizePool > 0) {
        // Prompt user to enter amount
        const userInput = prompt(`Character ${playerData.id} found money!\n\nPrize Pool: $${this.moneyPrizePool.toFixed(2)}\n\nHow much should they take?`);
        
        if (userInput !== null && userInput.trim() !== '') {
          const amountToTake = parseFloat(userInput);
          
          if (isNaN(amountToTake)) {
            alert('Invalid amount! Please enter a number.');
          } else if (amountToTake < 0) {
            alert('Amount cannot be negative!');
          } else if (amountToTake > this.moneyPrizePool) {
            alert(`Cannot take more than prize pool ($${this.moneyPrizePool.toFixed(2)})!`);
          } else {
            // Add money to player
            playerData.money += amountToTake;
            
            // Subtract from prize pool
            this.moneyPrizePool -= amountToTake;
            
            console.log(`Character ${playerData.id}: I took $${amountToTake.toFixed(2)}! Prize pool now has $${this.moneyPrizePool.toFixed(2)}`);
            console.log(`Character ${playerData.id}: I now have $${playerData.money.toFixed(2)} total`);
            
            this.updateUI();
          }
        }
      } else {
        console.log(`Character ${playerData.id}: The prize pool is empty!`);
        alert(`Character ${playerData.id} found the money, but the prize pool is empty!`);
      }
    }

    playerData.wasOnMoney = isOnMoney;
  }

  onPlayerCollide(sprite1, sprite2) {
    // Find which player data objects these sprites belong to
    const player1 = this.players.find(p => p.sprite === sprite1);
    const player2 = this.players.find(p => p.sprite === sprite2);

    if (player1 && player2) {
      if (!player1.greetedAgents.has(player2.id)) {
        player1.greetedAgents.add(player2.id);
        this.agentTalk(player1, `Hi ${player2.name}`);
      }

      if (!player2.greetedAgents.has(player1.id)) {
        player2.greetedAgents.add(player1.id);
        this.agentTalk(player2, `Hi ${player1.name}`);
      }
    }
  }

  agentTalk(playerData, message) {
    const now = this.time.now;
    if (now - playerData.lastTalkTime < 800) {
      return;
    }

    playerData.lastTalkTime = now;
    console.log(`Character ${playerData.id}: ${message}`);

    if (playerData.talkBubble) {
      playerData.talkBubble.destroy();
      playerData.talkBubble = null;
    }

    const offsetX = 16;
    const offsetY = -20;
    playerData.talkBubble = this.add.image(
      playerData.sprite.x + offsetX,
      playerData.sprite.y + offsetY,
      'talking_indicator'
    );
    playerData.talkBubble.setDepth(2000);
    playerData.talkBubble.setScale(0.4);

    this.time.delayedCall(700, () => {
      if (playerData.talkBubble) {
        playerData.talkBubble.destroy();
        playerData.talkBubble = null;
      }
    });
  }

  drawRoomBoundaries() {
    const graphics = this.add.graphics();
    graphics.setDepth(1000);
    graphics.setAlpha(0.3);

    // Green color for room boundaries
    graphics.lineStyle(2, 0x00ff00, 1);
    graphics.fillStyle(0x00ff00, 0.15);

    // Draw each room as a green box
    for (const [roomName, bounds] of Object.entries(this.rooms)) {
      const width = bounds.maxX - bounds.minX;
      const height = bounds.maxY - bounds.minY;
      graphics.strokeRect(bounds.minX, bounds.minY, width, height);
      graphics.fillRect(bounds.minX, bounds.minY, width, height);

      // Add room label text
      this.add.text(
        bounds.minX + width / 2,
        bounds.minY + 15,
        roomName,
        {
          fontSize: '12px',
          color: '#00ff00',
          align: 'center'
        }
      ).setOrigin(0.5, 0).setDepth(1001);
    }
  }
}
