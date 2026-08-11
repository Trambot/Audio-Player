import os
import io
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from mutagen import File as MutagenFile
from pyngrok import ngrok

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///riff_vault.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ==========================================
# YOUR EXTERNAL MUSIC FOLDER PATH
# ==========================================
EXTERNAL_MUSIC_FOLDER = "D:/music/FLAC"
app.config["UPLOAD_FOLDER"] = EXTERNAL_MUSIC_FOLDER

db = SQLAlchemy(app)

# --- DATABASE SCHEMA ---
playlist_tracks = db.Table('playlist_tracks',
    db.Column('playlist_id', db.Integer, db.ForeignKey('playlist.id'), primary_key=True),
    db.Column('track_id', db.Integer, db.ForeignKey('track.id'), primary_key=True)
)

class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), unique=True, nullable=False)
    plays = db.Column(db.Integer, default=0)
    rating = db.Column(db.Integer, default=0)

class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    tracks = db.relationship('Track', secondary=playlist_tracks, lazy='subquery',
        backref=db.backref('playlists', lazy=True))

# --- AUTO-SYNC & M3U GENERATOR ---
def sync_library():
    print("🔄 Syncing library and generating .m3u playlists...")
    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        os.makedirs(app.config["UPLOAD_FOLDER"])

    folder_tracks_map = {}

    for root, dirs, files in os.walk(app.config["UPLOAD_FOLDER"]):
        folder_name = os.path.basename(root)
        if folder_name == os.path.basename(app.config["UPLOAD_FOLDER"]):
            folder_name = "Root"

        if folder_name not in folder_tracks_map:
            folder_tracks_map[folder_name] = []

        for f in files:
            if f.lower().endswith((".mp3", ".wav", ".flac")):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, app.config["UPLOAD_FOLDER"]).replace("\\", "/")
                
                track = Track.query.filter_by(filename=rel_path).first()
                if not track:
                    track = Track(filename=rel_path, plays=0, rating=0)
                    db.session.add(track)
                    db.session.commit()
                
                folder_tracks_map[folder_name].append(track)

    for folder_name, tracks in folder_tracks_map.items():
        if not tracks:
            continue
            
        playlist = Playlist.query.filter_by(name=folder_name).first()
        if not playlist:
            playlist = Playlist(name=folder_name)
            db.session.add(playlist)
            
        playlist.tracks = []
        for track in tracks:
            playlist.tracks.append(track)
            
        db.session.commit()

        if folder_name != "Root":
            m3u_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{folder_name}.m3u")
            with open(m3u_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for track in tracks:
                    file_only = track.filename.split('/')[-1]
                    f.write(f"#EXTINF:-1,{file_only}\n")
                    f.write(f"{track.filename}\n")
    print("✅ Sync complete!")

# --- ROUTES ---
@app.route("/")
def home():
    all_playlists = Playlist.query.all()
    search_query = request.args.get("q")
    playlist_id = request.args.get("playlist_id")
    current_playlist = None
    
    if playlist_id:
        current_playlist = Playlist.query.get(playlist_id)
        db_tracks = current_playlist.tracks if current_playlist else []
    elif search_query:
        db_tracks = Track.query.filter(Track.filename.ilike(f"%{search_query}%")).all()
    else:
        db_tracks = Track.query.all()
        
    return render_template("home.html", app_name="Riff Vault", 
                           tracks=db_tracks, playlists=all_playlists, 
                           current_playlist=current_playlist)

@app.route("/create_playlist", methods=["POST"])
def create_playlist():
    name = request.form.get("playlist_name")
    if name:
        if not Playlist.query.filter_by(name=name).first():
            new_pl = Playlist(name=name)
            db.session.add(new_pl)
            db.session.commit()
    return redirect(url_for("home"))

@app.route("/add_to_playlist", methods=["POST"])
def add_to_playlist():
    track_id = request.form.get("track_id")
    playlist_id = request.form.get("playlist_id")
    if track_id and playlist_id:
        track = Track.query.get(track_id)
        playlist = Playlist.query.get(playlist_id)
        if track and playlist and track not in playlist.tracks:
            playlist.tracks.append(track)
            db.session.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/add_play/<int:track_id>", methods=["POST"])
def add_play(track_id):
    track = Track.query.get(track_id)
    if track:
        track.plays += 1
        db.session.commit()
    return "", 204

@app.route("/stream/<path:filename>")
def stream_audio(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/cover/<path:filename>")
def get_cover(filename):
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    try:
        audio = MutagenFile(file_path)
        if audio:
            if hasattr(audio, 'pictures') and audio.pictures:
                art = audio.pictures[0].data
                return send_file(io.BytesIO(art), mimetype='image/jpeg')
            elif audio.tags:
                for tag in audio.tags.values():
                    if tag.__class__.__name__ == 'APIC':
                        return send_file(io.BytesIO(tag.data), mimetype=tag.mime)
    except Exception:
        pass
    transparent_pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
    return send_file(io.BytesIO(transparent_pixel), mimetype='image/gif')

# Route for PWA Service Worker
@app.route('/sw.js')
def sw():
    return app.send_static_file('sw.js')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        sync_library()
        
    # Replace with your actual auth token if required by Ngrok
    ngrok.set_auth_token("3Hi7OdOtZQ6Lx7U7gmF4nXU4q5w_4KV56fASbup47SxcfBv4N")
    
    public_url = ngrok.connect(5000).public_url
    print("\n" + "="*50)
    print(f"🚀 YOUR APP IS LIVE GLOBALLY AT: {public_url}")
    print("📱 Copy and paste this exact link into ANY phone browser!")
    print("="*50 + "\n")
    
    app.run(host="0.0.0.0", port=5000, debug=False)