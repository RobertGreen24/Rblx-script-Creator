/* RobloxForge - shared front-end helpers (no dependencies) */
window.RF = (function () {
  "use strict";

  /* ------------------------------------------------------------ fetches -- */
  function request(url, options) {
    options = options || {};
    var init = {
      method: options.method || "GET",
      headers: { Accept: "application/json" }
    };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return fetch(url, init)
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return { ok: false, error: "The server sent back something unexpected." };
          })
          .then(function (data) {
            data.status = response.status;
            return data;
          });
      })
      .catch(function () {
        return { ok: false, error: "Could not reach the server. Is it still running?" };
      });
  }

  /* -------------------------------------------------------------- toasts -- */
  function toast(message, kind) {
    var area = document.getElementById("flash-area");
    if (!area) {
      return;
    }
    var node = document.createElement("div");
    node.className = "flash" + (kind === "error" ? " error" : "");
    node.textContent = message;
    area.appendChild(node);
    setTimeout(function () {
      node.style.transition = "opacity .3s ease, transform .3s ease";
      node.style.opacity = "0";
      node.style.transform = "translateX(14px)";
      setTimeout(function () {
        node.remove();
      }, 320);
    }, kind === "error" ? 5200 : 3200);
  }

  /* --------------------------------------------------------------- copy --- */
  function copyFrom(selector) {
    var source = document.querySelector(selector);
    if (!source) {
      return;
    }
    var text = "value" in source && source.tagName === "TEXTAREA" ? source.value : source.textContent;
    var done = function () {
      toast("Copied to clipboard.");
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    var helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "readonly");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    try {
      document.execCommand("copy");
      done();
    } catch (error) {
      toast("Copy failed - select the code and press Ctrl+C.", "error");
    }
    helper.remove();
  }

  function attachCopyButtons(root) {
    (root || document).querySelectorAll("[data-copy]").forEach(function (button) {
      if (button.dataset.copyBound) {
        return;
      }
      button.dataset.copyBound = "1";
      button.addEventListener("click", function () {
        copyFrom(button.dataset.copy);
      });
    });
  }

  /* --------------------------------------------------------------- misc --- */
  function highlightAll(selector) {
    if (!window.RFHighlight) {
      return;
    }
    document.querySelectorAll(selector || "pre.code").forEach(function (node) {
      node.innerHTML = RFHighlight.highlight(node.textContent);
    });
  }

  function debounce(fn, wait) {
    var timer;
    return function () {
      var args = arguments;
      var context = this;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(context, args);
      }, wait || 200);
    };
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  document.addEventListener("DOMContentLoaded", function () {
    attachCopyButtons();
  });

  return {
    request: request,
    toast: toast,
    copy: copyFrom,
    attachCopyButtons: attachCopyButtons,
    highlightAll: highlightAll,
    debounce: debounce,
    escapeHtml: escapeHtml
  };
})();
