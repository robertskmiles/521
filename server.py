from flask import Flask, render_template, request, jsonify, make_response, send_file, abort
import qrcode
import os

app = Flask(__name__, template_folder='templates')
app.secret_key = 'secret_key'

# In-memory storage
songs = {'default':[]}
user_id_counter = 0  # Counter to give each user a unique ID

qr_cache_dir = os.path.join('static', 'qr')
# Ensure the cache directory exists
if not os.path.exists(qr_cache_dir):
  os.makedirs(qr_cache_dir)

  
@app.route('/<string:jam_id>')
@app.route('/')
def index(jam_id="default"):
    global user_id_counter

    print(request.cookies)
    # jam_id = request.args.get('jam_id', 'default')
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id_counter += 1
        user_id = str(user_id_counter)

    user_submitted_songs = [song['song'] for song in songs.get(jam_id, []) if user_id in song['submitters']]

    response = make_response(render_template('index.html', jam_id=jam_id, songs=songs.get(jam_id, []), user_submitted_songs=user_submitted_songs, user_id=user_id))
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

@app.route('/togglehidden', methods=['POST'])
def toggle_hidden():
    jam_id = request.json.get('jam_id')
    song_name = request.json.get('song')
    user_id = request.json.get('user_id')

    print(user_id, "(un)hid", song_name)
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
      
    song_entry = next((song for song in songs[jam_id] if song['song'] == song_name), None)
    if song_entry:
        if user_id in song_entry['hiders']:
            song_entry['hiders'].remove(user_id)
        else:
            song_entry['hiders'].append(user_id)
        
        # if user_id in song_entry['showers']:
        #     song_entry['showers'].remove(user_id)
        # else:
        #     song_entry['showers'].append(user_id)
            
        # decide whether to show this song by deault
        hiders = len(song_entry['hiders'])
        showers = len(song_entry['showers'])
        
        # if most people have hidden it
        # (and hardly anyone has unhidden it)
        # then hide it by default for everyone
        if (hiders > (user_count // 2) and (showers <= (user_count // 3))):
          song_entry['default_hidden'] = True
        else:
          song_entry['default_hidden'] = False
            
    return jsonify({'status': 'success'})

  
@app.route('/get_songs', methods=['GET'])
def get_songs():
    jam_id = request.args.get('jam_id', 'default')
    print(jam_id, songs)
    
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []
      
    sorted_songs = sorted(songs[jam_id], key=lambda x: len(x['submitters']), reverse=True)
    return jsonify(sorted_songs)

@app.route('/qr/<string:jam_id>.png')
def generate_qr(jam_id):
    # Create the QR code URL
    url = 'https://521.glitch.me/{}'.format(jam_id)
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
 
