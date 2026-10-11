/* Feature builder: selection state, presets and the quick preview. */
(function () {
  "use strict";

  var PRESETS = {
    "preset-starter": {
      project: "My Starter Game",
      features: {
        sprint: {},
        double_jump: {},
        leaderstats: {},
        coin_collect: { tag: "Coin", stat: "Cash", amount: 5 },
        kill_brick: { tag: "KillBrick" },
        leaderboard_gui: { stat: "Cash", title: "TOP CASH" }
      }
    },
    "preset-obby": {
      project: "My Obby",
      features: {
        checkpoint: {},
        kill_brick: { tag: "KillBrick", instant_kill: true },
        void_rescue: {},
        speed_pad: {},
        jump_pad: {},
        double_jump: {},
        leaderboard_gui: { stat: "Points", title: "FURTHEST" }
      }
    },
    "preset-sim": {
      project: "My Simulator",
      features: {
        sprint: {},
        leaderstats: { stat_name: "Coins", currency_name: "Gems" },
        coin_collect: { tag: "Coin", stat: "Coins", amount: 1, respawn: 6 },
        income: { stat: "Gems", amount: 2, interval: 3, scale_with_time: true },
        leaderboard_gui: { stat: "Coins", title: "TOP COLLECTORS" },
        chat_commands: { admin_ids: "" }
      }
    }
  };

  var form = document.getElementById("builder-form");
  if (!form) {
    return;
  }

  var toggles = Array.prototype.slice.call(form.querySelectorAll(".feature-toggle"));
  var countPill = document.getElementById("count-pill");
  var selectionList = document.getElementById("selection-list");
  var previewButton = document.getElementById("preview-btn");
  var previewCard = document.getElementById("preview-card");
  var previewCode = document.getElementById("preview-code");
  var previewMeta = document.getElementById("preview-meta");

  /* ------------------------------------------------------------- helpers -- */
  function selectedToggles() {
    return toggles.filter(function (toggle) {
      return toggle.checked;
    });
  }

  function configFromForm() {
    var features = selectedToggles().map(function (toggle) {
      var card = toggle.closest(".feature");
      var params = {};
      card.querySelectorAll(".feature-body [name^='param_']").forEach(function (input) {
        if (input.type === "checkbox") {
          params[input.name.replace("param_" + toggle.value + "_", "")] = input.checked;
        } else if (input.value !== "") {
          params[input.name.replace("param_" + toggle.value + "_", "")] = input.value;
        }
      });
      return { id: toggle.value, params: params };
    });
    return {
      project_name: document.getElementById("project_name").value || "My Roblox Project",
      features: features
    };
  }

  function refreshSelection() {
    var chosen = selectedToggles();

    toggles.forEach(function (toggle) {
      var card = toggle.closest(".feature");
      if (card) {
        card.classList.toggle("selected", toggle.checked);
      }
    });

    countPill.textContent = chosen.length + " picked";
    previewButton.disabled = chosen.length === 0;
    document.getElementById("generate-btn").disabled = chosen.length === 0;

    if (!chosen.length) {
      selectionList.innerHTML =
        "Nothing picked yet. Try <strong>Sprint</strong>, <strong>Collectable coins</strong> and " +
        "<strong>Leaderstats + saving</strong> together - coins pay into the leaderboard automatically.";
      return;
    }

    selectionList.innerHTML = chosen
      .map(function (toggle, index) {
        var card = toggle.closest(".feature");
        var title = card.querySelector(".title").textContent;
        return (
          '<div class="spread" style="padding:3px 0">' +
          '<span class="small">' + (index + 1) + ". " + RF.escapeHtml(title) + "</span>" +
          '<span class="pill">' + RF.escapeHtml(card.dataset.category || "") + "</span></div>"
        );
      })
      .join("");
  }

  function setToggle(featureId, params) {
    var toggle = toggles.find(function (candidate) {
      return candidate.value === featureId;
    });
    if (!toggle) {
      return;
    }
    toggle.checked = true;
    var card = toggle.closest(".feature");
    Object.keys(params || {}).forEach(function (key) {
      var field = card.querySelector("#param_" + featureId + "_" + key);
      if (!field) {
        return;
      }
      if (field.type === "checkbox") {
        field.checked = Boolean(params[key]);
      } else {
        field.value = params[key];
      }
    });
  }

  /* ------------------------------------------------------------- events --- */
  toggles.forEach(function (toggle) {
    toggle.addEventListener("change", refreshSelection);
  });

  form.querySelectorAll(".chev").forEach(function (chevron) {
    chevron.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var card = chevron.closest(".feature");
      card.classList.toggle("open");
    });
  });

  form.querySelectorAll(".feature-head .title").forEach(function (title) {
    title.addEventListener("dblclick", function (event) {
      event.preventDefault();
      title.closest(".feature").classList.toggle("open");
    });
  });

  Object.keys(PRESETS).forEach(function (buttonId) {
    var button = document.getElementById(buttonId);
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      var preset = PRESETS[buttonId];
      toggles.forEach(function (toggle) {
        toggle.checked = false;
      });
      Object.keys(preset.features).forEach(function (featureId) {
        setToggle(featureId, preset.features[featureId]);
      });
      document.getElementById("project_name").value = preset.project;
      refreshSelection();
      RF.toast("Loaded the " + preset.project.replace("My ", "") + " preset.");
    });
  });

  var clearButton = document.getElementById("clear-all");
  if (clearButton) {
    clearButton.addEventListener("click", function () {
      toggles.forEach(function (toggle) {
        toggle.checked = false;
      });
      refreshSelection();
    });
  }

  if (previewButton) {
    previewButton.addEventListener("click", function () {
      previewButton.disabled = true;
      previewButton.textContent = "Building...";
      RF.request("/api/build", { method: "POST", body: { config: configFromForm() } }).then(function (result) {
        previewButton.disabled = false;
        previewButton.textContent = "Quick preview";
        if (!result.ok) {
          RF.toast(result.error || "Could not build that selection.", "error");
          return;
        }
        previewCard.classList.remove("hidden");
        previewMeta.textContent = result.file_count + " file(s), " + result.lines + " lines";
        previewCode.textContent = result.preview;
        if (window.RFHighlight) {
          previewCode.innerHTML = RFHighlight.highlight(result.preview);
        }
        previewCard.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  refreshSelection();
})();
