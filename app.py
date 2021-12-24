import json
from collections import defaultdict

from sqlalchemy.sql import text

from flask import request
from flask import Flask
from flask import render_template
from flask import jsonify

from flask_sqlalchemy import SQLAlchemy
from video_board.model import Base
from video_board.model import Video
from video_board.model import LabelType
from video_board.model import BoundingBox
from video_board.model import Frame
from video_board.model import Thing
from video_board.db_tools import insert_interpolated_bounding_boxes_on_video

from video_board.config import read_config
from video_board.config import validate_config
from video_board.config import SQLALCHEMY_DATABASE_URI_FIELD


conf = read_config('config.yml')
validate_config(conf)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = conf[SQLALCHEMY_DATABASE_URI_FIELD]
app.secret_key = 'l#ek3*0'
app.debug = True

db = SQLAlchemy(app=app, model_class=Base)


@app.route('/')
def index():
    videos = list(db.session.query(Video))
    annotated = set(get_annotated_video_ids())
    nb_annotated = len(annotated)
    for video in videos:
        video.annotation = video.id in annotated
    videos = sorted(videos, key=lambda v: v.annotation)
    context = {
        'videos': videos,
        'thumbnail': True,
        'title': 'Videos',
        'nb_annotated': nb_annotated,
    }
    return render_template('video_list.html', **context)


@app.route('/video/random')
def random_video():
    import random
    video_ids = [vid.id for vid in db.session.query(Video)]
    video_id = random.choice(video_ids)
    return video(video_id)


@app.route('/video/random_non_annotated')
def random_non_annotated_video():
    import random
    video_ids = get_non_annotated_video_ids()
    video_id = random.choice(video_ids)
    return video(video_id)



@app.route('/video/<video_id>')
def video(video_id):
    video = db.session.query(Video).get(video_id)
    video_data = {
        'id': video.id,
        'location': '/static/videos/{}'.format(video.id),
        'is_image_sequence': False,
        'annotated': _is_annotated(video_id),
        'verified': False,
        'rejected': False,
        'start_time': None,
        'end_time': None,
    }
    video_data = json.dumps(video_data)
    labels = db.session.query(LabelType).all()
    label_data = [
        {'name': label.name, 'id': label.id, 'color': 'blue'}
        for label in labels
    ]
    context = {
        'label_data': label_data,
        'video_data': video_data,
        'image_list': 0,
        'image_list_path': '',
        'help_url': 'help',
        'help_embed': 'help',
        'survey': 'false',
        'help_content': 'help'
    }
    return render_template('video.html', **context)


def get_annotated_video_ids():
    q = db.session.execute(text(
        "SELECT video.id FROM video, bounding_box, frame "
        "WHERE bounding_box.frame_id = frame.id AND "
        "frame.video_id = video.id "
        "GROUP BY video.id "
        "HAVING COUNT(*) > 0"
    ))
    return [video_id for video_id, in q]


def get_non_annotated_video_ids():
    video_ids = set(video.id for video in db.session.query(Video))
    annotated = set(get_annotated_video_ids())
    return list(video_ids - annotated)



def _is_annotated(video_id):
    q = db.session.query(BoundingBox, Frame, Video)
    q = q.filter(Video.id == video_id)
    q = q.filter(Frame.video_id == Video.id)
    q = q.filter(Frame.id == BoundingBox.frame_id)
    nb_bounding_boxes = q.count()
    return nb_bounding_boxes > 0


@app.route('/annotation/<video_id>/', methods=['GET', 'POST'])
def annotation(video_id):
    if request.method == 'GET':
        things = defaultdict(list)
        video = db.session.query(Video).get(video_id)
        fps = video.frames_per_second
        thing_label = {}
        q = db.session.query(BoundingBox, Frame, Video)
        q = q.filter(Video.id == video_id)
        q = q.filter(Frame.video_id == Video.id)
        q = q.filter(Frame.id == BoundingBox.frame_id)
        q = q.filter(BoundingBox.is_interpolated==False)
        for bbox, frame, _ in q:
                thing_label[bbox.thing_id] = bbox.thing.label_type.name
                things[bbox.thing_id].append({
                        'x': bbox.x,
                        'y': bbox.y,
                        'w': bbox.w,
                        'h': bbox.h,
                        'frame': frame.index / fps,
                        'continueInterpolation': True,
                })
        annots = []
        for thing_id, bboxes in things.items():
            bboxes = sorted(bboxes, key=lambda ks: ks['frame'])
            bboxes[-1]['continueInterpolation'] = False
            annot = {
                'keyframes': bboxes,
                'type': thing_label[thing_id],
                'color': 'blue',
                'id': thing_id,
            }
            annots.append(annot)
        return jsonify(annots)
    elif request.method == 'POST':
        data = request.get_json()
        q = db.session.query(BoundingBox, Frame, Video)
        q = q.filter(Video.id == video_id)
        q = q.filter(Frame.video_id == Video.id)
        q = q.filter(Frame.id == BoundingBox.frame_id)
        with db.session.no_autoflush:
            for bbox, frame, _ in q:
                db.session.delete(bbox)
                db.session.delete(bbox.thing)
        db.session.commit()
        annots = data['annotation']
        video = Video.query.get(video_id)
        frames = sorted(video.frames, key=lambda f: f.index)
        for annot in annots:
            label_name = annot['type']
            label_name = label_name.strip()
            keyframes = annot['keyframes']
            try:
                label = db.session.query(LabelType).filter(
                    LabelType.name == label_name).one()
            except Exception:
                label = LabelType(label_name)
                db.session.add(label)
                db.session.commit()
            thing = Thing(label)
            db.session.add(thing)
            db.session.commit()
            for kf in keyframes:
                frame_index = int(kf['frame'] * video.frames_per_second)
                frame_index = min(len(frames) - 1, frame_index)
                frame = frames[frame_index]
                x, y, w, h = kf['x'], kf['y'], kf['w'], kf['h']
                bbox = BoundingBox(frame, thing)
                bbox.is_interpolated = False
                bbox.x = x
                bbox.y = y
                bbox.w = w
                bbox.h = h
                db.session.add(bbox)
        db.session.commit()
        insert_interpolated_bounding_boxes_on_video(db.session, video)
        return 'success'


@app.template_filter('yesno')
def yesno(val):
    return 'True' if val else 'False'
