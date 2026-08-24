(function (global) {
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch (e) {}
    document.body.removeChild(ta);
  }

  function flashIcon(btn) {
    if (!btn) return;
    var icon = btn.querySelector("i");
    if (!icon) return;
    var prevClass = icon.className;
    icon.className = "fas fa-check";
    btn.classList.add("copied");
    btn.setAttribute("title", "Скопировано");
    setTimeout(function () {
      icon.className = prevClass;
      btn.classList.remove("copied");
      btn.setAttribute("title", "Копировать");
    }, 1500);
  }

  global.copyText = function (text, btn) {
    if (text == null) text = "";
    text = String(text);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          flashIcon(btn);
        },
        function () {
          fallbackCopy(text);
          flashIcon(btn);
        }
      );
    } else {
      fallbackCopy(text);
      flashIcon(btn);
    }
  };
})(window);
