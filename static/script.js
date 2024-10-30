
      const userId = "{{ user_id }}";
      const min_polling_wait = 3000; //3s
      const max_polling_wait = 20000; //20s

      // let jamIdTimer;
      let listSortTimer;

      /*
      // Check if there's a saved value when the page loads
      document.addEventListener("DOMContentLoaded", function () {
        if (localStorage.getItem("jamId")) {
          document.getElementById("jamIdInput").value =
            localStorage.getItem("jamId");
        }
      });

      // Listen for changes in the text box
      document
        .getElementById("jamIdInput")
        .addEventListener("input", function () {
          localStorage.setItem("jamId", this.value);

          //update the URL to reflect the new jam id
          newUrl = "http://521.glitch.me/" + this.value;
          if (window.location.pathname !== newUrl) {
            window.history.pushState({}, "", newUrl);
          }

          // Whenever the jamid changes, reset a timer
          // so we can refresh the list shortly afterwards
          clearTimeout(jamIdTimer);

          // Set a new timer
          jamIdTimer = setTimeout(() => {
            updateSongList();
          }, 1000);
        });

        */

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
          if (event.key === "Enter") {
            submitSong();
          }
        });

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
        return "{{ jam_id }}";
      }

      previousList = "";
      async function updateSongList() {
        const jamId = getJamId();
        const response = await fetch(`/get_songs?jam_id=${jamId}`);
        const songs = await response.json();
        console.log(JSON.stringify(songs));

        const songList = document.getElementById("songList");

        if (JSON.stringify(songs) === previousList) {
          console.log("Songs didn't change");
          songs_changed_p = false;
        } else {
          songs_changed_p = true;
          console.log("Songs changed");
          //store the old list for comparison later
          previousList = JSON.stringify(songs);
        }

        songList.innerHTML = ""; // Clear the current list

        function createSongLi(song, songlist) {
          const li = document.createElement("li");

          const songname_span = document.createElement("span");
          songname_span.textContent = `${song.song}     `;
          li.appendChild(songname_span);

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

          // How many fans does the song have?
          const fanText = song.submitters.length === 1 ? "fan" : "fans";
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
            hideLink.title = "Mark as completed";

          } else if (songlist === 2) {
            hideLink.innerHTML = "&times;"; // Unicode 'x'
            hideLink.title = "Mark as not completed";

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

      pollSongList();
    