// Setup payload saved from /setup route.
try {
  const rawSetup = localStorage.getItem('simco_setup');
  window.SIMCO_SETUP = rawSetup ? JSON.parse(rawSetup) : null;
} catch (err) {
  window.SIMCO_SETUP = null;
}

window.SIMCO_RUN_VIEW = null;

async function bootstrapGame() {
  const params = new URLSearchParams(window.location.search);
  const standaloneMode = params.get('standalone') === '1';
  const runId = standaloneMode
    ? ''
    : (params.get('run_id') || '').trim();

  if (standaloneMode) {
    localStorage.removeItem('simco_selected_run_id');
  }

  if (runId) {
    try {
      const res = await fetch(`/api/run-view?run_id=${encodeURIComponent(runId)}`);
      const data = await res.json();
      if (res.ok) {
        window.SIMCO_RUN_VIEW = data;
        localStorage.setItem('simco_selected_run_id', runId);
      } else {
        console.warn('Could not load historical run view:', data.error || res.statusText);
      }
    } catch (err) {
      console.warn('Could not load historical run view:', err);
    }
  }

  // Game configuration
  const config = {
    type: Phaser.AUTO,
    parent: 'game-container',
    width: 960,
    height: 640,
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
      width: 960,
      height: 640
    },
    physics: {
      default: 'arcade',
      arcade: {
        gravity: { y: 0 },
        debug: false
      }
    },
    scene: [MapScene, AgentScene]
  };

  window.SIMCO_GAME = new Phaser.Game(config);
}

bootstrapGame();
