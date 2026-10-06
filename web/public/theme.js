(function () {
  var choice = null;
  try {
    choice = window.localStorage.getItem("mcplain-theme");
  } catch {
    choice = null;
  }
  if (choice === "light" || choice === "dark") {
    document.documentElement.classList.add("th-" + choice);
  }
})();
