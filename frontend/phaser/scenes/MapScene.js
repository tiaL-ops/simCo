// Map Scene
class MapScene extends Phaser.Scene {
  constructor() {
    super({ key: 'MapScene' });
  }

  preload() {
    // Load the tileset image
    this.load.image('Room_Builder', 'phaser/assets/Room_Builder_16x16.png');
    this.load.image('Museum_Shadow', 'phaser/assets/Museum_Black_Shadow_Singles_56.png');
    
    // Load the tilemap JSON
    this.load.tilemapTiledJSON('map', 'phaser/assets/simCoSandbox.json');
  }

  create() {
    // Create the tilemap
    const map = this.make.tilemap({ key: 'map' });
    
    // Add tilesets used by the map
    const roomBuilderTileset = map.addTilesetImage('Room_Builder_16x16', 'Room_Builder');
    const museumShadowTileset = map.addTilesetImage('Museum_Black_Shadow_Singles_56', 'Museum_Shadow');
    const tilesets = [roomBuilderTileset, museumShadowTileset].filter(Boolean);
    
    // Create tile layers
    const floorLayer = map.createLayer('Floor', tilesets, 0, 0);
    const wallLayer = map.createLayer('Wall', tilesets, 0, 0);
    const moneyLayer = map.createLayer('Money', tilesets, 0, 0);

    if (moneyLayer) {
      moneyLayer.setDepth(30);
      moneyLayer.setCollisionByExclusion([-1, 0]);
      console.log('Money layer displayed using Museum_Black_Shadow_Singles_56 tileset');
    }
    
    // Set the camera to follow the map
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
    this.physics.world.setBounds(0, 0, map.widthInPixels, map.heightInPixels);

    // Store map and wall layer for collision detection
    this.mapRef = map;
    this.wallLayer = wallLayer;
    
    // Set collision on wall layer (tiles with index > 0 are walls)
    wallLayer.setCollisionByExclusion([-1, 0]);

    // Extract room objects from RoomObject layer
    const roomLayer = map.getObjectLayer('RoomObject');
    const rooms = {};
    if (roomLayer) {
      roomLayer.objects.forEach(obj => {
        if (obj.name) {
          rooms[obj.name] = {
            minX: obj.x,
            maxX: obj.x + obj.width,
            minY: obj.y,
            maxY: obj.y + obj.height
          };
          console.log(`Room "${obj.name}" from JSON: x=${obj.x.toFixed(2)}, y=${obj.y.toFixed(2)}, w=${obj.width.toFixed(2)}, h=${obj.height.toFixed(2)}`);
        }
      });
    }

    // Launch AgentScene once on top, passing map reference and rooms
    this.scene.launch('AgentScene', { mapScene: this, map: map, wallLayer: wallLayer, moneyLayer: moneyLayer, rooms: rooms });
  }
}
