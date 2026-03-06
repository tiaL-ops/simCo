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

    // Create player sprite
    this.player = this.physics.add.sprite(width / 2, height / 2, 'player');
    this.player.setScale(1.5);
    this.player.setDepth(20);
    this.player.setCollideWorldBounds(true);

    // Physics body sized to the character's feet area (bottom of 64px frame)
    this.player.body.setSize(20, 16);
    this.player.body.setOffset(6, 46);

    this.currentCharacter = 'player';
    this.lastDirection = 'down';

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
    this.cameras.main.startFollow(this.player, true, 0.05, 0.05);
    this.cameras.main.setZoom(1.0);
    this.cameras.main.setDeadzone(100, 100);
    this.cameras.main.centerOn(this.player.x, this.player.y);
  }

  update() {
    if (!this.player) return;

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
}