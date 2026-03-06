// scenes/AgentScene.js

/**
 * AgentScene - Displays and manages multiple player agents with animations
 *
 * Supports up to 5 selectable characters in SocialRoom
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
    this.maxCharacters = 5;
    this.characterCounter = 1;
    this.usedCharacters = [];   // Track which character indices have been used
    this.availableCharacters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]; // All 11 available
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
    
    // Set up UI button listener
    const addBtn = document.getElementById('add-character-btn');
    if (addBtn) {
      addBtn.addEventListener('click', () => this.addNewCharacter());
    }

    console.log('AgentScene created - Player sprite ready with animations');
  }

  addNewCharacter() {
    if (this.players.length >= this.maxCharacters) {
      console.log('Maximum 5 characters reached!');
      return;
    }

    // Pick a random unused character
    const remaining = this.availableCharacters.filter(idx => !this.usedCharacters.includes(idx));
    if (remaining.length === 0) {
      console.log('No more unique characters available!');
      return;
    }

    const randomIdx = Math.floor(Math.random() * remaining.length);
    const selectedCharNum = remaining[randomIdx];
    this.usedCharacters.push(selectedCharNum);
    const characterKey = `character_${selectedCharNum.toString().padStart(2, '0')}`;

    // Create animations for this character if not already created
    if (!this.anims.exists(`${characterKey}_walk_right`)) {
      this.createPlayerAnimations(characterKey);
    }

    const socialRoom = this.rooms['SocialRoom'];
    let startX, startY;
    
    if (socialRoom) {
      // Spread characters in the room with some randomness
      startX = socialRoom.minX + Math.random() * (socialRoom.maxX - socialRoom.minX);
      startY = socialRoom.minY + Math.random() * (socialRoom.maxY - socialRoom.minY);
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
      lastDirection: 'down',
      currentRoom: 'SocialRoom',
      wasOnMoney: false,
      isSelected: false,
      idleFrames: this.getIdleFrames(characterKey)
    };

    // Make sprite interactive for selection
    player.setInteractive({ useHandCursor: true });
    player.on('pointerdown', () => this.selectPlayer(playerData));

    this.players.push(playerData);

    // Auto-select first player if none selected
    if (!this.selectedPlayer) {
      this.selectPlayer(playerData);
    }

    this.updateUI();
    console.log(`Character ${playerData.id} spawned (Type: ${selectedCharNum}). Total: ${this.players.length}`);
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

    if (selectedDisplay) {
      selectedDisplay.textContent = this.selectedPlayer 
        ? `Selected: Character ${this.selectedPlayer.id}` 
        : 'Selected: None';
    }

    if (countDisplay) {
      countDisplay.textContent = `Characters: ${this.players.length}/${this.maxCharacters}`;
    }
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

    // Update all players
    this.players.forEach(playerData => {
      const player = playerData.sprite;
      if (!player) return;

      const key = playerData.characterKey;

      // Check room for all players
      this.checkPlayerRoom(playerData);
      this.checkPlayerMoneyTouch(playerData);

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

      // ONLY selected player responds to input
      if (playerData.isSelected) {
        // Horizontal movement
        if (this.cursors.left.isDown || this.wasd.left.isDown) {
          player.body.setVelocityX(-speed);
          player.anims.play(`${key}_walk_left`, true);
          playerData.lastDirection = 'left';
          isMoving = true;
        } else if (this.cursors.right.isDown || this.wasd.right.isDown) {
          player.body.setVelocityX(speed);
          player.anims.play(`${key}_walk_right`, true);
          playerData.lastDirection = 'right';
          isMoving = true;
        }

        // Vertical movement
        if (this.cursors.up.isDown || this.wasd.up.isDown) {
          player.body.setVelocityY(-speed);
          player.anims.play(`${key}_walk_up`, true);
          playerData.lastDirection = 'up';
          isMoving = true;
        } else if (this.cursors.down.isDown || this.wasd.down.isDown) {
          player.body.setVelocityY(speed);
          player.anims.play(`${key}_walk_down`, true);
          playerData.lastDirection = 'down';
          isMoving = true;
        }
      }

      // Idle animation
      if (!isMoving) {
        player.anims.stop();
        if (playerData.idleFrames) {
          player.setFrame(playerData.idleFrames[playerData.lastDirection]);
        }
      }
    });
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
      console.log(`Character ${playerData.id}: moneyyyyy`);
    }

    playerData.wasOnMoney = isOnMoney;
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
