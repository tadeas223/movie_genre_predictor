import os
import json
import argparse
import subprocess
import re
from multiprocessing import Pool, Manager, cpu_count

parser = argparse.ArgumentParser()
parser.add_argument("jsonl_file", help="input from the scraper")
parser.add_argument("output_dir", help="where to store the clips")
parser.add_argument("dataset_jsonl", help="metadata of the clips")
parser.add_argument("--base-dir", required=True, help="base directory to resolve relative input video paths")
parser.add_argument("--workers", type=int, default=cpu_count(), help="number of parallel workers")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

clip_duration = 600  # 10 minutes
base_dir = os.path.abspath(args.base_dir)
output_dir_abs = os.path.abspath(args.output_dir)


def safe_name(name):
    return re.sub(r'[^\w\-_\. ]', '_', name)


def reencode_and_segment(video_input, output_pattern):
    def run_ffmpeg(cmd):
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, preexec_fn=lambda: os.nice(10))

    try:
        run_ffmpeg([
            "ffmpeg", "-y", "-i", video_input,
            "-c", "copy", "-f", "segment",
            "-segment_time", str(clip_duration),
            "-reset_timestamps", "1",
            output_pattern
        ])
        return "copy"
    except subprocess.CalledProcessError:
        pass  
    
    try:
        run_ffmpeg([
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-hwaccel_output_format", "cuda",
            "-i", video_input,
            "-c:v", "h264_nvenc",
            "-preset", "p1", "-rc", "constqp", "-qp", "30", "-g", "300", "-bf", "0",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "segment", "-segment_time", str(clip_duration),
            "-reset_timestamps", "1",
            output_pattern
        ])
        return "reencode"
    except subprocess.CalledProcessError:
        return None


def process_movie(film, dataset_jsonl_path, output_dir_abs, base_dir):
    safe_title = safe_name(film['title'])
    folder_name = f"{safe_title} ({film['year']})"
    folder_path = os.path.join(output_dir_abs, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    video_input = film['file_path']
    if not os.path.isabs(video_input):
        video_input = os.path.join(base_dir, video_input)
    video_input = os.path.abspath(video_input)

    if not os.path.isfile(video_input):
        print(f"video not found: {video_input}")
        return 0
    
    print(f"processing video: {video_input}")

    output_pattern = os.path.join(folder_path, f"{safe_title}_{film['year']}_%03d.mkv")

    result = reencode_and_segment(video_input, output_pattern)
    if result == "copy":
        print(f"success (stream copy): {film['title']}")
    elif result == "reencode":
        print(f"success (reencode): {film['title']}")
    else:
        print(f"failed: {film['title']}")
        return 0

    video_extensions = (".mkv", ".mp4", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".webm")  # add more if needed
    clips = sorted(
        f for f in os.listdir(folder_path)
        if f.lower().endswith(video_extensions)  # allows all major video formats
    )
    count = 0
    with open(dataset_jsonl_path, 'a', encoding='utf-8') as out_f:
        for clip_file in clips:
            clip_path_abs = os.path.join(folder_path, clip_file)
            clip_path_rel = os.path.relpath(clip_path_abs, output_dir_abs)
            entry = {
                "csfd_id": film.get("csfd_id"),
                "title": film.get("title"),
                "year": film.get("year"),
                "genres": film.get("genres", []),
                "clip_path": clip_path_rel
            }
            json.dump(entry, out_f, ensure_ascii=False)
            out_f.write('\n')
            count += 1
    return count


def main():
    movies = []
    with open(args.jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                movies.append(json.loads(line))

    total_clips = 0
    dataset_jsonl_path = args.dataset_jsonl

    open(dataset_jsonl_path, 'w').close()

    with Pool(processes=args.workers) as pool:
        results = pool.starmap(
            process_movie,
            [(film, dataset_jsonl_path, output_dir_abs, base_dir) for film in movies]
        )
        total_clips = sum(results)
    
    print(f"total clips processed: {total_clips}")


if __name__ == "__main__":
    main()
