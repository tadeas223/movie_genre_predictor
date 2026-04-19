import tkinter as tk
from tkinter import filedialog, messagebox

import ffmpeg
import os
import glob
import os
import pandas as pd
import librosa
import numpy as np
import shutil
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler
import re
import cv2
import threading

# copy of processing code

def safe_name(name):
    return re.sub(r'[^\w\-_\. ]', '_', name)

def array_to_columns(arr, name):
    return {f"{name}_{i}": val for i, val in enumerate(arr)}

def array_2d_to_columns(arr, name):
    flat_dict = {}
    for i, row in enumerate(arr):
        for j, val in enumerate(row):
            flat_dict[f"{name}_{i}_{j}"] = val
    return flat_dict

def chop_video(video_path, output_pattern, clip_duration=600):
    pattern_check = output_pattern.replace("%03d", "*")
    existing_clips = glob.glob(pattern_check)

    if existing_clips:
        return "exists"

    # stream copy
    try:
        (
            ffmpeg
            .input(video_path)
            .output(
                output_pattern,
                c='copy',
                f='segment',
                segment_time=clip_duration,
                reset_timestamps=1
            )
            .overwrite_output()
            .run(quiet=True)
        )
        return "copy"
    except ffmpeg.Error:
        pass

    # reencode if copy fails
    try:
        (
            ffmpeg
            .input(video_path)
            .output(
                output_pattern,
                vcodec='libx264',
                preset='ultrafast',
                crf=28,
                acodec='aac',
                audio_bitrate='128k',
                f='segment',
                segment_time=clip_duration,
                reset_timestamps=1
            )
            .overwrite_output()
            .run(quiet=True)
        )
        return "reencode"
    except ffmpeg.Error:
        return None

def process_chop(movie, root_dir, output_dir):
    print(f"chopping: {movie['file_path']}")
    safe_title = safe_name(movie['title'])
    dir_name = f"{safe_title} ({movie['year']})"
    dir_path = os.path.join(output_dir, dir_name)
    os.makedirs(dir_path, exist_ok=True)

    video_input = os.path.join(root_dir, movie['file_path'])
    if not os.path.isfile(video_input):
        print(f"video not found: {video_input}")
        return pd.DataFrame()

    output_pattern = os.path.join(dir_path, f"{safe_title}_{movie['year']}_%03d.mkv")

    result = chop_video(video_input, output_pattern)
    if result == "copy":
        print(f"stream copy: {movie['title']}")
    elif result == "reencode":
        print(f"reencode: {movie['title']}")
    elif result == "exists":
        print(f"clips exist: {movie['title']}")
    else:
        print(f"failed {movie['title']}")
        return pd.DataFrame()

    video_extensions = (".mkv", ".mp4", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".webm")
    clips = sorted(
        f for f in os.listdir(dir_path)
        if os.path.isfile(os.path.join(dir_path, f)) and f.lower().endswith(video_extensions)
    )

    entries = pd.DataFrame()
    
    for clip_file in clips:
        clip_path_rel = os.path.relpath(os.path.join(dir_path, clip_file), output_dir)
        entry = {
            "csfd_id": movie["csfd_id"],
            "title": movie["title"],
            "year": movie["year"],
            "genres": movie["genres"],
            "clip_path": clip_path_rel
        }
        
        entries = pd.concat([entries, pd.DataFrame([entry])], ignore_index=True)

    return entries

# enable gpu acceleration
cv2.ocl.setUseOpenCL(True)

def process_video(video_clip, root_dir, width=256, height=144, segments=32):
    print(f"processing video: {video_clip['clip_path']}")
    video_path = os.path.join(root_dir, video_clip["clip_path"])
    
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")

    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= segments:
        frames_to_check = list(range(total_frames))
    else:
        step = total_frames / (segments)
        frames_to_check = [int(i * step) for i in range(segments + 1)]

    motion_values = []
    brightness_values = []
    avg_color_values = []

    prev_gray = None

    for frame_idx in frames_to_check:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = capture.read()
        if not ret:
            break

        frame = cv2.resize(frame, (width, height))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # motion
        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray)
            motion_values.append(float(diff.mean()))
        else:
            motion_values.append(0.0)

        # brightness
        brightness_values.append(float(gray.mean()))

        # avg color
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mean_bgr = frame.mean(axis=(0, 1))
        avg_color_values.append((
            float(mean_bgr[2]),
            float(mean_bgr[1]),
            float(mean_bgr[0])
        ))

        prev_gray = gray

    capture.release()

    row_data = {
        **array_to_columns(motion_values, "motion"),
        **array_to_columns(brightness_values, "brightness"),
        **array_2d_to_columns(avg_color_values, "color")
    }

    df = pd.DataFrame([row_data])
    return df

def process_audio(video_clip, root_dir, segments=32, sample_rate=8000):
    print(f"processing audio: {video_clip['clip_path']}")
    video_path = os.path.join(root_dir, video_clip["clip_path"])

    out, _ = (
        ffmpeg
        .input(video_path)
        .output('pipe:', format='f32le', acodec='pcm_f32le', ac=1, ar=sample_rate)
        .run(capture_stdout=True, capture_stderr=True)
    )
    
    y = np.frombuffer(out, np.float32)
    total_samples = len(y)
    
    segment_size = total_samples // segments
    rms_values = []
    amp_values = []
    mfcc_values = []
    
    for i in range(segments):
        start = i * segment_size
        end = start + segment_size if i < segments - 1 else total_samples
        segment = y[start:end]
        
        rms = np.sqrt(np.mean(segment**2))
        amp_mean = np.mean(np.abs(segment))
        mfccs = librosa.feature.mfcc(y=segment, sr=sample_rate, n_mfcc=13)
        mfcc_mean = np.mean(mfccs, axis=1)
        
        rms_values.append(rms)
        amp_values.append(amp_mean)
        mfcc_values.append(mfcc_mean)
    
    row_data = {
        **array_to_columns(amp_values, "amp"),
        **array_to_columns(rms_values, "rms"),
        **array_2d_to_columns(mfcc_values, "mfcc")
    }

    df = pd.DataFrame([row_data])
    return df


def process_movie(movie, root_dir, output_dir):
    chopped = process_chop(movie.to_dict(), root_dir, output_dir)

    all_rows = []
    for _, clip in chopped.iterrows():
        video = process_video(clip, output_dir)
        audio = process_audio(clip, output_dir)

        clip_dict = clip.to_dict()
        video_dict = video.iloc[0].to_dict()
        audio_dict = audio.iloc[0].to_dict()

        merged_row = {**clip_dict, **video_dict, **audio_dict}

        all_rows.append(merged_row)
    return pd.DataFrame(all_rows)


def prepare_dataset_X(dataset):
    X = dataset.drop(columns=[
    'genres', 'genre_single', 'title', 'clip_path'
    ], errors='ignore')

    # X = X.select_dtypes(include=[np.number])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_scaled = np.nan_to_num(X_scaled)

    return X_scaled
    
def prepare_dataset_y(dataset):
    dataset['genres'] = dataset['genres'].apply(
        lambda genre_list: [
            g.strip()
            for item in genre_list
            for g in re.split(r'\s+', item)
            if g.strip()
        ]
    )

    print(dataset['genres'])

    mlb = MultiLabelBinarizer()
    y = mlb.fit_transform(dataset['genres'])

    return y, mlb

# gui code

def predict_genres():
    import os
    import shutil
    import pickle
    import pandas as pd
    from tensorflow.keras.models import load_model
    from tkinter import messagebox

    video_path = video_path_var.get()
    if not video_path:
        messagebox.showwarning("no file", "select a video file first")
        return

    dir_path = "temp"

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"directory created: {dir_path}")
    else:
        print(f"directory already exists: {dir_path}")

    movie = pd.Series({
        "csfd_id": 0,
        "title": "unknown",
        "year": 0,
        "genres": [],
        "file_path": video_path
    })

    df = process_movie(movie, os.path.dirname(video_path), dir_path)

    model = load_model("model.keras")

    X = prepare_dataset_X(df)

    with open("mlb.pkl", "rb") as mlb_file:
        mlb = pickle.load(mlb_file)

    pred_probs = model.predict(X)
    avg_probs = pred_probs.mean(axis=0)
    pred_labels = (avg_probs >= 0.5).astype(int)

    predicted_genres = [genre for i, genre in enumerate(mlb.classes_) if pred_labels[i] == 1]

    if predicted_genres:
        output_var.set(", ".join(predicted_genres))
    else:
        output_var.set("no genres predicted")

    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        print(f"directory removed: {dir_path}")
    else:
        print(f"directory does not exist: {dir_path}")

def predict_genres_threaded():
    predict_button.config(state=tk.DISABLED)
    output_var.set("processing...")

    def task():
        try:
            predict_genres()
        finally:
            predict_button.config(state=tk.NORMAL)

    threading.Thread(target=task, daemon=True).start()

def browse_file():
    file_path = filedialog.askopenfilename(
        title="select movie file",
        filetypes=[("video files", "*.mp4 *.avi *.mov *.mkv"), ("all files", "*.*")]
    )
    if file_path:
        video_path_var.set(file_path)


root = tk.Tk()
root.title("movie genre prediction")

video_path_var = tk.StringVar()
tk.Label(root, text="select a movie:").grid(row=0, column=0, sticky="e")
entry_video = tk.Entry(root, textvariable=video_path_var, width=40)
entry_video.grid(row=0, column=1, padx=5, pady=5)
browse_button = tk.Button(root, text="browse", command=browse_file)
browse_button.grid(row=0, column=2, padx=5, pady=5)

predict_button = tk.Button(root, text="predict", command=predict_genres_threaded)
predict_button.grid(row=1, column=0, columnspan=3, pady=10)

tk.Label(root, text="predicted genres:").grid(row=2, column=0, sticky="e")
output_var = tk.StringVar()
output_label = tk.Label(root, textvariable=output_var, fg="blue")
output_label.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

root.mainloop()