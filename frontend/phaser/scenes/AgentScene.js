// scenes/AgentScene.js

/**
 * AgentScene - Displays and manages the player agent with animations
 *
 * Spritesheet layout: Premade_Character_01.png
 *   - 896 x 656 px total
 *   - Frame size: 32 x 64 px  (frameWidth=32, frameHeight=64)
 *   - Columns per row: 896 / 32 = 28
 *
 *   Walk animations live at y=256 (logical row 4 at 64px height):
 *     Cols  0–5  → walk RIGHT
 *     Cols  6–11 → walk UP
 *     Cols 12–17 → walk LEFT
 *     Cols 18–23 → walk DOWN
 *
 *   Frame index formula: f(row, col) = row * 28 + col
 *   Row 4 base = 4 * 28 = 112
 *     walk_right : 112–117
 *     walk_up    : 118–123
 *     walk_left  : 124–129
 *     walk_down  : 130–135
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
  }

  preload() {
    // 32 wide × 64 tall frames, 28 columns per row, no margin or spacing
    this.load.spritesheet('player', 'phaser/assets/agents/Premade_Character_01.png', {
      frameWidth: 16,
      frameHeight: 32,
      margin: 0,
      spacing: 0
    });
    console.log('AgentScene preload - Character spritesheet loaded');
  }

  create() {
    console.log('AgentScene create - Creating player with animations');

    const { width, height } = this.scale;

    // Find starting position in SocialRoom
    const socialRoom = this.rooms['SocialRoom'];
    let startX = 100, startY = 150;
    if (socialRoom) {
      startX = socialRoom.minX + (socialRoom.maxX - socialRoom.minX) / 2;
      startY = socialRoom.minY + (socialRoom.maxY - socialRoom.minY) / 2;
    }

    // Create player sprite
    this.player = this.physics.add.sprite(startX, startY, 'player');
    this.player.setScale(1.5);
    this.player.setDepth(20);
    this.player.setCollideWorldBounds(true);
    this.player.setBounce(0.2);

    // Physics body sized to the character's feet area (bottom of 32px frame)
    // frameHeight is 32px, so feet are around y=22-28
    this.player.body.setSize(14, 8);
    this.player.body.setOffset(1, 22);

    // Set up collision with wall layer
    if (this.wallLayer) {
      this.physics.add.collider(this.player, this.wallLayer);
      console.log('Wall collision enabled');
    }

    this.wasOnMoney = false;

    this.currentCharacter = 'player';
    this.lastDirection = 'down';
    this.currentRoom = 'SocialRoom';

    // Draw room boundaries as green boxes
    this.drawRoomBoundaries();

    // Enable physics debug display
    this.debugGraphics = this.add.graphics();
    this.debugGraphics.setDepth(100);

    // Create animations
    this.createPlayerAnimations();

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

    console.log('AgentScene created - Player sprite ready with animations');
  }

  createPlayerAnimations() {
    if (this.currentCharacter === 'fallback') return;

    const key = this.currentCharacter;

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

    // Idle = first frame of each direction's group
    this.idleFrames = {
      right: f(WALK_ROW, 1),
      up:    f(WALK_ROW, 6),
      left:  f(WALK_ROW, 12),
      down:  f(WALK_ROW, 18)
    };

    // Start facing down
    this.player.setFrame(this.idleFrames.down);
  }

  setupCamera() {
    const { width, height } = this.scale;

    this.cameras.main.setViewport(0, 0, width, height);
    this.cameras.main.setZoom(1.0);

    // Fixed camera: do not follow player
    this.cameras.main.setScroll(0, 0);
  }

  update() {
    if (!this.player) return;

    // Check which room player is in
    this.checkCurrentRoom();
    this.checkMoneyTouch();

    // Draw collision debug boxes
    this.debugGraphics.clear();
    this.debugGraphics.lineStyle(2, 0xff0000, 1);
    this.debugGraphics.strokeRect(
      this.player.body.x,
      this.player.body.y,
      this.player.body.width,
      this.player.body.height
    );

    this.player.body.setVelocity(0, 0);

    const speed = 160;
    const key   = this.currentCharacter;
    let isMoving = false;

    // Horizontal movement (checked first; vertical can override animation)
    if (this.cursors.left.isDown || this.wasd.left.isDown) {
      this.player.body.setVelocityX(-speed);
      this.player.anims.play(`${key}_walk_left`, true);
      this.lastDirection = 'left';
      isMoving = true;
    } else if (this.cursors.right.isDown || this.wasd.right.isDown) {
      this.player.body.setVelocityX(speed);
      this.player.anims.play(`${key}_walk_right`, true);
      this.lastDirection = 'right';
      isMoving = true;
    }

    // Vertical movement (overrides horizontal animation for cleaner diagonals)
    if (this.cursors.up.isDown || this.wasd.up.isDown) {
      this.player.body.setVelocityY(-speed);
      this.player.anims.play(`${key}_walk_up`, true);
      this.lastDirection = 'up';
      isMoving = true;
    } else if (this.cursors.down.isDown || this.wasd.down.isDown) {
      this.player.body.setVelocityY(speed);
      this.player.anims.play(`${key}_walk_down`, true);
      this.lastDirection = 'down';
      isMoving = true;
    }

    // Idle: freeze on first frame of last-used direction
    if (!isMoving) {
      this.player.anims.stop();
      if (this.idleFrames) {
        this.player.setFrame(this.idleFrames[this.lastDirection]);
      }
    }
  }

  checkCurrentRoom() {
    const x = this.player.x;
    const y = this.player.y;
    let room = 'Unknown';

    // Check which room the player is in
    for (const [roomName, bounds] of Object.entries(this.rooms)) {
      if (x >= bounds.minX && x <= bounds.maxX && y >= bounds.minY && y <= bounds.maxY) {
        room = roomName;
        break;
      }
    }

    // Log if room changed
    if (room !== this.currentRoom) {
      this.currentRoom = room;
      console.log(`🎮 Oh! I am in ${this.currentRoom}`);
    }
  }

  checkMoneyTouch() {
    if (!this.moneyLayer) return;

    const tile = this.moneyLayer.getTileAtWorldXY(this.player.x, this.player.y, true);
    const isOnMoney = !!(tile && tile.index > 0);

    if (isOnMoney && !this.wasOnMoney) {
      console.log('moneyyyyy');
    }

    this.wasOnMoney = isOnMoney;
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