/* Snippet library: highlight, add your own, delete your own. */
(function () {
  "use strict";

  RF.highlightAll(".code");

  var form = document.getElementById("save-form");
  var toggle = document.getElementById("toggle-save-form");
  var cancel = document.getElementById("cancel-snippet-btn");

  if (toggle && form) {
    toggle.addEventListener("click", function () {
      form.classList.toggle("hidden");
      if (!form.classList.contains("hidden")) {
        document.getElementById("snip-title").focus();
      }
    });
  }
  if (cancel && form) {
    cancel.addEventListener("click", function () {
      form.classList.add("hidden");
    });
  }

  var saveButton = document.getElementById("save-snippet-btn");
  if (saveButton) {
    saveButton.addEventListener("click", function () {
      var payload = {
        title: document.getElementById("snip-title").value,
        category: document.getElementById("snip-category").value || "My snippets",
        summary: document.getElementById("snip-summary").value,
        tags: document.getElementById("snip-tags").value,
        code: document.getElementById("snip-code").value
      };
      RF.request("/api/snippets", { method: "POST", body: payload }).then(function (result) {
        if (!result.ok) {
          RF.toast(result.error || "Could not save that snippet.", "error");
          return;
        }
        RF.toast(result.message || "Snippet saved.");
        setTimeout(function () {
          location.reload();
        }, 700);
      });
    });
  }

  document.querySelectorAll("[data-delete-snippet]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!confirm("Delete this snippet?")) {
        return;
      }
      RF.request("/api/snippets/" + button.dataset.deleteSnippet, { method: "DELETE" }).then(function (result) {
        if (!result.ok) {
          RF.toast(result.error || "Could not delete that snippet.", "error");
          return;
        }
        var card = button.closest(".snippet");
        if (card) {
          card.remove();
        }
        RF.toast("Snippet deleted.");
      });
    });
  });
})();
