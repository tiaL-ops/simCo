// scenes/Agent.js

/**
 *Here we have the posiinilities to actually move the agent
 */
export default class AgentScene extends Phaser.Physics.Arcade.Sprite {
  /**
   * @param {Phaser.Scene} scene The scene that owns this Agent.
   * @param {number} x The starting x-coordinate.
   * @param {number} y The starting y-coordinate.
   * @param {string} textureKey The key for the Agent's spritesheet.
   */
  constructor(scene, x, y, textureKey) {
    // Call the parent constructor (Phaser.Physics.Arcade.Sprite)
    super(scene, x, y, textureKey);

    // --- Add the Agent to the scene and physics engine ---
    scene.add.existing(this);
    scene.physics.add.existing(this);

    // --- Agent Properties ---
    this.setCollideWorldBounds(true);
    this.textureKey = textureKey; // Store the key for animation lookup
    this.lastDirection = 'down';  // Used for setting the correct idle frame

    // --- Physics Body Adjustment ---
    // We create a smaller, more precise physics body for smoother collisions.
    const bodyWidth = this.width * 0.5;
    const bodyHeight = this.height * 0.3;
    this.body.setSize(bodyWidth, bodyHeight);
    this.body.setOffset(
      (this.width - bodyWidth) / 2,
      this.height - bodyHeight
    );

    // --- Animations ---
    // Create all the necessary animations for this specific Agent sprite.
    this.createAgentAnimations();
  }

  /**
   * Creates the Agent's walking animations from its spritesheet.
   * This is called internally by the constructor.
   */
  createAgentAnimations() {
    const anims = this.scene.anims;
    const key = this.textureKey;

    anims.create({
      key: `${key}_walk_down`,
      frames: anims.generateFrameNumbers(key, { frames: [0, 4, 8, 12] }),
      frameRate: 10,
      repeat: -1,
    });
    anims.create({
      key: `${key}_walk_left`,
      frames: anims.generateFrameNumbers(key, { frames: [1, 5, 9, 13] }),
      frameRate: 10,
      repeat: -1,
    });
    anims.create({
      key: `${key}_walk_up`,
      frames: anims.generateFrameNumbers(key, { frames: [2, 6, 10, 14] }),
      frameRate: 10,
      repeat: -1,
    });
    anims.create({
      key: `${key}_walk_right`,
      frames: anims.generateFrameNumbers(key, { frames: [3, 7, 11, 15] }),
      frameRate: 10,
      repeat: -1,
    });
  }

  /**
   * The update method for the Agent, called every frame from the scene's update loop.
   * @param {Phaser.Types.Input.Keyboard.CursorKeys} cursors The cursor keys object.
   */
  update(cursors) {
    const speed = 200;
    const key = this.textureKey;

    // Reset velocity from the previous frame
    this.setVelocity(0);

    // --- Handle Movement and Animation ---
    if (cursors.left.isDown) {
      this.setVelocityX(-speed);
      this.anims.play(`${key}_walk_left`, true);
      this.lastDirection = 'left';
    } else if (cursors.right.isDown) {
      this.setVelocityX(speed);
      this.anims.play(`${key}_walk_right`, true);
      this.lastDirection = 'right';
    } else if (cursors.up.isDown) {
      this.setVelocityY(-speed);
      this.anims.play(`${key}_walk_up`, true);
      this.lastDirection = 'up';
    } else if (cursors.down.isDown) {
      this.setVelocityY(speed);
      this.anims.play(`${key}_walk_down`, true);
      this.lastDirection = 'down';
    } else {
      // --- Handle Idle State ---
      this.anims.stop();

      // Set the idle frame based on the last direction of movement.
      switch (this.lastDirection) {
        case 'up':
          this.setFrame(2);
          break;
        case 'down':
          this.setFrame(0);
          break;
        case 'left':
          this.setFrame(1);
          break;
        case 'right':
          this.setFrame(3);
          break;
      }
    }
  }
}