/**
 * CharacterSelectScene.js
 * Scene for selecting from 20 premade characters
 */

class CharacterSelectScene extends Phaser.Scene {
    constructor() {
        super({ key: 'CharacterSelectScene' });
        this.selectedCharacterIndex = 0;
        this.characterSprites = [];
        this.charactersPerRow = 5;
        this.totalCharacters = 20;
    }

    preload() {
        // Load all 20 character spritesheets
        for (let i = 1; i <= this.totalCharacters; i++) {
            const paddedNum = i.toString().padStart(2, '0');
            this.load.spritesheet(`character_${paddedNum}`, `/assets/agents/Premade_Character_${paddedNum}.png`, {
                frameWidth: 32,
                frameHeight: 64
            });
        }
    }

    create() {
        const { width, height } = this.scale;
        
        // Background
        this.add.rectangle(width / 2, height / 2, width, height, 0x2c3e50);
        
        // Title
        this.add.text(width / 2, 50, 'Select Your Character', {
            fontSize: '32px',
            fill: '#ffffff',
            fontStyle: 'bold'
        }).setOrigin(0.5);
        
        // Instructions
        this.add.text(width / 2, 90, 'Click on a character to select, then press START', {
            fontSize: '16px',
            fill: '#ecf0f1'
        }).setOrigin(0.5);
        
        this.createCharacterGrid();
        this.createUI();
        
        // Delay character selection to ensure everything is loaded
        this.time.delayedCall(200, () => {
            // Double check that sprites are loaded before selecting
            if (this.characterSprites && this.characterSprites.length > 0) {
                // Ensure all animations are properly set up
                this.validateAnimations();
                
                const currentSelection = localStorage.getItem('selectedCharacter') || 'character_01';
                const currentIndex = parseInt(currentSelection.replace('character_', '')) - 1;
                
                // Ensure index is within bounds
                if (currentIndex >= 0 && currentIndex < this.characterSprites.length) {
                    this.selectCharacter(currentIndex);
                } else {
                    // Fallback to first character
                    this.selectCharacter(0);
                }
            } else {
                // If sprites still not loaded, try again after another delay
                this.time.delayedCall(200, () => {
                    if (this.characterSprites && this.characterSprites.length > 0) {
                        this.validateAnimations();
                        this.selectCharacter(0);
                    }
                });
            }
        });
    }

    createCharacterGrid() {
        const { width, height } = this.scale;
        const startX = width / 2 - (this.charactersPerRow * 70) / 2 + 35;
        const startY = 160;
        const spacing = 70;
        
        // Clear existing character sprites to prevent memory leaks
        if (this.characterSprites) {
            this.characterSprites.forEach(char => {
                if (char.background) {
                    char.background.removeAllListeners();
                    char.background.destroy();
                }
                if (char.sprite) {
                    char.sprite.removeAllListeners();
                    char.sprite.destroy();
                }
            });
        }
        this.characterSprites = [];
        
        for (let i = 0; i < this.totalCharacters; i++) {
            const row = Math.floor(i / this.charactersPerRow);
            const col = i % this.charactersPerRow;
            
            const x = startX + col * spacing;
            const y = startY + row * spacing;
            
            const characterKey = `character_${(i + 1).toString().padStart(2, '0')}`;
            
            // Character background
            const bg = this.add.rectangle(x, y, 60, 60, 0x34495e);
            bg.setStrokeStyle(2, 0x7f8c8d);
            bg.setInteractive({ useHandCursor: true });
            
            // Character sprite (use frame 0 - down direction)
            const sprite = this.add.sprite(x, y, characterKey, 0);
            sprite.setScale(0.75);
            sprite.setInteractive({ useHandCursor: true });
            
            // Create idle animation for this character
            const idleKey = `${characterKey}_idle`;
            try {
                if (!this.anims.exists(idleKey)) {
                    this.anims.create({
                        key: idleKey,
                        frames: [
                            { key: characterKey, frame: 0 },
                            { key: characterKey, frame: 1 }
                        ],
                        frameRate: 1, // Very slow breathing animation
                        repeat: -1,
                        yoyo: true // Go back and forth
                    });
                }
                
                // Start idle animation
                sprite.anims.play(idleKey, true);
            } catch (error) {
                // Fallback: just show frame 0
                sprite.setFrame(0);
            }
            
            // Store references
            this.characterSprites.push({
                index: i,
                background: bg,
                sprite: sprite,
                characterKey: characterKey
            });
            
            // Add click handlers
            [bg, sprite].forEach(obj => {
                obj.on('pointerdown', () => this.selectCharacter(i));
                obj.on('pointerover', () => this.hoverCharacter(i));
                obj.on('pointerout', () => this.unhoverCharacter(i));
            });
        }
    }

    createUI() {
        const { width, height } = this.scale;
        
        // Selected character display
        this.selectedCharacterText = this.add.text(width / 2, height - 120, '', {
            fontSize: '20px',
            fill: '#3498db',
            fontStyle: 'bold'
        }).setOrigin(0.5);
        
        // Determine if we're coming from the game or starting fresh
        const comingFromGame = this.scene.settings.data && this.scene.settings.data.wasActive;
        const buttonText = comingFromGame ? 'RETURN TO GAME' : 'START GAME';
        
        // Start/Return button
        this.startButton = this.add.rectangle(width / 2, height - 60, 200, 40, 0x27ae60);
        this.startButton.setStrokeStyle(2, 0x2ecc71);
        this.startButton.setInteractive({ useHandCursor: true });
        
        const startText = this.add.text(width / 2, height - 60, buttonText, {
            fontSize: '18px',
            fill: '#ffffff',
            fontStyle: 'bold'
        }).setOrigin(0.5);
        
        // Store reference for potential updates
        this.startText = startText;
        
        // Button hover effects
        this.startButton.on('pointerover', () => {
            this.startButton.setFillStyle(0x2ecc71);
            startText.setScale(1.1);
        });
        
        this.startButton.on('pointerout', () => {
            this.startButton.setFillStyle(0x27ae60);
            startText.setScale(1.0);
        });
        
        this.startButton.on('pointerdown', () => {
            this.startGame();
        });
        
        // Back to menu button
        const backButton = this.add.rectangle(80, height - 60, 120, 30, 0xe74c3c);
        backButton.setStrokeStyle(2, 0xc0392b);
        backButton.setInteractive({ useHandCursor: true });
        
        const backText = this.add.text(80, height - 60, 'BACK', {
            fontSize: '14px',
            fill: '#ffffff',
            fontStyle: 'bold'
        }).setOrigin(0.5);
        
        backButton.on('pointerover', () => {
            backButton.setFillStyle(0xc0392b);
        });
        
        backButton.on('pointerout', () => {
            backButton.setFillStyle(0xe74c3c);
        });
        
        backButton.on('pointerdown', () => {
            // Check if we're coming from an active game
            const wasActive = this.scene.settings.data && this.scene.settings.data.wasActive;
            const returnScene = this.scene.settings.data && this.scene.settings.data.returnScene;
            
            if (wasActive && returnScene) {
                // Return to the game (resume)
                this.scene.stop(); // Stop this scene
                this.scene.resume(returnScene); // Resume the paused scene
            } else if (this.scene.get('ArenaGameScene')) {
                // Arena scene exists, start it
                this.scene.start('ArenaGameScene');
            } else {
                // Hide game and return to main menu
                if (window.hideGame) {
                    window.hideGame();
                }
            }
        });
    }

    validateAnimations() {
        // Ensure all idle animations exist and are playing
        this.characterSprites.forEach((char, index) => {
            if (char && char.sprite && char.characterKey) {
                const idleKey = `${char.characterKey}_idle`;
                
                try {
                    // Create idle animation if it doesn't exist
                    if (!this.anims.exists(idleKey)) {
                        this.anims.create({
                            key: idleKey,
                            frames: [
                                { key: char.characterKey, frame: 0 },
                                { key: char.characterKey, frame: 1 }
                            ],
                            frameRate: 1,
                            repeat: -1,
                            yoyo: true
                        });
                    }
                    
                    // Start idle animation if sprite is not already animating
                    if (char.sprite.anims && !char.sprite.anims.isPlaying) {
                        char.sprite.anims.play(idleKey, true);
                    }
                } catch (error) {
                }
            }
        });
    }

    selectCharacter(index) {
        // Safety check
        if (!this.characterSprites || !this.characterSprites[index]) {
            return;
        }
        
        // Clear previous selection and return to idle animations
        this.characterSprites.forEach((char, i) => {
            if (char && char.background && char.sprite) {
                char.background.setFillStyle(0x34495e);
                char.background.setStrokeStyle(2, 0x7f8c8d);
                
                // Return previously selected character to idle animation
                if (i === this.selectedCharacterIndex && i !== index && char.sprite.anims) {
                    const idleKey = `${char.characterKey}_idle`;
                    if (this.anims.exists(idleKey)) {
                        char.sprite.anims.play(idleKey, true);
                    }
                }
            }
        });
        
        // Highlight selected character
        const selected = this.characterSprites[index];
        
        // Safety check for selected character
        if (!selected || !selected.background || !selected.sprite) {
            return;
        }
        
        selected.background.setFillStyle(0x3498db);
        selected.background.setStrokeStyle(3, 0x2980b9);
        
        // Create simple 4-frame animation using row 0, frames 0,1,2,3
        const turnaroundKey = `${selected.characterKey}_simple`;
        
        if (!this.anims.exists(turnaroundKey)) {
            this.anims.create({
                key: turnaroundKey,
                frames: [
                    { key: selected.characterKey, frame: 0 },
                    { key: selected.characterKey, frame: 1 },
                    { key: selected.characterKey, frame: 2 },
                    { key: selected.characterKey, frame: 3 },
                ],
                frameRate: 3, // quicker turnaround
                repeat: -1,
            });
        }
        
        // Check if sprite and animation manager exist before playing
        if (selected.sprite && selected.sprite.anims && this.anims.exists(turnaroundKey)) {
            selected.sprite.anims.play(turnaroundKey, true);
        }
        
        this.selectedCharacterIndex = index;
        this.selectedCharacterText.setText(`Selected: Character ${(index + 1).toString().padStart(2, '0')}`);
        
        // Save selection to localStorage
        localStorage.setItem('selectedCharacter', selected.characterKey);
    }

    hoverCharacter(index) {
        // Safety check
        if (!this.characterSprites || !this.characterSprites[index]) {
            return;
        }
        
        const char = this.characterSprites[index];
        
        // Safety check for character
        if (!char || !char.background || !char.sprite) {
            return;
        }
        
        if (index !== this.selectedCharacterIndex) {
            char.background.setFillStyle(0x5dade2);
            
            // Create hover turnaround animation
            const hoverKey = `${char.characterKey}_hover`;
            
            // Always try to create the animation (it will be ignored if it exists)
            try {
                if (!this.anims.exists(hoverKey)) {
                    this.anims.create({
                        key: hoverKey,
                        frames: [
                            { key: char.characterKey, frame: 0 },
                            { key: char.characterKey, frame: 1 },
                            { key: char.characterKey, frame: 2 },
                            { key: char.characterKey, frame: 3 },
                        ],
                        frameRate: 4, // quick hover turnaround
                        repeat: -1,
                    });
                }
                
                // Check if sprite and animation manager exist before playing
                if (char.sprite && char.sprite.anims && this.anims.exists(hoverKey)) {
                    char.sprite.anims.play(hoverKey, true);
                }
            } catch (error) {
                // Fallback: just show the blue background without animation
            }
        }
    }

    unhoverCharacter(index) {
        // Safety check
        if (!this.characterSprites || !this.characterSprites[index]) {
            return;
        }
        
        const char = this.characterSprites[index];
        
        // Safety check for character
        if (!char || !char.background || !char.sprite) {
            return;
        }
        
        if (index !== this.selectedCharacterIndex) {
            char.background.setFillStyle(0x34495e);
            
            // Return to idle animation instead of stopping
            try {
                if (char.sprite && char.sprite.anims) {
                    const idleKey = `${char.characterKey}_idle`;
                    if (this.anims.exists(idleKey)) {
                        char.sprite.anims.play(idleKey, true);
                    } else {
                        // Fallback: create idle animation if it doesn't exist
                        this.anims.create({
                            key: idleKey,
                            frames: [
                                { key: char.characterKey, frame: 0 },
                                { key: char.characterKey, frame: 1 }
                            ],
                            frameRate: 1,
                            repeat: -1,
                            yoyo: true
                        });
                        char.sprite.anims.play(idleKey, true);
                    }
                }
            } catch (error) {
                // Fallback: just set frame 0
                if (char.sprite) {
                    char.sprite.setFrame(0);
                }
            }
        }
    }

    startGame() {
        // Get the character key for the selected character
        const selected = this.characterSprites[this.selectedCharacterIndex];
        const selectedKey = selected ? selected.characterKey : 'character_01';
        
        
        // Save to localStorage and potentially Firebase
        localStorage.setItem('selectedCharacter', selectedKey);
        
        // Check if we're returning to an active game or starting fresh
        const wasActive = this.scene.settings.data && this.scene.settings.data.wasActive;
        const returnScene = this.scene.settings.data && this.scene.settings.data.returnScene;
        
        try {
            if (wasActive && returnScene) {
                // Return to the game (resume)
                this.scene.stop(); // Stop this scene
                this.scene.resume(returnScene); // Resume the paused scene
            } else {
                // Starting fresh
                this.scene.start('ArenaGameScene');
            }
        } catch (error) {
            // Fallback: just start the arena scene
            this.scene.start('ArenaGameScene');
        }
    }
}

// Export the scene for use
window.CharacterSelectScene = CharacterSelectScene;