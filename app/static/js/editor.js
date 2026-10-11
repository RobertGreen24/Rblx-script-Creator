/* Luau editor: highlighting overlay, indentation, stats, analyser and saving. */
(function () {
  "use strict";

  var editor = document.getElementById("editor");
  if (!editor) {
    return;
  }

  var textarea = document.getElementById("code-input");
  var layer = document.getElementById("highlight-layer");
  var gutter = document.getElementById("gutter");
  var cursorPill = document.getElementById("cursor-pill");
  var statLines = document.getElementById("stat-lines");
  var statChars = document.getElementById("stat-chars");
  var statFunctions = document.getElementById("stat-functions");
  var statSaved = document.getElementById("stat-saved");
  var heading = document.getElementById("editor-heading");
  var filenameLabel = document.getElementById("filename-label");
  var projectName = document.getElementById("project-name");
  var projectDesc = document.getElementById("project-desc");
  var typeSelect = document.getElementById("script-type");
  var typePill = document.getElementById("type-pill");
  var projectId = window.RF_PROJECT_ID || null;

  var INDENT = "    ";

  /* ------------------------------------------------------------ rendering */
  function render() {
    var code = textarea.value;
    layer.innerHTML = window.RFHighlight ? RFHighlight.highlight(code) + "\n" : RF.escapeHtml(code) + "\n";

    var lines = code.split("\n").length;
    if (gutter.childElementCount !== lines) {
      var numbers = [];
      for (var index = 1; index <= lines; index += 1) {
        numbers.push("<span>" + index + "</span>");
      }
      gutter.innerHTML = numbers.join("");
    }

    statLines.textContent = lines;
    statChars.textContent = code.length;
    var functions = (code.match(/\bfunction\b/g) || []).length;
    statFunctions.textContent = functions;
    syncScroll();
  }

  function syncScroll() {
    layer.scrollTop = textarea.scrollTop;
    layer.scrollLeft = textarea.scrollLeft;
    gutter.scrollTop = textarea.scrollTop;
  }

  function updateCursor() {
    var upto = textarea.value.slice(0, textarea.selectionStart);
    var line = upto.split("\n").length;
    var column = upto.length - upto.lastIndexOf("\n");
    cursorPill.textContent = "Ln " + line + ", Col " + column;
  }

  /* -------------------------------------------------------------- editing */
  function insert(text, selectionOffset) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var value = textarea.value;
    textarea.value = value.slice(0, start) + text + value.slice(end);
    var caret = start + (selectionOffset === undefined ? text.length : selectionOffset);
    textarea.setSelectionRange(caret, caret);
    render();
    updateCursor();
  }

  textarea.addEventListener("input", render);
  textarea.addEventListener("scroll", syncScroll);
  textarea.addEventListener("click", updateCursor);
  textarea.addEventListener("keyup", updateCursor);
  textarea.addEventListener("keydown", function (event) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var value = textarea.value;

    // Tab / Shift+Tab: indent or outdent, whole-line aware.
    if (event.key === "Tab") {
      event.preventDefault();
      var lineStart = value.lastIndexOf("\n", start - 1) + 1;
      var multiline = value.slice(start, end).indexOf("\n") !== -1 || value.slice(lineStart, end).indexOf("\n") !== -1;

      if (!event.shiftKey && !multiline && start === end) {
        insert(INDENT);
        return;
      }

      var lineEnd = value.indexOf("\n", end) === -1 ? value.length : value.indexOf("\n", end);
      var block = value.slice(lineStart, lineEnd);
      var shifted = block
        .split("\n")
        .map(function (line, index) {
          if (event.shiftKey) {
            return line.replace(/^ {1,4}/, "").replace(/^\t/, "");
          }
          return INDENT + line;
        })
        .join("\n");

      textarea.value = value.slice(0, lineStart) + shifted + value.slice(lineEnd);
      textarea.setSelectionRange(lineStart, lineStart + shifted.length);
      render();
      return;
    }

    // Enter keeps the current indentation, and adds one level after "do/for/if".
    if (event.key === "Enter" && start === end) {
      event.preventDefault();
      var currentLineStart = value.lastIndexOf("\n", start - 1) + 1;
      var currentLine = value.slice(currentLineStart, start);
      var indentMatch = currentLine.match(/^[ \t]*/);
      var indent = indentMatch ? indentMatch[0] : "";
      var extra = /(\bthen\b|\bdo\b|\bfunction\b|\brepeat\b|\belse\b|\(|,)\s*$/.test(currentLine) ? INDENT : "";

      // Keep blank-line-with-indent from compounding forever.
      if (extra && currentLine.trim() === "") {
        extra = "";
      }
      insert("\n" + indent + extra);
      return;
    }

    // Ctrl/Cmd+S saves.
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      save();
    }
  });

  /* ------------------------------------------------------------- starters */
  var starterHolder = document.getElementById("starter-buttons");
  RF.request("/api/snippets").then(function (result) {
    if (!result.ok || !starterHolder) {
      return;
    }
    var builtin = result.snippets.filter(function (snippet) {
      return snippet.builtin;
    }).slice(0, 5);

    builtin.forEach(function (snippet, index) {
      var existing = starterHolder.children[index];
      if (existing) {
        existing.textContent = snippet.title;
        existing.dataset.starter = index;
      }
    });

    starterHolder.addEventListener("click", function (event) {
      var button = event.target.closest("[data-starter]");
      if (!button) {
        return;
      }
      var snippet = builtin[Number(button.dataset.starter)];
      if (!snippet) {
        return;
      }
      if (textarea.value.trim() && !confirm("Replace the current code with this template?")) {
        return;
      }
      textarea.value = snippet.code.replace(/\s+$/, "") + "\n";
      if (typeSelect) {
        typeSelect.value = snippet.script_type || "server";
        typeSelect.dispatchEvent(new Event("change"));
      }
      render();
      RF.toast("Loaded template: " + snippet.title);
    });
  });

  /* ------------------------------------------------------- saved projects */
  var loader = document.getElementById("load-project");
  RF.request("/api/projects").then(function (result) {
    if (!result.ok || !loader) {
      return;
    }
    result.projects.forEach(function (project) {
      var option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name;
      loader.appendChild(option);
    });
  });

  if (loader) {
    loader.addEventListener("change", function () {
      if (!loader.value) {
        return;
      }
      RF.request("/api/projects/" + loader.value).then(function (result) {
        if (!result.ok) {
          RF.toast(result.error || "Could not load that project.", "error");
          return;
        }
        var project = result.project;
        projectId = project.id;
        window.RF_PROJECT_ID = project.id;
        textarea.value = project.code;
        projectName.value = project.name;
        projectDesc.value = project.description || "";
        typeSelect.value = project.script_type || "server";
        typeSelect.dispatchEvent(new Event("change"));
        heading.textContent = project.name;
        render();
        RF.toast("Loaded '" + project.name + "'.");
      });
    });
  }

  /* -------------------------------------------------------------- saving  */
  function save() {
    var code = textarea.value;
    var payload = {
      name: projectName.value || "Untitled script",
      description: projectDesc.value,
      script_type: typeSelect.value,
      code: code,
      source: "editor"
    };

    var promise = projectId
      ? RF.request("/api/projects/" + projectId, { method: "PATCH", body: payload })
      : RF.request("/api/projects", { method: "POST", body: payload });

    promise.then(function (result) {
      if (!result.ok) {
        RF.toast(result.error || "Could not save.", "error");
        return;
      }
      if (!projectId && result.id) {
        projectId = result.id;
        window.RF_PROJECT_ID = result.id;
      }
      heading.textContent = payload.name;
      statSaved.textContent = "just now";
      RF.toast(result.message || "Saved.");
      if (window.history && window.history.replaceState) {
        window.history.replaceState({}, "", "/editor?project=" + projectId);
      }
    });
  }

  ["save-btn", "save-btn-2"].forEach(function (id) {
    var button = document.getElementById(id);
    if (button) {
      button.addEventListener("click", save);
    }
  });

  var newButton = document.getElementById("new-btn");
  if (newButton) {
    newButton.addEventListener("click", function () {
      if (textarea.value.trim() && !confirm("Clear the editor? Unsaved changes will be lost.")) {
        return;
      }
      projectId = null;
      window.RF_PROJECT_ID = null;
      textarea.value = "";
      projectName.value = "";
      projectDesc.value = "";
      heading.textContent = "Untitled script";
      render();
    });
  }

  /* ------------------------------------------------------------ filename  */
  function refreshFilename() {
    var base = (projectName.value || "script").trim().replace(/\s+/g, "") || "script";
    var suffix = { server: ".server.luau", client: ".client.luau", module: ".luau" }[typeSelect.value] || ".luau";
    filenameLabel.textContent = base + suffix;
    typePill.textContent = typeSelect.value.charAt(0).toUpperCase() + typeSelect.value.slice(1);
    typePill.className =
      "pill " + (typeSelect.value === "client" ? "mint" : typeSelect.value === "module" ? "violet" : "accent");
  }
  projectName.addEventListener("input", RF.debounce(refreshFilename, 200));
  typeSelect.addEventListener("change", refreshFilename);

  /* --------------------------------------------------------------- tidy   */
  var formatButton = document.getElementById("format-btn");
  if (formatButton) {
    formatButton.addEventListener("click", function () {
      var cleaned = textarea.value
        .replace(/\r\n/g, "\n")
        .replace(/[ \t]+$/gm, "")
        .replace(/\n{4,}/g, "\n\n\n")
        .replace(/\s+$/, "");
      textarea.value = cleaned + "\n";
      render();
      RF.toast("Trailing whitespace cleaned up. Indentation left as-is.");
    });
  }

  /* ------------------------------------------------------------ analyser  */
  var RULES = [
    {
      pattern: /\bwait\s*\(/g,
      level: "warn",
      message: "wait() is deprecated - use task.wait() so the delay is accurate."
    },
    {
      pattern: /\bspawn\s*\(/g,
      level: "warn",
      message: "spawn() does not pass errors up - use task.spawn() instead."
    },
    {
      pattern: /:connect\s*\(/g,
      level: "error",
      message: ":connect() is the old spelling - use :Connect() or nothing will fire."
    },
    {
      pattern: /:Disconnect\(/g,
      level: "info",
      message: "Check every :Disconnect() still has a matching connection variable."
    },
    {
      pattern: /game\.Players\.LocalPlayer/g,
      level: "info",
      message: "On the server, LocalPlayer is nil. Guard it with RunService:IsClient()."
    },
    {
      pattern: /DataStoreService:GetDataStore\(/g,
      level: "info",
      message: "DataStore calls should live inside pcall, and only on the server."
    },
    {
      pattern: /\.Changed:Connect\(\s*function\s*\(\s*\)/g,
      level: "info",
      message: "Value.Changed passes the new value - accept a parameter if you need it."
    },
    {
      pattern: /workspace:GetChildren\(\)\s*do/g,
      level: "info",
      message: "Consider GetDescendants() or CollectionService tags for large maps."
    },
    {
      pattern: /math\.random\(\)\s*==/g,
      level: "warn",
      message: "Floating point equality on math.random() will almost never be true."
    },
    {
      pattern: /WaitForChild\(\s*"[^"]+"\s*\)/g,
      level: "info",
      message: "A missing WaitForChild can hang forever - a timeout keeps your script alive."
    }
  ];

  function analyse() {
    var code = textarea.value;
    var lines = code.split("\n");
    var findings = [];

    RULES.forEach(function (rule) {
      lines.forEach(function (line, index) {
        if (line.trim().indexOf("--") === 0) {
          return;
        }
        rule.pattern.lastIndex = 0;
        if (rule.pattern.test(line)) {
          findings.push({ line: index + 1, level: rule.level, message: rule.message });
        }
      });
    });

    var summary = {
      remotes: (code.match(/RemoteEvent|RemoteFunction/g) || []).length,
      waits: (code.match(/task\.wait|WaitForChild|:Wait\(/g) || []).length,
      pcalls: (code.match(/\bpcall\b|\bxpcall\b/g) || []).length,
      loops: (code.match(/\bwhile\b|\bfor\b/g) || []).length,
      connections: (code.match(/:Connect\(/g) || []).length
    };

    var pill = document.getElementById("analyse-pill");
    var target = document.getElementById("analyse-results");
    var errors = findings.filter(function (f) {
      return f.level === "error";
    }).length;
    var warns = findings.filter(function (f) {
      return f.level === "warn";
    }).length;

    pill.textContent = findings.length ? findings.length + " note(s)" : "clean";
    pill.className = "pill " + (errors ? "accent" : warns ? "amber" : "mint");

    var header =
      '<div class="grid grid-4" style="margin-bottom:14px; gap:8px">' +
      ["lines " + lines.length, "connections " + summary.connections, "waits " + summary.waits, "pcall " + summary.pcalls, "loops " + summary.loops]
        .map(function (text) {
          return '<span class="pill">' + text + "</span>";
        })
        .join("") +
      "</div>";

    if (!findings.length) {
      target.innerHTML = header + '<div class="muted small">Nothing jumped out. Nice and tidy.</div>';
      return;
    }

    var colours = { error: "accent", warn: "amber", info: "" };
    target.innerHTML =
      header +
      findings
        .slice(0, 40)
        .map(function (finding) {
          return (
            '<div style="padding:6px 0; border-top:1px solid var(--border-soft)">' +
            '<span class="pill ' + (colours[finding.level] || "") + '">line ' + finding.line + "</span> " +
            '<span class="muted">' + RF.escapeHtml(finding.message) + "</span></div>"
          );
        })
        .join("") +
      (findings.length > 40 ? '<div class="faint small">...and ' + (findings.length - 40) + " more.</div>" : "");
  }

  var analyseButton = document.getElementById("analyse-btn");
  if (analyseButton) {
    analyseButton.addEventListener("click", analyse);
  }

  // Live re-analysis once the user has asked for it at least once.
  var autoAnalyse = false;
  if (analyseButton) {
    analyseButton.addEventListener("click", function () {
      autoAnalyse = true;
    });
  }
  textarea.addEventListener(
    "input",
    RF.debounce(function () {
      if (autoAnalyse) {
        analyse();
      }
    }, 700)
  );

  refreshFilename();
  render();
  updateCursor();
})();
