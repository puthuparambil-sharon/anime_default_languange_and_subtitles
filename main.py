import subprocess
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
SKIP_EXISTING = True
MAX_WORKERS = 4  # Number of files to process at once


def get_track_logic(input_path):
    try:
        data = subprocess.check_output(["mkvmerge", "-J", str(input_path)])
        mkv_info = json.loads(data)
    except Exception as e:
        print(f"Error reading {input_path.name}: {e}")
        return None

    audio_tracks, subtitle_tracks, video_tracks = [], [], []
    jpn_audio_id, full_eng_sub_id = None, None

    for track in mkv_info.get("tracks", []):
        t_id, t_type = track["id"], track["type"]
        props = track.get("properties", {})
        lang = props.get("language", "")
        name = props.get("track_name", "").lower()

        if t_type == "video":
            video_tracks.append(t_id)
        elif t_type == "audio":
            audio_tracks.append(t_id)
            if lang == "jpn": jpn_audio_id = t_id
        elif t_type == "subtitles":
            subtitle_tracks.append(t_id)
            if lang == "eng":
                # Priority logic:
                # 1. Name contains 'full'
                # 2. Doesn't contain 'signs' or 'songs'
                if "full" in name:
                    full_eng_sub_id = t_id
                elif not any(x in name for x in ["signs", "songs", "forced"]) and full_eng_sub_id is None:
                    full_eng_sub_id = t_id

    return {
        "video": video_tracks, "audio": audio_tracks, "subs": subtitle_tracks,
        "jpn_audio": jpn_audio_id, "eng_sub": full_eng_sub_id
    }


def process_file(input_file, output_file):
    if SKIP_EXISTING and output_file.exists():
        print(f"SKIPPING (Exists): {input_file.name}")
        return

    tracks = get_track_logic(input_file)
    if not tracks or tracks["jpn_audio"] is None:
        print(f"SKIPPING (No JPN Audio): {input_file.name}")
        return

    cmd = ["mkvmerge", "-o", str(output_file)]

    # Flags logic
    flags = [(tracks['jpn_audio'], 'yes')]
    if tracks['eng_sub'] is not None:
        flags.append((tracks['eng_sub'], 'yes'))

    for tid in tracks['audio'] + tracks['subs']:
        if tid not in [tracks['jpn_audio'], tracks['eng_sub']]:
            flags.append((tid, 'no'))

    for tid, state in flags:
        cmd.extend(["--default-track-flag", f"{tid}:{state}", "--forced-display-flag", f"{tid}:{state}"])

    # Order logic
    ordered_ids = tracks["video"] + [tracks["jpn_audio"]]
    ordered_ids += [tid for tid in tracks["audio"] if tid != tracks["jpn_audio"]]
    if tracks["eng_sub"] is not None:
        ordered_ids.append(tracks["eng_sub"])
    ordered_ids += [tid for tid in tracks["subs"] if tid != tracks["eng_sub"]]

    cmd.extend(["--track-order", ",".join([f"0:{tid}" for tid in ordered_ids]), str(input_file)])

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"SUCCESS: {input_file.name}")
    except subprocess.CalledProcessError as e:
        print(f"FAILED: {input_file.name} | Error: {e.stderr.decode()[:200]}")


def main():
    script_dir = Path(__file__).parent.resolve()
    source_dir, target_dir = script_dir / "Original", script_dir / "Modified"
    target_dir.mkdir(parents=True, exist_ok=True)

    files_to_process = list(source_dir.rglob("*.mkv"))
    print(f"Found {len(files_to_process)} files. Processing with {MAX_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for input_path in files_to_process:
            rel_path = input_path.relative_to(source_dir)
            output_path = target_dir / rel_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            executor.submit(process_file, input_path, output_path)


if __name__ == "__main__":
    main()
