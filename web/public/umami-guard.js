(function () {
  var ID_SEGMENT = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_-]{20,})$/i;
  var LOCALES = { en: true, fr: true };
  var HIDDEN = { admin: true, account: true };
  var KEPT = ["website", "hostname", "language", "screen", "title"];

  function cleanPath(pathname) {
    var segments = pathname.split("/");
    for (var index = 0; index < segments.length; index += 1) {
      if (ID_SEGMENT.test(segments[index])) {
        segments[index] = "[id]";
      }
    }
    return segments.join("/") || "/";
  }

  function hidden(pathname) {
    var segments = pathname.split("/").filter(function (segment) {
      return segment !== "";
    });
    if (segments.length > 0 && LOCALES[segments[0]] === true) {
      segments = segments.slice(1);
    }
    return segments.length > 0 && HIDDEN[segments[0]] === true;
  }

  function parse(value) {
    try {
      return new URL(value, window.location.href);
    } catch {
      return null;
    }
  }

  function privacyAsked() {
    return window.navigator.globalPrivacyControl === true;
  }

  window.mcplainUmamiBeforeSend = function (type, payload) {
    if (type !== "event" || !payload || payload.name !== undefined || payload.data !== undefined || privacyAsked()) {
      return null;
    }
    var page = parse(payload.url || window.location.href);
    if (page === null || page.host !== window.location.host || hidden(page.pathname)) {
      return null;
    }
    var clean = { url: cleanPath(page.pathname) };
    for (var index = 0; index < KEPT.length; index += 1) {
      if (typeof payload[KEPT[index]] === "string") {
        clean[KEPT[index]] = payload[KEPT[index]];
      }
    }
    if (typeof payload.referrer === "string" && payload.referrer !== "") {
      var referrer = parse(payload.referrer);
      if (referrer !== null && referrer.host === window.location.host) {
        clean.referrer = cleanPath(referrer.pathname);
      } else if (referrer !== null && (referrer.protocol === "https:" || referrer.protocol === "http:")) {
        clean.referrer = referrer.origin;
      }
    }
    return clean;
  };
})();
