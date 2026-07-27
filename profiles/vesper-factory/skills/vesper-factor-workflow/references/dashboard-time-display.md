# Dashboard Time Display Patterns

## UTC→ET Conversion (`fmtTime`)

All timestamps in `dashboard_data.json` are UTC 24-hour format. The JS must convert them to ET 12-hour format for display.

```js
const fmtTime = (s) => {
  if (!s || s === "—") return "—";
  var m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?(.*)$/);
  if (!m) return s;
  var h = parseInt(m[1], 10);
  var min = m[2];
  var sec = m[3];
  var rest = (m[4] || "").trim();
  // Convert UTC→ET: subtract 4 (EDT) or 5 (EST)
  var isDST = (new Date()).getTimezoneOffset() === 240;
  var offset = isDST ? 4 : 5;
  h = (h - offset + 24) % 24;
  var ampm = h >= 12 ? "PM" : "AM";
  var h12 = h % 12 || 12;
  return h12 + ":" + min + (sec ? ":" + sec : "") + " " + ampm + (rest ? " " + rest : "");
};
```

**Apply `fmtTime()` to ALL renderers** that display times:
- `renderActiveJobs`: `fmtTime(j.next)`, `fmtTime(j.last)`
- `renderTodaysData`: `fmtTime(d.time)`
- `renderHeader`: `fmtTime(data.last_update)`
- SPA Jobs view renderers also need it

Use Python `str.replace()` to apply `esc(j.next)` → `fmtTime(j.next)` etc. across the file.

## Live Relative Timestamps (`relTime` + `tickRelTimes`)

For activity logs, absolute timestamps feel dead. Show relative times that tick every second:

```js
function relTime(utcStr) {
  if (!utcStr || utcStr === "—") return "—";
  var m = utcStr.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return utcStr;
  var now = new Date();
  var h = parseInt(m[1], 10), min = parseInt(m[2], 10);
  var nowH = now.getUTCHours(), nowM = now.getUTCMinutes();
  var diffMin = (nowH * 60 + nowM) - (h * 60 + min);
  if (diffMin < 0) diffMin += 1440;
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return diffMin + "m ago";
  var hrs = Math.floor(diffMin / 60);
  if (hrs < 24) return hrs + "h ago";
  return Math.floor(hrs / 24) + "d ago";
}

function tickRelTimes() {
  $$(".log-time[data-utc]").forEach(function(el) {
    el.textContent = relTime(el.getAttribute("data-utc"));
  });
}
```

**Render pattern** — store raw UTC in `data-utc` attribute:
```js
"<span class='log-time' data-utc='" + esc(a.time) + "'>" + relTime(a.time) + "</span>"
```

**Hook into 1-second tick**:
```js
setInterval(tickRelTimes, 1000);
```

## Cache Busting

When JS changes don't take effect, query params (`?v=N`) aren't reliable. **Rename the file**:
```bash
cp data-binder.js data-binder-vN.js
# Update index.html: data-binder-vN.js
```

Then the browser can't possibly serve a cached version.
