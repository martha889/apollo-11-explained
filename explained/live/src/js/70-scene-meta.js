  var SCENE_TITLE = { launch: "Launch and climb", "earth-orbit": "Earth orbit", cislunar: "Earth–Moon space", "lunar-orbit": "Lunar orbit", descent: "Powered descent", surface: "On the surface", ascent: "Ascent from the Moon", rendezvous: "Rendezvous and docking", entry: "Entry" };
  var SCENE_FRAME = {};
  for (var sk in T) SCENE_FRAME[sk] = T[sk].frame || "Tranquility Base";

  (function () {
    function wrapScene(name, orig) {
      return function (g, dt) {
        var r = orig(g, dt);
        if (typeof HUD !== "undefined" && HUD && HUD.strips) {
          try {
            HUD.strips(name, g);
          } catch (err) {
            document.documentElement.setAttribute("data-hud-error", (err && err.message) ? err.message : String(err));
          }
        }
        return r;
      };
    }
    for (var sName in SCENES) {
      if (Object.prototype.hasOwnProperty.call(SCENES, sName) && typeof SCENES[sName] === "function") {
        SCENES[sName] = wrapScene(sName, SCENES[sName]);
      }
    }
  })();
