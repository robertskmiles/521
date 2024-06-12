from flask import Flask, render_template, request, jsonify, make_response

app = Flask(__name__, template_folder='templates')
app.secret_key = 'secret_key'

# In-memory storage
songs = {'default':[]}
user_id_counter = 0  # Counter to give each user a unique ID

@app.route('/')
def index():
    global user_id_counter

    print(request.cookies)
    jam_id = request.args.get('jam_id', 'default')
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id_counter += 1
        user_id = str(user_id_counter)

    user_submitted_songs = [song['song'] for song in songs[jam_id] if user_id in song['submitters']]

    response = make_response(render_template('index.html', songs=songs[jam_id], user_submitted_songs=user_submitted_songs, user_id=user_id))
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
        songs[jam_id].append({'song': song_name, 'submitters': [user_id]})

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

@app.route('/get_songs', methods=['GET'])
def get_songs():
    jam_id = request.args.get('jam_id', 'default')
    print(jam_id, songs)
    
    # Check if this is a new jam, make it if so
    if not songs.get(jam_id, None):
      songs[jam_id] = []
      
    sorted_songs = sorted(songs[jam_id], key=lambda x: len(x['submitters']), reverse=True)
    return jsonify(sorted_songs)


if __name__ == '__main__':
    app.run(debug=True)
 
