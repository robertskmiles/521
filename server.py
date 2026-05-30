from flask import Flask, render_template, request, jsonify, make_response, send_file, abort
from werkzeug.middleware.proxy_fix import ProxyFix
import qrcode
import os
import random
import string
import json

app = Flask(__name__, template_folder='templates')
app.secret_key = 'secret_key'

# Render (and most PaaS hosts) terminate TLS at a proxy and forward the request.
# Trust the X-Forwarded-* headers so request.host_url reflects the real https host.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def generate_short_id(length=8):
    # Use all letters and numbers, but skip confusing ones like l, I, O
    chars = string.ascii_letters + string.digits
    chars = chars.replace('l', '').replace('I', '').replace('O', '')
    return ''.join(random.choice(chars) for _ in range(length))


# In-memory storage
songs = {'default':[]}

# Per-room state version, bumped on every mutation so /get_songs can answer
# "nothing changed" cheaply. Clients send their last-seen version; if it still
# matches we skip sorting + serializing the full list. Default 0 for new rooms.
versions = {}

def bump(jam_id):
    versions[jam_id] = versions.get(jam_id, 0) + 1

# Per-room mode votes: {jam_id: {user_id: 'songs'|'questions'|'general'}}
# A user who hasn't picked a mode sees the majority pick among those who have,
# mirroring the no-central-authority hide/show voting (see update_default_hidden).
mode_votes = {}

VALID_MODES = ('songs', 'questions', 'general')
DEFAULT_MODE = 'general'
# Tie-break priority when vote counts are equal (first listed wins):
MODE_PRIORITY = ('songs', 'questions', 'general')


def compute_mode(jam_id):
    votes = mode_votes.get(jam_id, {})
    if not votes:
        return DEFAULT_MODE
    counts = {mode: 0 for mode in VALID_MODES}
    for mode in votes.values():
        if mode in counts:
            counts[mode] += 1
    # Highest count wins; ties broken by MODE_PRIORITY order.
    return max(MODE_PRIORITY, key=lambda mode: counts[mode])

qr_cache_dir = os.path.join('static', 'qr')
# Ensure the cache directory exists
if not os.path.exists(qr_cache_dir):
  os.makedirs(qr_cache_dir)

  
@app.route('/<string:jam_id>')
@app.route('/')
def index(jam_id="default"):
    print(request.cookies)
    # jam_id = request.args.get('jam_id', 'default')
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = generate_short_id()

    # A ?mode=... link casts this user's mode vote, so sharing e.g.
    # letspick.onrender.com/myroom?mode=songs drops the recipient straight into
    # that mode (it wins outright in a fresh room; otherwise the majority still
    # applies, same as picking it from the gear menu).
    requested_mode = request.args.get('mode')
    if requested_mode in VALID_MODES:
        mode_votes.setdefault(jam_id, {})[user_id] = requested_mode
        bump(jam_id)

    user_submitted_songs = [song['song'] for song in songs.get(jam_id, []) if user_id in song['submitters']]

    response = make_response(render_template('index.html', jam_id=jam_id, songs=songs.get(jam_id, []), user_submitted_songs=user_submitted_songs, user_id=user_id, mode=compute_mode(jam_id)))
    response.set_cookie('user_id', user_id, max_age=60*60*24)  # Set cookie to expire after 1 day

    return response

@app.route('/submit', methods=['POST'])
def submit_song():
    jam_id = request.json.get('jam_id')
    song_name = request.json.get('song')
    user_id = request.json.get('user_id')
    
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []

    # Check if song already exists
    song_entry = next((song for song in songs[jam_id] if song['song'] == song_name), None)

    if song_entry:
        if user_id not in song_entry['submitters']:
            song_entry['submitters'].append(user_id)
    else:
        songs[jam_id].append({'song': song_name, 'submitters': [user_id], 'hiders':[], 'showers':[], 'default_hidden':False})

    bump(jam_id)
    return jsonify({'status': 'success'})

@app.route('/toggle', methods=['POST'])
def toggle_song():
    jam_id = request.json.get('jam_id')
    song_name = request.json.get('song')
    user_id = request.json.get('user_id')

    print(user_id, "toggled", song_name)
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []

    song_entry = next((song for song in songs[jam_id] if song['song'] == song_name), None)
    if song_entry:
        if user_id in song_entry['submitters']:
            song_entry['submitters'].remove(user_id)
        else:
            song_entry['submitters'].append(user_id)
        bump(jam_id)

    return jsonify({'status': 'success'})


@app.route('/hide', methods=['POST'])
def hide_song():
    jam_id = request.json.get('jam_id')
    song_name = request.json.get('song')
    user_id = request.json.get('user_id')

    print(user_id, "hid", song_name)
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []

    song_entry = next((song for song in songs[jam_id] if song['song'] == song_name), None)
    if song_entry:
        if user_id not in song_entry['hiders']:
            song_entry['hiders'].append(user_id)
        if user_id in song_entry['showers']:
            song_entry['showers'].remove(user_id)
            
    
    update_default_hidden(jam_id, song_entry)
    bump(jam_id)
    return jsonify({'status': 'success'})


@app.route('/show', methods=['POST'])
def show_song():
    jam_id = request.json.get('jam_id')
    song_name = request.json.get('song')
    user_id = request.json.get('user_id')

    print(user_id, "showed", song_name)
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []
      
    song_entry = next((song for song in songs[jam_id] if song['song'] == song_name), None)
    if song_entry:
        if user_id not in song_entry['showers']:
            song_entry['showers'].append(user_id)
        if user_id in song_entry['hiders']:
            song_entry['hiders'].remove(user_id)
    
    update_default_hidden(jam_id, song_entry)
    bump(jam_id)
    return jsonify({'status': 'success'})

def update_default_hidden(jam_id, song_entry):
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []

    # Create a set to store unique user IDs
    unique_users = set()

    # Loop through each dictionary and add unique user IDs to the set
    for entry in songs[jam_id]:
        unique_users.update(entry['hiders'])
        unique_users.update(entry['showers'])
        unique_users.update(entry['submitters'])

    # Get the total count of unique users
    user_count = len(unique_users)

    # Decide whether to show this song by deault
    hiders = len(song_entry['hiders'])
    showers = len(song_entry['showers'])

    # if most people have hidden it
    # (and hardly anyone has unhidden it)
    # then hide it by default for everyone
    if (hiders > (user_count // 2) and (showers <= (user_count // 3))):
      song_entry['default_hidden'] = True
    else:
      song_entry['default_hidden'] = False

      
@app.route('/set_mode', methods=['POST'])
def set_mode():
    jam_id = request.json.get('jam_id')
    user_id = request.json.get('user_id')
    mode = request.json.get('mode')

    if mode not in VALID_MODES:
        return jsonify({'status': 'error', 'message': 'invalid mode'}), 400

    print(user_id, "voted mode", mode, "in", jam_id)
    mode_votes.setdefault(jam_id, {})[user_id] = mode
    bump(jam_id)

    # Return the new effective mode (may differ from the user's pick if outvoted).
    return jsonify({'status': 'success', 'mode': compute_mode(jam_id)})


@app.route('/get_songs', methods=['GET'])
def get_songs():
    jam_id = request.args.get('jam_id', 'default')
    if not songs.get(jam_id, None):
      songs[jam_id] = []

    # Conditional poll: if the client's last-seen version still matches, nothing
    # changed, so return a tiny response and skip the sort + full serialization.
    client_v = request.args.get('v', type=int)
    current_v = versions.get(jam_id, 0)
    if client_v is not None and client_v == current_v:
      return jsonify({'changed': False, 'version': current_v})

    sorted_songs = sorted(songs[jam_id], key=lambda x: len(x['submitters']), reverse=True)
    return jsonify({'changed': True, 'version': current_v, 'mode': compute_mode(jam_id), 'songs': sorted_songs})

@app.route('/qr/<string:jam_id>.png')
def generate_qr(jam_id):
    # Create the QR code URL from the live host, so it works on any domain
    url = request.host_url + jam_id
    qr_filename = '{}.png'.format(jam_id)
    qr_filepath = os.path.join(qr_cache_dir, qr_filename)

    # Check if the file already exists
    if not os.path.exists(qr_filepath):
        # Generate a new QR code
        qr = qrcode.make(url)
        qr.save(qr_filepath)

    try:
        # Return the existing or newly generated QR code image
        return send_file(qr_filepath, mimetype='image/png')
    except Exception as e:
        abort(404)
  
if __name__ == '__main__':
    app.run(debug=True)
 
