/* Leadbell first-touch source. Include once on every public page:
 *   <script src="/leadbell/source.js"></script>
 * The first time a visitor arrives, it remembers where they came from (utm_* tags, ?ref=, the landing
 * page and the referring site's host) in localStorage under "leadbell_source". Nothing is sent anywhere
 * by this script. Read it with window.leadbellSource() and include it as "source" in your form or sign-up.
 */
(function () {
  var KEY = "leadbell_source";
  try {
    if (!localStorage.getItem(KEY)) {
      var q = new URLSearchParams(location.search), src = {};
      ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref"].forEach(function (k) {
        var v = q.get(k);
        if (v) src[k] = v.slice(0, 80);
      });
      src.landing = location.pathname.slice(0, 80);
      if (document.referrer) {
        var host = new URL(document.referrer).host;
        if (host && host !== location.host) src.referrer = host.slice(0, 80);
      }
      localStorage.setItem(KEY, JSON.stringify(src));
    }
  } catch (e) { /* private mode or storage blocked: no source, nothing breaks */ }
  window.leadbellSource = function () {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  };
})();
