// Map Scene
class MapScene extends Phaser.Scene {
  constructor() {
    super({ key: 'MapScene' });
  }

  preload() {
    // Load the tileset image
    this.load.image('Room_Builder', 'phaser/assets/Room_Builder_16x16.png');
    
    // Load the tilemap JSON
    this.load.tilemapTiledJSON('map', 'phaser/assets/simCoSandbox.json');
  }

  create() {
    // Create the tilemap
    const map = this.make.tilemap({ key: 'map' });
    
    // Add the tileset to the map
    const tileset = map.addTilesetImage('Room_Builder_16x16', 'Room_Builder');
    
    // Create tile layers
    const floorLayer = map.createLayer('Floor', tileset, 0, 0);
    const wallLayer = map.createLayer('Wall', tileset, 0, 0);
    
    // Set the camera to follow the map
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
    this.physics.world.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
  }
}




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
  scene: [MapScene]
};

const game = new Phaser.Game(config);
