
      // const userId = "{{ user_id }}";

      // Per-mode configuration: the single source of truth for everything that
      // differs between the songs / questions / general modes.
      const MODES = {
        general: {
          heading: "Let's Pick a thing",
          placeholder: "Type a suggestion here",
          likePrompt: "Check the box for each you like:",
          completed: "Done:",
          markDone: "Mark as done",
          markUndone: "Mark as not done",
          unit1: "vote", unitN: "votes",
          links: false, multiline: false,
        },
        songs: {
          heading: "Let's Pick a song",
          placeholder: "Type a song here",
          likePrompt: "Check the box for each you like:",
          completed: "Already Played:",
          markDone: "Mark as played",
          markUndone: "Mark as not played",
          unit1: "fan", unitN: "fans",
          links: true, multiline: false,
        },
        questions: {
          heading: "Let's Pick a question",
          placeholder: "Type your question here",
          likePrompt: "Check the box for each you'd like asked:",
          completed: "Already Asked:",
          markDone: "Mark as asked",
          markUndone: "Mark as not asked",
          unit1: "vote", unitN: "votes",
          links: false, multiline: true,
        },
      };
      let currentMode = window.initialMode in MODES ? window.initialMode : "general";

      // Adaptive poll floor. The server suggests an interval (`poll_after`) to
      // keep the global request rate under its CPU budget; on top of that each
      // client raises its own floor when its polls are slow or error out — a
      // safety net for cold starts or a server too swamped to even advise. The
      // effective floor is the max of both, so small/quiet rooms stay at 1s.
      let serverPollFloor = 1000; // ms, from the server's poll_after hint
      let latencyFloor = 1000;    // ms, client-side backoff on slow round-trips
      const SLOW_RTT = 4000;      // a poll slower than this means we're struggling
      function currentFloor() {
        return Math.max(min_polling_wait, serverPollFloor, latencyFloor);
      }
      // Fold a poll's outcome into the adaptive floors: adopt the server's hint,
      // and AIMD the client safety net (back off fast when slow, recover slowly).
      function noteServerHints(payload, rttMs) {
        if (payload && typeof payload.poll_after === "number") {
          serverPollFloor = payload.poll_after;
        }
        if (rttMs > SLOW_RTT) {
          latencyFloor = Math.min(max_polling_wait, latencyFloor * 1.5);
        } else {
          latencyFloor = Math.max(1000, latencyFloor * 0.9);
        }
      }

      const min_polling_wait = 1000; //1s
      const max_polling_wait = 15000; //15s
      let polling_wait = currentFloor();
      // Last room version seen from the server. -1 never matches a real version,
      // so the first poll always pulls the full payload and syncs.
      let currentVersion = -1;

      // let roomIdTimer;
      let listSortTimer;

      // Connection state. The banner shows whenever a request fails (network
      // down, server down, HTTP error) and hides again on the next success.
      let connected = true;
      function setConnected(ok) {
        if (ok === connected) return;
        connected = ok;
        const banner = document.getElementById("connectionBanner");
        if (banner) banner.classList.toggle("show", !ok);
      }

      // fetch wrapper that tracks connection state: a thrown error (offline) or a
      // non-OK response (server error) shows the banner and rethrows; a good
      // response clears it. All API calls go through this.
      async function apiFetch(url, options) {
        try {
          const response = await fetch(url, options);
          if (!response.ok) throw new Error("HTTP " + response.status);
          setConnected(true);
          return response;
        } catch (err) {
          setConnected(false);
          throw err;
        }
      }


      async function submitItem() {
        const itemText = document.getElementById("itemInput").value;
        const response = await apiFetch("/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            text: itemText,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          updateItemList();
          itemInput.value = ""; // Clear the text input
          itemInput.focus(); // Set focus back to the input
          polling_wait = currentFloor(); // reset the polling wait time
        }
      }

      document
        .getElementById("itemInput")
        .addEventListener("keydown", function (event) {
          // In multiline (questions) mode, Enter inserts a newline; submit via
          // the button. Otherwise Enter submits (unless Shift is held).
          if (event.key === "Enter" && !MODES[currentMode].multiline && !event.shiftKey) {
            event.preventDefault();
            submitItem();
          }
        });

      // Apply the given mode to the UI (strings, styling, input behaviour).
      function applyMode(mode) {
        if (!(mode in MODES)) mode = "general";
        currentMode = mode;
        const cfg = MODES[mode];

        document.body.className = "mode-" + mode;

        // Favicon is a checked checkbox tinted with the mode's accent colour.
        const favicon = document.getElementById("favicon");
        if (favicon) favicon.href = "static/favicon-" + mode + ".svg";

        const heading = document.getElementById("heading");
        if (heading) heading.textContent = cfg.heading;

        const likePrompt = document.getElementById("likePrompt");
        if (likePrompt) likePrompt.textContent = cfg.likePrompt;

        const completedLabel = document.querySelector("#itemList2Label p");
        if (completedLabel) completedLabel.textContent = cfg.completed;

        const input = document.getElementById("itemInput");
        if (input) {
          input.placeholder = cfg.placeholder;
          if (cfg.multiline) {
            input.rows = 3;
            input.classList.add("multiline");
          } else {
            input.rows = 1;
            input.classList.remove("multiline");
          }
        }

        // Highlight the active mode in the gear menu.
        document.querySelectorAll("#modeMenuList button").forEach((btn) => {
          btn.classList.toggle("active", btn.dataset.mode === mode);
        });

        // The form height differs by mode (questions is multiline), so re-centre
        // the corner QR against the new layout.
        layoutQr();
      }

      function toggleModeMenu() {
        document.getElementById("modeMenu").classList.toggle("open");
      }

      // Desktop-only: enlarge the corner QR to a big top-right overlay; click again
      // to shrink. On mobile the QR already spans the full width, so do nothing.
      function toggleQrZoom() {
        if (window.matchMedia("(min-width: 750px)").matches) {
          document.getElementById("qrWrap").classList.toggle("zoomed");
        }
      }

      // Desktop-only: size the corner QR to the heading→form cluster and centre it
      // vertically in the space beside the text box, so it sits evenly and grows
      // when the box is taller (e.g. questions mode). Written as CSS custom props
      // so the .zoomed overlay can still override. On mobile the QR is full-width
      // in normal flow, so we clear the props and let CSS handle it.
      function layoutQr() {
        const wrap = document.getElementById("qrWrap");
        if (!wrap) return;
        if (!window.matchMedia("(min-width: 750px)").matches) {
          wrap.style.removeProperty("--qr-size");
          wrap.style.removeProperty("--qr-top");
          return;
        }
        const heading = document.getElementById("heading");
        const form = document.getElementById("submitform");
        if (!heading || !form) return;
        // Use document coordinates (add scrollY) so the fixed QR lands beside the
        // form's natural position regardless of how far the page is scrolled.
        const sy = window.scrollY;
        const top = heading.getBoundingClientRect().top + sy;
        const bottom = form.getBoundingClientRect().bottom + sy;
        const MAX = 200; // QR column width beside the form
        const MIN = 150;
        const size = Math.max(MIN, Math.min(bottom - top, MAX));
        const center = (top + bottom) / 2;
        wrap.style.setProperty("--qr-size", size + "px");
        wrap.style.setProperty("--qr-top", Math.round(center - size / 2) + "px");
      }

      // Keep the QR placement correct as the viewport changes or web fonts load
      // (the questions-mode serif heading changes height once it arrives).
      window.addEventListener("resize", layoutQr);
      window.addEventListener("load", layoutQr);
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(layoutQr);
      }

      // Close the gear menu on outside click or Escape.
      document.addEventListener("click", function (event) {
        const menu = document.getElementById("modeMenu");
        if (menu && !menu.contains(event.target)) {
          menu.classList.remove("open");
        }
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          document.getElementById("modeMenu").classList.remove("open");
        }
      });

      // Cast this user's mode vote, then apply the resulting effective mode
      // (which may differ from the pick if the user is outvoted).
      async function setMode(mode) {
        document.getElementById("modeMenu").classList.remove("open");
        const response = await apiFetch("/set_mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            mode: mode,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          applyMode(data.mode);
          updateItemList();
          polling_wait = currentFloor();
        }
      }

      async function toggleItem(itemText) {
        const response = await apiFetch("/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            text: itemText,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          // Don't resort everything immediately, wait a bit for the user to stop clicking
          clearTimeout(listSortTimer);
          listSortTimer = setTimeout(() => {
            updateItemList();
          }, 2000);

          polling_wait = currentFloor();
        }
      }

      async function toggleHidden(itemText) {
        const response = await apiFetch("/togglehidden", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            text: itemText,
            user_id: userId,
          }),
        });

        const data = await response.json();

        console.log("hiding");
        console.log(data);
        if (data.status === "success") {
          updateItemList();
        }

        polling_wait = currentFloor();
      }

      async function hideItem(itemText) {
        const response = await apiFetch("/hide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            text: itemText,
            user_id: userId,
          }),
        });

        const data = await response.json();

        if (data.status === "success") {
          updateItemList();
        }

        polling_wait = currentFloor();
      }

      async function showItem(itemText) {
        const response = await apiFetch("/show", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: getRoomId(),
            text: itemText,
            user_id: userId,
          }),
        });

        const data = await response.json();

        if (data.status === "success") {
          updateItemList();
        }

        polling_wait = currentFloor();
      }

      function getRoomId() {
        return window.roomId;
      }

      async function updateItemList() {
        const roomId = getRoomId();
        const t0 = performance.now();
        const response = await apiFetch(`/get_items?room_id=${roomId}&v=${currentVersion}`);
        const payload = await response.json();
        // Adopt the server's suggested poll interval + update the client safety net.
        noteServerHints(payload, performance.now() - t0);

        // Server says nothing changed since our last version: skip the whole
        // re-render (avoids clearing/rebuilding both lists and checkbox flicker).
        if (payload.changed === false) {
          currentVersion = payload.version;
          return false;
        }

        currentVersion = payload.version;
        items_changed_p = true;
        const items = payload.items || [];

        // Effective mode can change as others vote; apply it before rendering.
        if (payload.mode && payload.mode !== currentMode) {
          applyMode(payload.mode);
        }

        const itemList = document.getElementById("itemList");

        itemList.innerHTML = ""; // Clear the current list

        function createItemLi(item, itemlist) {
          const li = document.createElement("li");

          const item_text_span = document.createElement("span");
          item_text_span.textContent = `${item.text}     `;
          li.appendChild(item_text_span);

          // Song-specific helper links (YouTube + chords) only in songs mode.
          if (MODES[currentMode].links) {
            // Create YouTube search link
            const youtubeLink = document.createElement("a");
            youtubeLink.href = `https://www.youtube.com/results?search_query=${encodeURIComponent(
              item.text
            )}`;
            youtubeLink.target = "_blank"; // Open link in a new tab/window
            youtubeLink.title = `Search for song on YouTube`;

            const youtubeIcon = document.createTextNode(" ▶️ ");
            youtubeLink.appendChild(youtubeIcon);

            item_text_span.appendChild(youtubeLink);

            // Create chord search link
            const chordsLink = document.createElement("a");
            chordsLink.href = `https://www.google.com/search?q=${encodeURIComponent(
              item.text + " chords"
            )}`;
            chordsLink.target = "_blank"; // Open link in a new tab/window
            chordsLink.title = `Search for chords on Google`;

            const chordsIcon = document.createTextNode(" 🎸 ");
            chordsLink.appendChild(chordsIcon);

            item_text_span.appendChild(chordsLink);
          }

          // Create checkbox for liking items
          const checkboxDiv = document.createElement("div");
          checkboxDiv.className = "checkbox-container";
          checkboxDiv.title = "I like this";

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          if (item.submitters.includes(userId)) {
            checkbox.checked = true;
          }
          checkbox.onclick = function () {
            toggleItem(item.text);
          };
          checkboxDiv.appendChild(checkbox);
          li.appendChild(checkboxDiv);

          // How many fans/votes does the suggestion have?
          const countText =
            item.submitters.length === 1
              ? MODES[currentMode].unit1
              : MODES[currentMode].unitN;
          const count_span = document.createElement("span");
          count_span.textContent = `(${item.submitters.length} ${countText})`;
          count_span.className = "count-span";
          li.appendChild(count_span);

          // Add hide/un-hide link
          const hideLink = document.createElement("a");

          hideLink.href = "#"; // No actual navigation, just a link
          hideLink.className = "hide-item-link"; // Optional class for styling
          if (itemlist === 1) {
            hideLink.innerHTML = "&times;"; // Unicode 'x'
            hideLink.title = MODES[currentMode].markDone;

          } else if (itemlist === 2) {
            hideLink.innerHTML = "&times;"; // Unicode 'x'
            hideLink.title = MODES[currentMode].markUndone;

          }
          hideLink.onclick = function (event) {
            event.preventDefault(); // Prevent default link behavior

            if (itemlist === 1) {
              hideItem(item.text);
            } else if (itemlist === 2) {
              showItem(item.text);
            }
            updateItemList();
          };
          li.appendChild(hideLink);

          return li;
        }

        console.log(items.length);
        if (items.length === 0) {
          const li = document.createElement("li");
          li.textContent = "No suggestions yet";
          li.style.fontStyle = "italic";
          li.style.color = "grey";
          itemList.appendChild(li);
          // itemList.innerHTML = "<p>No suggestions yet</p>";
        }

        for (const item of items) {
          if (
            item.showers.includes(userId) ||
            (!item.default_hidden && !item.hiders.includes(userId))
          ) {
            const li = createItemLi(item, 1);
            itemList.appendChild(li);
          }
        }

        const itemList2 = document.getElementById("itemList2");

        itemList2.innerHTML = ""; // Clear the current list

        let itemList2Empty = true;
        for (const item of items) {
          if (
            item.hiders.includes(userId) ||
            (item.default_hidden && !item.showers.includes(userId))
          ) {
            itemList2Empty = false;
            const li = createItemLi(item, 2); // let createItemLi know that this is list 2, styled differently
            itemList2.appendChild(li);
          }
        }

        const itemList2Label = document.getElementById("itemList2Label");
        if (itemList2Empty === true) {
          itemList2Label.style.display = "none";
        } else {
          itemList2Label.style.display = "block";
        }

        return items_changed_p;
      }

      async function pollItemList() {
        try {
          // Pull down the new item list, storing whether anything changed
          items_changed_p = await updateItemList();

          const floor = currentFloor();
          if (items_changed_p) {
            // the item list changed, poll again at the floor for quick updates
            polling_wait = floor;
          } else {
            // Nothing changed, take longer to poll next time (but never below
            // the floor the server/our-safety-net is asking for)
            polling_wait = Math.min(max_polling_wait, polling_wait * 1.5);
            if (polling_wait < floor) polling_wait = floor;
          }
        } catch (err) {
          // Connection/overload problem (apiFetch already showed the banner).
          // Raise the client safety-net floor so we don't hammer a struggling
          // server, then retry — recovering once it's healthy again.
          latencyFloor = Math.min(max_polling_wait, latencyFloor * 1.5);
          polling_wait = currentFloor();
        }
        console.log(polling_wait, items_changed_p, connected);
        // Jitter (±15%) so hundreds of clients don't poll in lockstep, then
        // reschedule — always, so polling never silently dies.
        const jittered = polling_wait * (0.85 + Math.random() * 0.3);
        setTimeout(pollItemList, jittered);
      }

      // Apply the server-provided initial mode immediately (avoids a flash),
      // then start polling — which keeps the mode in sync as others vote.
      applyMode(currentMode);
      pollItemList();
