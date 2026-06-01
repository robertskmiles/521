
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

      const min_polling_wait = 1000; //1s
      const max_polling_wait = 15000; //15s
      let polling_wait = min_polling_wait;
      // Last room version seen from the server. -1 never matches a real version,
      // so the first poll always pulls the full payload and syncs.
      let currentVersion = -1;

      // let jamIdTimer;
      let listSortTimer;


      async function submitSong() {
        const songName = document.getElementById("songInput").value;
        const response = await fetch("/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            song: songName,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          updateSongList();
          songInput.value = ""; // Clear the text input
          songInput.focus(); // Set focus back to the input
          polling_wait = min_polling_wait; // reset the polling wait time
        }
      }

      document
        .getElementById("songInput")
        .addEventListener("keydown", function (event) {
          // In multiline (questions) mode, Enter inserts a newline; submit via
          // the button. Otherwise Enter submits (unless Shift is held).
          if (event.key === "Enter" && !MODES[currentMode].multiline && !event.shiftKey) {
            event.preventDefault();
            submitSong();
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

        const completedLabel = document.querySelector("#songList2Label p");
        if (completedLabel) completedLabel.textContent = cfg.completed;

        const input = document.getElementById("songInput");
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
      }

      function toggleModeMenu() {
        document.getElementById("modeMenu").classList.toggle("open");
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
        const response = await fetch("/set_mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            mode: mode,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          applyMode(data.mode);
          updateSongList();
          polling_wait = min_polling_wait;
        }
      }

      async function toggleSong(songName) {
        const response = await fetch("/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            song: songName,
            user_id: userId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          // Don't resort everything immediately, wait a bit for the user to stop clicking
          clearTimeout(listSortTimer);
          listSortTimer = setTimeout(() => {
            updateSongList();
          }, 2000);

          polling_wait = min_polling_wait;
        }
      }

      async function toggleHidden(songName) {
        const response = await fetch("/togglehidden", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            song: songName,
            user_id: userId,
          }),
        });

        const data = await response.json();

        console.log("hiding");
        console.log(data);
        if (data.status === "success") {
          updateSongList();
        }

        polling_wait = min_polling_wait;
      }

      async function hideSong(songName) {
        const response = await fetch("/hide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            song: songName,
            user_id: userId,
          }),
        });

        const data = await response.json();

        if (data.status === "success") {
          updateSongList();
        }

        polling_wait = min_polling_wait;
      }

      async function showSong(songName) {
        const response = await fetch("/show", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jam_id: getJamId(),
            song: songName,
            user_id: userId,
          }),
        });

        const data = await response.json();

        if (data.status === "success") {
          updateSongList();
        }

        polling_wait = min_polling_wait;
      }

      function getJamId() {
        // return document.getElementById("jamIdInput").value;
        return window.jamId;
      }

      async function updateSongList() {
        const jamId = getJamId();
        const response = await fetch(`/get_songs?jam_id=${jamId}&v=${currentVersion}`);
        const payload = await response.json();

        // Server says nothing changed since our last version: skip the whole
        // re-render (avoids clearing/rebuilding both lists and checkbox flicker).
        if (payload.changed === false) {
          currentVersion = payload.version;
          return false;
        }

        currentVersion = payload.version;
        songs_changed_p = true;
        const songs = payload.songs || [];

        // Effective mode can change as others vote; apply it before rendering.
        if (payload.mode && payload.mode !== currentMode) {
          applyMode(payload.mode);
        }

        const songList = document.getElementById("songList");

        songList.innerHTML = ""; // Clear the current list

        function createSongLi(song, songlist) {
          const li = document.createElement("li");

          const songname_span = document.createElement("span");
          songname_span.textContent = `${song.song}     `;
          li.appendChild(songname_span);

          // Song-specific helper links (YouTube + chords) only in songs mode.
          if (MODES[currentMode].links) {
            // Create YouTube search link
            const youtubeLink = document.createElement("a");
            youtubeLink.href = `https://www.youtube.com/results?search_query=${encodeURIComponent(
              song.song
            )}`;
            youtubeLink.target = "_blank"; // Open link in a new tab/window
            youtubeLink.title = `Search for song on YouTube`;

            const youtubeIcon = document.createTextNode(" ▶️ ");
            youtubeLink.appendChild(youtubeIcon);

            songname_span.appendChild(youtubeLink);

            // Create chord search link
            const chordsLink = document.createElement("a");
            chordsLink.href = `https://www.google.com/search?q=${encodeURIComponent(
              song.song + " chords"
            )}`;
            chordsLink.target = "_blank"; // Open link in a new tab/window
            chordsLink.title = `Search for chords on Google`;

            const chordsIcon = document.createTextNode(" 🎸 ");
            chordsLink.appendChild(chordsIcon);

            songname_span.appendChild(chordsLink);
          }

          // Create checkbox for liking songs
          const checkboxDiv = document.createElement("div");
          checkboxDiv.className = "checkbox-container";
          checkboxDiv.title = "I like this song";

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          if (song.submitters.includes(userId)) {
            checkbox.checked = true;
          }
          checkbox.onclick = function () {
            toggleSong(song.song);
          };
          checkboxDiv.appendChild(checkbox);
          li.appendChild(checkboxDiv);

          // How many fans/votes does the suggestion have?
          const fanText =
            song.submitters.length === 1
              ? MODES[currentMode].unit1
              : MODES[currentMode].unitN;
          const fans_span = document.createElement("span");
          fans_span.textContent = `(${song.submitters.length} ${fanText})`;
          fans_span.className = "fans-span";
          li.appendChild(fans_span);

          // Add hide/un-hide link
          const hideLink = document.createElement("a");
          
          hideLink.href = "#"; // No actual navigation, just a link
          hideLink.className = "hide-song-link"; // Optional class for styling
          if (songlist === 1) {
            hideLink.innerHTML = "&times;"; // Unicode 'x'
            hideLink.title = MODES[currentMode].markDone;

          } else if (songlist === 2) {
            hideLink.innerHTML = "&times;"; // Unicode 'x'
            hideLink.title = MODES[currentMode].markUndone;

          }
          hideLink.onclick = function (event) {
            event.preventDefault(); // Prevent default link behavior

            if (songlist === 1) {
              hideSong(song.song);
            } else if (songlist === 2) {
              showSong(song.song);
            }
            updateSongList();
          };
          li.appendChild(hideLink);

          return li;
        }

        console.log(songs.length);
        if (songs.length === 0) {
          const li = document.createElement("li");
          li.textContent = "No suggestions yet";
          li.style.fontStyle = "italic";
          li.style.color = "grey";
          songList.appendChild(li);
          // songList.innerHTML = "<p>No suggestions yet</p>";
        }
        
        for (const song of songs) {
          if (
            song.showers.includes(userId) ||
            (!song.default_hidden && !song.hiders.includes(userId))
          ) {
            const li = createSongLi(song, 1);
            songList.appendChild(li);
          }
        }

        const songList2 = document.getElementById("songList2");

        songList2.innerHTML = ""; // Clear the current list

        let songList2Empty = true;
        for (const song of songs) {
          if (
            song.hiders.includes(userId) ||
            (song.default_hidden && !song.showers.includes(userId))
          ) {
            songList2Empty = false;
            const li = createSongLi(song, 2); // let createSong know that this is list 2, styled differently
            songList2.appendChild(li);
          }
        }

        const songList2Label = document.getElementById("songList2Label");
        if (songList2Empty === true) {
          songList2Label.style.display = "none";
        } else {
          songList2Label.style.display = "block";
        }

        return songs_changed_p;
      }

      async function pollSongList() {
        // Pull down the new song list, storing whether anything changed
        songs_changed_p = await updateSongList();

        if (songs_changed_p) {
          // the song list changed, set the polling time to short
          polling_wait = min_polling_wait;
        } else {
          // Nothing changed, take longer to poll next time
          polling_wait = polling_wait * 1.5;
          if (polling_wait > max_polling_wait) {
            polling_wait = max_polling_wait;
          }
        }
        console.log(polling_wait, songs_changed_p);
        setTimeout(pollSongList, polling_wait);
      }

      // Apply the server-provided initial mode immediately (avoids a flash),
      // then start polling — which keeps the mode in sync as others vote.
      applyMode(currentMode);
      pollSongList();
