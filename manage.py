#!/usr/bin/env python
import json
import os
from clize import run
from glob import glob
import tempfile
from shutil import copy
from shutil import move
from shutil import rmtree
from subprocess import call
from joblib import Parallel
from joblib import delayed
from sigtools.modifiers import autokwoargs

import numpy as np

from video_board.model import Video
from video_board.model import Frame
from video_board.model import LabelType
from video_board.db_tools import insert_interpolated_bounding_boxes_on_video
from video_board.db_tools import get_all_frames_with_labels
from video_board.config import IMAGES_PATH_FIELD
from video_board.config import VIDEOS_PATH_FIELD
from video_board.ramp import make_video_classification_problem
from video_board.utils import extract_frames

from app import app
from app import db
from app import conf


def create_db():
    """
    Create the database if it does not exist
    """
    db.create_all()


def clean():
    move('sqlite.db', 'sqlite.db.bak')
    create_db()
    if os.path.exists('static/videos'):
        rmtree('static/videos')
    os.mkdir('static/videos')
    if os.path.exists('static/frames'):
        rmtree('static/frames')
    os.mkdir('static/frames')


def download_videos_from_xls(filename):
    import pandas as pd
    dfs = pd.read_excel(filename, sheet_name=None)
    urls = []
    for k, d in dfs.items():
        urls += d.values.flatten().tolist()
    Parallel(n_jobs=-1)(delayed(download_video)(url) for url in urls)


def download_video(url, output_folder='downloaded'):
    cmd = 'youtube-dl --format mp4 --merge-output-format mp4 --output "{}/%(id)s.mp4" {}'
    cmd = cmd.format(output_folder, url)
    call(cmd, shell=True)


def add_videos(pattern):
    """
    Add a set of videos to the database as well as copy them
    to the videos folder with the right names
    """
    Parallel(n_jobs=-1)(
        delayed(add_video)(filename) for filename in glob(pattern))


def update_frames_per_second():
    from video_board.utils import get_frames_per_second
    videos = db.session.query(Video)
    for video in videos:
        video.frames_per_second = get_frames_per_second(
            os.path.join('downloaded', video.name))
        db.session.add(video)
        db.session.commit()
        print(video.name)


def add_video(filename):
    print('Processing video: {}'.format(filename))
    with tempfile.TemporaryDirectory() as tmpdirname:
        video = Video.from_filename(filename)
        db.session.add(video)
        db.session.commit()

        extract_frames(filename, tmpdirname)
        frame_filenames = sorted(glob(os.path.join(tmpdirname, '*.jpg')))
        copy(
            filename,
            os.path.join(
                conf[VIDEOS_PATH_FIELD],
                video.filename,
            )
        )
        print('Number of frames : {}'.format(len(frame_filenames)))
        for frame_filename in frame_filenames:
            frame_index, _ = os.path.basename(frame_filename).split('.')
            frame_index = int(frame_index)
            frame = Frame(video=video, index=frame_index)
            db.session.add(frame)
            db.session.commit()
            dest = os.path.join(
                conf[IMAGES_PATH_FIELD],
                frame.filename,
            )
            print('Copying frame {} to {}...'.format(frame_index, dest))
            copy(frame_filename, dest)


def add_label(name):
    label_type = LabelType(name)
    db.session.add(label_type)
    db.session.commit()


def remove_label(name):
    q = db.session.query(LabelType)
    q = q.filter(LabelType.name == name)
    label_type = q.one()
    db.session.delete(label_type)
    db.session.commit()


def rename_label(name, new_name):
    q = db.session.query(LabelType)
    q = q.filter(LabelType.name == name)
    label_type = q.one()
    label_type.name = new_name
    db.session.add(label_type)
    db.session.commit()


@autokwoargs
def make_video_classification_ramp(
    split_by='videos',
    background_strategy='none',
    video_labels='video_labels.json',
    nb_frames=None,
    test_size=0.1,
    dest_path='ramp-kits/last',
    seed=42
):
    """
    Make a RAMP kit with the available labels

    Parameters
    ----------

    split_by : 'videos' or 'frames'
        whether to split the train and test sets using videos
        or frames
    background_strategy : 'none' or 'rest_is_background'
        if 'none' does not include background frames
        if 'rest_is_background' we consider all frames non-annotated
        from annotated videos as 'background', meaning all their labels
        indicator will be set to zero.
    video_labels : str
        filename where the dictionary from frame labels to video labels
        is defined. we consider to define video labels as a simple rule
        if frame has label X, then video has label video_labels[X].
    nb_frames : int or None
        number of frames to use. if None use all frames
        of all videos which have at least one frame annotated.
    test_size : float between 0 and 1
        ratio of test size
    dest_path : str
        destination path of where the kit will be created
    """
    if os.path.exists(dest_path):
        print('"{}" already exists, please remove it.'.format(dest_path))
        return
    frame_to_video_label_map = json.load(open(video_labels))
    label_names = [lt.name for lt in db.session.query(LabelType)]
    if background_strategy == 'none':
        frames = get_all_frames_with_labels(db.session, label_names)
    elif background_strategy == 'rest_is_background':
        pos_frames = get_all_frames_with_labels(db.session, label_names)
        videos = set([frame.video for frame in pos_frames])
        pos_frames_ids = set(frame.id for frame in pos_frames)
        neg_frames = [
            frame
            for video in videos
            for frame in video.frames
            if frame.id not in pos_frames_ids
        ]
        frames = pos_frames + neg_frames
    else:
        raise ValueError('Wrong background strategy : "{}"'.format(
            background_strategy))
    if nb_frames:
        nb_frames = int(nb_frames)
        rng = np.random.RandomState(42)
        rng.shuffle(frames)
        frames = frames[0:nb_frames]
    print('Label names to use : {}'.format(label_names))
    print('Total number of frames to use : {}'.format(len(frames)))
    video_label_names = list(set(frame_to_video_label_map.values()))
    make_video_classification_problem(
        conf,
        frames,
        label_names,
        video_label_names,
        frame_to_video_label_map,
        test_size,
        dest_path,
        split_by=split_by,
        seed=seed,
    )


def insert_interpolated_bounding_boxes():
    videos = db.session.query(Video)
    for video in videos:
        insert_interpolated_bounding_boxes_on_video(db.session, video)


def serve(host='0.0.0.0', port=5000):
    app.run(host=host, port=port)


if __name__ == '__main__':
    run([
        clean,
        create_db,
        add_videos,
        add_label,
        remove_label,
        rename_label,
        make_video_classification_ramp,
        serve,
        insert_interpolated_bounding_boxes,
        download_videos_from_xls,
        download_video,
        update_frames_per_second,
    ])
