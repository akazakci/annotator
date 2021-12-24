# What is it ?

This is a video annotation tool that is integrated with the video board (https://github.com/mehdidc/video_board) 
database. It is based on BeaverDam (https://github.com/antingshen/BeaverDam) and has been rewritten in Flask
to facilitate further integration with the RAMP.

# How to install ?

```pip install -r requirements.txt```

You will also need ffmpeg and ffprobe to extract frames from the videos.

- On OSX: ```brew install ffmpeg```
- On Ubuntu: ```sudo apt install ffmpeg```
- On Arch: ```sudo pacman -S ffmpeg``` 

# How to run ?

```python manage.py create-db``` to create the database.

```python manage.py serve``` to launch the web server.

# How to add videos to the DB ?

```python manage.py add-videos <pattern>``` 

where pattern is a glob pattern(https://docs.python.org/3/library/glob.html) specifying the set of 
videos.

e.g.,

```python manage.py add-videos 'videos/*.mp4'```

# How to add labels to the DB ?

```python manage.py add-label-type <name>```

e.g.,

```python manage.py add-label-type wine```

# How to make a RAMP kit based on annotations ?

```python manage.py make-ramp```

# How to modify the database configuration ?

check and modify config.yml
