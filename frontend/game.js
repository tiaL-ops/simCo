// Game configuration
const config = {
  type: Phaser.AUTO,
  width: 960,
  height: 640,
  physics: {
    default: 'arcade',
    arcade: {
      gravity: { y: 0 },
      debug: false
    }
  },
  scene: [MapScene, AgentScene]
};

const game = new Phaser.Game(config);
