    (function () {
      var KEY = "arw_computer_notify";
      var CURSOR = "arw_appeared_cursor";
      var CLIENT_API_REVISION = 2;
      var wired = false;
      var usingDesktopNotify = false;
      var canAfterId = true;
      var desktopApi = null;
      var desktopRuntimeMode = null;
      var bootTimer = null;
      function $(id) { return document.getElementById(id); }
      function enabled() { return localStorage.getItem(KEY) === "1"; }
      var HINT_DEFAULT = "需要浏览器通知权限。";
      var HINT_DENIED = "浏览器已关闭此网站的通知。请在地址栏允许通知后刷新页面。";
      function setStatus(text, warn) {
        var node = $("computer-notify-status");
        if (!node) return;
        node.textContent = text || "";
        if (warn) node.classList.add("is-warn");
        else node.classList.remove("is-warn");
      }
      function permissionState() {
        if (typeof Notification === "undefined") return "unsupported";
        return Notification.permission;
      }
      function askPermission(onGranted) {
        var state = permissionState();
        if (state === "unsupported") {
          setStatus("当前浏览器不支持网页通知。可用桌面包或 Bark。", true);
          return;
        }
        if (state === "granted") {
          if (onGranted) onGranted();
          return;
        }
        if (state === "denied") {
          setStatus(HINT_DENIED, true);
          return;
        }
        Notification.requestPermission().then(function (perm) {
          if (perm === "granted") {
            if (onGranted) onGranted();
            return;
          }
          setStatus(perm === "denied" ? HINT_DENIED : HINT_DEFAULT, true);
        }).catch(function () {
          setStatus(HINT_DENIED, true);
        });
      }
      function showBanner(text) {
        var el = $("compat-banner");
        if (!el || !text) return;
        el.hidden = false;
        el.textContent = text;
      }
      function isDesktopShell() {
        return !!(desktopApi || document.documentElement.classList.contains("desktop") || window.pywebview);
      }
      function showUpdate(latest, url) {
        var nav = $("nav-settings");
        if (nav) {
          if (latest) {
            nav.classList.add("has-update");
            nav.setAttribute("aria-label", "设置，有新版本 " + latest);
          } else {
            nav.classList.remove("has-update");
            nav.removeAttribute("aria-label");
          }
        }
        var settings = $(isDesktopShell() ? "desktop-update" : "server-update");
        if (settings) {
          if (latest) {
            if (url) settings.href = url;
            settings.hidden = false;
          } else {
            settings.hidden = true;
          }
        }
      }
      window.__arwShowUpdate = showUpdate;
      function applyUpdateInfo(s) {
        if (s && s.newer && s.latest) showUpdate(s.latest, s.url);
      }
      function parseReleaseTag(tag) {
        var text = String(tag || "").trim();
        if (/^v\d/i.test(text)) return text.slice(1);
        return text;
      }
      function versionParts(ver) {
        var nums = [];
        String(ver || "").replace(/-/g, ".").split(".").forEach(function (part) {
          var digits = part.replace(/\D/g, "");
          if (digits) nums.push(parseInt(digits, 10));
        });
        return nums;
      }
      function isNewerRelease(latest, current) {
        var a = versionParts(parseReleaseTag(latest));
        var b = versionParts(parseReleaseTag(current));
        if (!a.length || !b.length) return false;
        var n = Math.max(a.length, b.length);
        for (var i = 0; i < n; i += 1) {
          var x = a[i] || 0;
          var y = b[i] || 0;
          if (x > y) return true;
          if (x < y) return false;
        }
        return false;
      }
      function showIfClientBehind(current, latest, url) {
        if (latest && current && isNewerRelease(latest, current)) showUpdate(latest, url);
      }
      function checkServerUpdate() {
        fetch("/api/update")
          .then(function (r) { return r.json(); })
          .then(applyUpdateInfo)
          .catch(function () {});
      }
      function checkServerUpdateFor(current) {
        fetch("/api/update")
          .then(function (r) { return r.json(); })
          .then(function (u) {
            if (!u) return;
            showIfClientBehind(current || u.current, u.latest, u.url);
          })
          .catch(function () {});
      }
      function watchDesktopUpdate(api) {
        var tries = 0;
        function tick() {
          tries += 1;
          api.state().then(function (s) {
            var current = (s && s.client_version) || "";
            if (s && s.update) showIfClientBehind(current, s.update.latest, s.update.url);
            if (s && s.update && s.update.newer) return;
            if (s && s.update_checked) {
              checkServerUpdateFor(current);
              return;
            }
            if (tries < 24) setTimeout(tick, 500);
            else checkServerUpdateFor(current);
          }).catch(function () {
            if (tries < 24) setTimeout(tick, 500);
          });
        }
        setTimeout(tick, 400);
      }
      function getDesktopApi() {
        return (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
      }
      function seedCursor() {
        if (!canAfterId) return Promise.resolve();
        return fetch("/api/events?type=appeared&limit=1")
          .then(function (r) { return r.json(); })
          .then(function (rows) {
            if (localStorage.getItem(CURSOR) == null) {
              var id = rows && rows[0] ? rows[0].id : 0;
              localStorage.setItem(CURSOR, String(id || 0));
            }
          })
          .catch(function () {});
      }
      function poll() {
        if (usingDesktopNotify || !canAfterId) return;
        if (!enabled() || typeof Notification === "undefined" || Notification.permission !== "granted") return;
        var after = localStorage.getItem(CURSOR) || "0";
        fetch("/api/events?type=appeared&after_id=" + encodeURIComponent(after) + "&limit=50")
          .then(function (r) { return r.json(); })
          .then(function (rows) {
            (rows || []).forEach(function (ev) {
              var id = Number(ev.id || 0);
              var cursor = Number(localStorage.getItem(CURSOR) || 0);
              if (id <= cursor) return;
              try {
                new Notification(ev.title || "官翻上线", { body: (ev.message || "").slice(0, 180), tag: "arw-" + id });
              } catch (err) {}
              if (id > cursor) localStorage.setItem(CURSOR, String(id));
            });
          })
          .catch(function () {});
      }
      function applyToggle(on) {
        if (!canAfterId) {
          setStatus("当前服务器不支持电脑通知。");
          var box = $("computer-notify-enabled");
          if (box) box.checked = false;
          return;
        }
        localStorage.setItem(KEY, on ? "1" : "0");
        if (!on) {
          setStatus("已关闭。");
          return;
        }
        askPermission(function () {
          setStatus("已开启。");
          seedCursor();
        });
      }
      function applyHealth(h) {
        var caps = h && h.capabilities;
        if (Array.isArray(caps) && caps.length) {
          canAfterId = caps.indexOf("events.after_id") >= 0;
        } else if (h && h.ok) {
          canAfterId = false;
        }
        if (h && h.api_revision != null && Number(h.api_revision) > CLIENT_API_REVISION) {
          showBanner("服务器 API 新于本页面，请升级客户端。");
        } else if (h && !canAfterId) {
          showBanner("服务器版本较旧，电脑通知不可用。可继续使用核心功能，或升级服务器。");
        }
      }
      function fillDesktopPanel(s) {
        desktopRuntimeMode = s.mode || null;
        var panel = $("desktop-this-computer");
        if (panel) panel.hidden = false;
        document.documentElement.classList.add("desktop");
        var url = $("desktop-url");
        if (url && s.url) url.value = s.url;
        var insecure = $("desktop-insecure");
        if (insecure) insecure.checked = !!s.allow_insecure;
        var auto = $("desktop-autostart");
        if (auto) auto.checked = !!s.autostart;
        var hint = $("desktop-autostart-hint");
        if (hint) hint.textContent = "";
        var st = $("desktop-conn-status");
        if (st) {
          if (s.env_locked) st.textContent = "连接由环境变量指定，无法在此更改。";
          else if (s.error) st.textContent = s.error;
          else if (s.mode === "remote") st.textContent = "已连接 " + (s.url || "") + "。";
          else st.textContent = "正在使用本机服务。";
        }
        var clientVer = $("desktop-client-ver");
        if (clientVer && s.client_version) {
          clientVer.textContent = "桌面 " + s.client_version;
        }
        var token = $("desktop-token");
        if (token && s.has_token) token.placeholder = "已保存";
        if (s.env_locked) {
          var connBtn = $("desktop-connect");
          var discBtn = $("desktop-disconnect");
          if (connBtn) connBtn.disabled = true;
          if (discBtn) discBtn.disabled = true;
        }
        if (s.notice) showBanner(s.notice);
        if (s.error) showBanner(s.error);
        if (s.can_notify === false) canAfterId = false;
        applyUpdateInfo(s.update);
      }
      function wireDesktopButtons(api) {
        var connectBtn = $("desktop-connect");
        if (connectBtn) connectBtn.addEventListener("click", function () {
          var urlEl = $("desktop-url");
          var tokenEl = $("desktop-token");
          var insecureEl = $("desktop-insecure");
          var st = $("desktop-conn-status");
          api.connect((urlEl && urlEl.value) || "", (tokenEl && tokenEl.value) || "", !!(insecureEl && insecureEl.checked)).then(function (r) {
            if (!r || !r.ok) {
              if (st) st.textContent = (r && r.error) || "连接失败";
              return;
            }
            if (st) st.textContent = "正在重启窗口…";
          });
        });
        var discBtn = $("desktop-disconnect");
        if (discBtn) discBtn.addEventListener("click", function () {
          var st = $("desktop-conn-status");
          api.disconnect().then(function (r) {
            if (!r || !r.ok) {
              if (st) st.textContent = (r && r.error) || "无法改回本机";
              return;
            }
            if (st) st.textContent = "正在重启窗口…";
          });
        });
        var auto = $("desktop-autostart");
        if (auto) auto.addEventListener("change", function () {
          var hint = $("desktop-autostart-hint");
          api.set_autostart(auto.checked).then(function (r) {
            if (!r || !r.ok) {
              auto.checked = !auto.checked;
              if (hint) hint.textContent = (r && r.error) || "无法更改开机自启";
              return;
            }
            auto.checked = !!r.autostart;
            if (hint) hint.textContent = "";
          });
        });
      }
      function wireNotifyTest() {
        var btn = $("computer-notify-test");
        if (!btn) return;
        btn.addEventListener("click", function () {
          if (desktopApi && desktopApi.test_computer_notify) {
            desktopApi.test_computer_notify().then(function (r) {
              setStatus((r && r.ok) ? "已弹出本机通知。" : ((r && r.error) || "无法弹出"), !(r && r.ok));
            }).catch(function () { setStatus("无法弹出", true); });
            return;
          }
          askPermission(function () {
            try {
              new Notification("官翻监听测试", { body: "电脑通知已接通。" });
              setStatus("已弹出本机通知。");
            } catch (err) {
              setStatus("无法弹出通知。", true);
            }
          });
        });
      }
      function wireNotify(box) {
        if (!box) {
          if (!usingDesktopNotify && canAfterId && enabled()) seedCursor();
          return;
        }
        if (usingDesktopNotify) {
          if (!canAfterId) {
            box.disabled = true;
            box.checked = false;
            setStatus("当前服务器不支持电脑通知。");
            return;
          }
          box.addEventListener("change", function () {
            desktopApi.set_computer_notify(box.checked).then(function (r) {
              if (r && !r.ok) {
                box.checked = false;
                setStatus(r.error || "无法保存");
                return;
              }
              setStatus(box.checked ? "已开启。" : "已关闭。");
            });
          });
          return;
        }
        if (!canAfterId) {
          box.disabled = true;
          box.checked = false;
          setStatus("当前服务器不支持电脑通知。");
          return;
        }
        box.checked = enabled();
        if (enabled()) {
          if (permissionState() === "granted") {
            seedCursor();
          } else if (permissionState() === "denied") {
            setStatus(HINT_DENIED, true);
          } else if (permissionState() === "unsupported") {
            setStatus("当前浏览器不支持网页通知。", true);
          } else {
            setStatus(HINT_DEFAULT, true);
          }
        } else if (permissionState() === "denied") {
          setStatus(HINT_DENIED, true);
        }
        box.addEventListener("change", function () { applyToggle(box.checked); });
      }
      function wireServerAutostart(hide) {
        var panel = $("server-autostart");
        var box = $("server-autostart-enabled");
        var status = $("server-autostart-status");
        if (!panel || !box) return;
        if (hide) {
          panel.hidden = true;
          return;
        }
        panel.hidden = false;
        fetch("/api/autostart")
          .then(function (r) { return r.json(); })
          .then(function (s) {
            box.checked = !!s.installed;
            if (status) status.textContent = "";
          })
          .catch(function () {
            if (status) status.textContent = "无法读取开机自启状态。";
          });
        box.addEventListener("change", function () {
          fetch("/api/autostart", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify({ enabled: box.checked })
          })
            .then(function (r) { return r.json().then(function (data) { return { okHttp: r.ok, data: data }; }); })
            .then(function (res) {
              var s = res.data || {};
              if (!res.okHttp || !s.ok) {
                box.checked = !box.checked;
                if (status) status.textContent = s.message || s.detail || "无法更改开机自启。";
                return;
              }
              box.checked = !!s.installed;
              if (status) status.textContent = s.message || (s.installed ? "已开启。" : "已关闭。");
            })
            .catch(function () {
              box.checked = !box.checked;
              if (status) status.textContent = "无法更改开机自启。";
            });
        });
      }
      function boot() {
        if (wired) return;
        wired = true;
        desktopApi = getDesktopApi();
        var ready = Promise.resolve();
        if (desktopApi && desktopApi.state) {
          usingDesktopNotify = true;
          ready = desktopApi.state().then(fillDesktopPanel).catch(function () {
            usingDesktopNotify = false;
          });
        }
        var healthP = fetch("/api/health").then(function (r) { return r.json(); }).then(applyHealth).catch(function () {});
        Promise.all([ready, healthP]).then(function () {
          wireNotify($("computer-notify-enabled"));
          wireNotifyTest();
          if (desktopApi) {
            wireDesktopButtons(desktopApi);
            watchDesktopUpdate(desktopApi);
          } else {
            checkServerUpdate();
          }
          wireServerAutostart(desktopRuntimeMode === "local");
        });
      }
      function bootSoon() {
        if (getDesktopApi()) {
          if (bootTimer) clearTimeout(bootTimer);
          boot();
          return;
        }
        if (document.documentElement.classList.contains("desktop")) return;
        if (!bootTimer) {
          bootTimer = setTimeout(function () {
            bootTimer = null;
            boot();
          }, 120);
        }
      }
      window.addEventListener("pywebviewready", function () {
        if (bootTimer) clearTimeout(bootTimer);
        bootTimer = null;
        boot();
      });
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootSoon);
      } else {
        bootSoon();
      }
      function applyScanChrome(data) {
        var view = (data && data.view) || {};
        var scanning = !!view.scanning;
        document.querySelectorAll(".scan-form button[type='submit']").forEach(function (btn) {
          btn.disabled = scanning;
          if (scanning) btn.setAttribute("aria-busy", "true");
          else btn.removeAttribute("aria-busy");
          btn.textContent = scanning ? "正在扫描" : "立即扫描";
        });
        var pulse = document.getElementById("status-pulse");
        if (pulse && view.state) {
          pulse.setAttribute("data-state", view.state);
          pulse.setAttribute("title", view.detail || "");
          var dot = pulse.querySelector(".dot");
          if (dot) dot.className = "dot " + view.state;
          var label = pulse.querySelector("summary b");
          if (label) label.textContent = view.label || "";
          var fields = {
            "last-success": "上次成功 " + (view.last_success || "无"),
            interval: (view.interval_label || "") + "扫描",
            stock: "在售 " + (view.in_stock == null ? "" : view.in_stock),
            watches: "规则 " + (view.watch_enabled || 0) + "/" + (view.watch_total || 0) + " 启用",
            baseline: "基线 " + (view.baseline_label || "")
          };
          Object.keys(fields).forEach(function (key) {
            var node = pulse.querySelector("[data-pulse='" + key + "']");
            if (node) node.textContent = fields[key];
          });
          var errPop = pulse.querySelector("[data-pulse='error']");
          if (errPop) {
            errPop.textContent = view.last_error || "";
            errPop.hidden = !view.last_error;
          }
        }
        var errBar = document.getElementById("pulse-err");
        if (errBar) {
          errBar.textContent = view.last_error || "";
          errBar.hidden = !view.last_error;
        }
      }
      function emitStatus(data) {
        window.__arwLastStatus = data;
        applyScanChrome(data);
        window.dispatchEvent(new CustomEvent("arw-status", { detail: data }));
      }
      var statusInFlight = false;
      function pollStatus() {
        if (document.visibilityState === "hidden" || statusInFlight) return;
        statusInFlight = true;
        fetch("/api/status", { headers: { "Accept": "application/json" } })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) { if (data) emitStatus(data); })
          .catch(function () {})
          .then(function () { statusInFlight = false; });
      }
      window.__arwApplyStatus = applyScanChrome;
      window.__arwEmitStatus = emitStatus;
      window.setInterval(pollStatus, 4000);
      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState !== "hidden") pollStatus();
      });
      pollStatus();
      setInterval(poll, 12000);
      var filterSwapState = null;
      function snapshotFilterUi() {
        var dlg = document.getElementById("filter-dialog");
        if (!dlg) return null;
        var active = document.activeElement;
        var activeName = null;
        var activeValue = null;
        var activeType = null;
        if (active && dlg.contains(active) && active.getAttribute) {
          activeName = active.getAttribute("name");
          activeValue = active.value;
          activeType = active.type || "";
        }
        var openDetails = [];
        dlg.querySelectorAll("details").forEach(function (el) {
          if (!el.open) return;
          var summary = el.querySelector("summary");
          openDetails.push(summary ? String(summary.textContent || "").trim() : "");
        });
        return {
          dialogOpen: !!(dlg.open || dlg.hasAttribute("open")),
          activeName: activeName,
          activeValue: activeValue,
          activeType: activeType,
          openDetails: openDetails
        };
      }
      function restoreFilterUi(state) {
        if (!state) return;
        var dlg = document.getElementById("filter-dialog");
        var btn = document.getElementById("filter-toggle");
        if (!dlg) return;
        if (state.dialogOpen) {
          if (typeof dlg.showModal === "function") {
            if (!dlg.open) dlg.showModal();
          } else {
            dlg.setAttribute("open", "");
          }
          if (btn) btn.setAttribute("aria-expanded", "true");
        }
        if (state.openDetails && state.openDetails.length) {
          dlg.querySelectorAll("details").forEach(function (el) {
            var summary = el.querySelector("summary");
            var key = summary ? String(summary.textContent || "").trim() : "";
            el.open = state.openDetails.indexOf(key) !== -1;
          });
        }
        if (state.activeName) {
          var nodes = dlg.querySelectorAll("[name=\"" + String(state.activeName).replace(/"/g, "") + "\"]");
          var focusEl = null;
          nodes.forEach(function (node) {
            if (state.activeType === "checkbox") {
              if (node.value === state.activeValue) focusEl = node;
            } else {
              focusEl = node;
            }
          });
          if (focusEl && typeof focusEl.focus === "function") {
            try { focusEl.focus({ preventScroll: true }); } catch (err) { focusEl.focus(); }
          }
        }
      }
      function shopSwapTarget(ev) {
        var target = ev.detail && ev.detail.target;
        if (!target) return false;
        return target.id === "shop" || (target.querySelector && target.querySelector("#filter-toggle"));
      }
      function wireFilterDialog() {
        var btn = document.getElementById("filter-toggle");
        var dlg = document.getElementById("filter-dialog");
        var closeBtn = document.getElementById("filter-close");
        if (!btn || !dlg || btn.dataset.wired === "1") return;
        btn.dataset.wired = "1";
        function setExpanded(open) {
          btn.setAttribute("aria-expanded", open ? "true" : "false");
        }
        btn.addEventListener("click", function () {
          if (typeof dlg.showModal === "function") dlg.showModal();
          else dlg.setAttribute("open", "");
          setExpanded(true);
        });
        if (closeBtn) closeBtn.addEventListener("click", function () {
          if (typeof dlg.close === "function") dlg.close();
          else dlg.removeAttribute("open");
        });
        dlg.addEventListener("close", function () { setExpanded(false); });
      }
      wireFilterDialog();
      document.body.addEventListener("htmx:beforeRequest", function (ev) {
        if (shopSwapTarget(ev)) filterSwapState = snapshotFilterUi();
      });
      document.body.addEventListener("htmx:afterSwap", function (ev) {
        if (!shopSwapTarget(ev)) return;
        restoreFilterUi(filterSwapState);
        filterSwapState = null;
        wireFilterDialog();
      });
    })();
