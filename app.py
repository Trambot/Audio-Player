from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy   
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///riff_vault.db"
db = SQLAlchemy(app)

class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150), unique=True, nullable=False)
    plays = db.Column(db.Integer, default=0)
    rating = db.Column(db.Integer, default=0)
        
@app.route("/")
def home():
    raw_files = os.listdir("static/audio")
    tracks = []
    for i in raw_files:
        if i.endswith((".mp3", ".wav", ".flac")):
            tracks.append(i)
    # We pass the title and the tracks list to the HTML
    for i in tracks:
        existing_track = Track.query.filter_by(filename=i).first()
        
        if existing_track is None:
            new_song = Track(filename=i, plays=0, rating=0)
            db.session.add(new_song)
            db.session.commit()
    db_tracks = Track.query.all()        
    return render_template("home.html", app_name="Riff Vault", tracks=db_tracks)
@app.route("/add_play/<int:track_id>", methods=["POST"])
def add_play(track_id):
    # 1. Find the track by its unique ID
    track = Track.query.get(track_id)
    
    # 2. If found, increment the play count and save
    if track:
        track.plays += 1
        db.session.commit()
        
    # 3. Return a clean empty response (HTTP 204 = No Content)
    return "", 204
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create the database tables if they don't exist
    app.run(debug=True)
