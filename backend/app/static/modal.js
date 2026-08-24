(function (global) {
  "use strict";

  function ensureRoot() {
    var root = document.getElementById("ui-modal-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "ui-modal-root";
    document.body.appendChild(root);
    return root;
  }

  function closeModal(root) {
    root.innerHTML = "";
    root.classList.remove("is-open");
    document.body.classList.remove("ui-modal-open");
  }

  function openModal(opts) {
    var root = ensureRoot();
    var title = opts.title || (opts.danger ? "Подтверждение" : "Сообщение");
    var message = opts.message || "";
    var okText = opts.okText || "OK";
    var cancelText = opts.cancelText || "Отмена";
    var showCancel = !!opts.showCancel;
    var danger = !!opts.danger;

    root.classList.add("is-open");
    document.body.classList.add("ui-modal-open");

    root.innerHTML =
      '<div class="ui-modal-backdrop" data-ui-close="1"></div>' +
      '<div class="ui-modal" role="dialog" aria-modal="true" aria-labelledby="ui-modal-title">' +
      '  <div class="ui-modal-header">' +
      '    <h2 id="ui-modal-title" class="ui-modal-title">' +
      escapeHtml(title) +
      "</h2>" +
      '    <button type="button" class="ui-modal-x" data-ui-close="1" aria-label="Закрыть">&times;</button>' +
      "  </div>" +
      '  <div class="ui-modal-body">' +
      escapeHtml(message).replace(/\\n/g, "<br>") +
      "</div>" +
      '  <div class="ui-modal-footer">' +
      (showCancel
        ? '<button type="button" class="ui-modal-btn ui-modal-btn-secondary" data-ui-cancel="1">' +
          escapeHtml(cancelText) +
          "</button>"
        : "") +
      '<button type="button" class="ui-modal-btn ' +
      (danger ? "ui-modal-btn-danger" : "ui-modal-btn-primary") +
      '" data-ui-ok="1">' +
      escapeHtml(okText) +
      "</button>" +
      "  </div>" +
      "</div>";

    return new Promise(function (resolve) {
      function finish(result) {
        root.removeEventListener("click", onClick);
        document.removeEventListener("keydown", onKey);
        closeModal(root);
        resolve(result);
      }
      function onClick(e) {
        var t = e.target;
        if (t.closest("[data-ui-ok]")) return finish(true);
        if (t.closest("[data-ui-cancel]") || t.closest("[data-ui-close]"))
          return finish(false);
      }
      function onKey(e) {
        if (e.key === "Escape") finish(false);
        if (e.key === "Enter" && !showCancel) finish(true);
      }
      root.addEventListener("click", onClick);
      document.addEventListener("keydown", onKey);
      var okBtn = root.querySelector("[data-ui-ok]");
      if (okBtn) setTimeout(function () { okBtn.focus(); }, 10);
    });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function uiAlert(message, options) {
    options = options || {};
    return openModal({
      title: options.title || "Сообщение",
      message: message,
      okText: options.okText || "Понятно",
      showCancel: false,
      danger: !!options.danger,
    }).then(function () { return true; });
  }

  function uiConfirm(message, options) {
    options = options || {};
    return openModal({
      title: options.title || "Подтверждение",
      message: message,
      okText: options.okText || "Да",
      cancelText: options.cancelText || "Отмена",
      showCancel: true,
      danger: options.danger !== false,
    });
  }

  function uiConfirmSubmit(event, message, options) {
    if (event) {
      event.preventDefault();
      if (typeof event.stopPropagation === "function") event.stopPropagation();
    }
    var form = event && event.target;
    if (!form || form.tagName !== "FORM") {
      form = event && event.target && event.target.closest && event.target.closest("form");
    }
    if (!form) return false;

    uiConfirm(message, options || { danger: true, okText: "Удалить", cancelText: "Отмена" }).then(function (ok) {
      if (!ok) return;
      // form.submit() не вызывает onsubmit снова — иначе preventDefault блокирует отправку
      HTMLFormElement.prototype.submit.call(form);
    });
    return false;
  }

  global.uiAlert = uiAlert;
  global.uiConfirm = uiConfirm;
  global.uiConfirmSubmit = uiConfirmSubmit;

  var _alert = global.alert;
  var _confirm = global.confirm;
  global.alert = function (msg) {
    try {
      uiAlert(String(msg));
    } catch (e) {
      _alert(msg);
    }
  };
  global.__nativeConfirm = _confirm;



  function safeDownload(url, event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    return fetch(url, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) {
          var msg = "Файл не найден или удалён из хранилища";
          var ct = res.headers.get("content-type") || "";
          if (ct.indexOf("application/json") !== -1) {
            return res.json().then(function (j) {
              if (j && j.detail) {
                msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
              }
              return uiAlert(msg, { title: "Файл недоступен" });
            });
          }
          return uiAlert(msg, { title: "Файл недоступен" });
        }
        var cd = res.headers.get("content-disposition") || "";
        var name = "file";
        var m = /filename\*=UTF-8''([^;]+)|filename="([^"]+)"|filename=([^;]+)/i.exec(cd);
        if (m) {
          name = decodeURIComponent((m[1] || m[2] || m[3] || "file").trim());
        }
        return res.blob().then(function (blob) {
          var a = document.createElement("a");
          var obj = URL.createObjectURL(blob);
          a.href = obj;
          a.download = name;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function () { URL.revokeObjectURL(obj); }, 2000);
        });
      })
      .catch(function (err) {
        return uiAlert("Не удалось скачать файл: " + (err && err.message ? err.message : err), {
          title: "Ошибка",
        });
      });
  }

  global.safeDownload = safeDownload;

  document.addEventListener(
    "click",
    function (e) {
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a) return;
      var href = a.getAttribute("href") || "";
      if (href.indexOf("/download") === -1) return;
      if (/^https?:\/\//i.test(href) && href.indexOf(location.origin) !== 0) return;
      if (a.classList.contains("github-link")) return;
      e.preventDefault();
      safeDownload(href, e);
    },
    true
  );

})(window);
