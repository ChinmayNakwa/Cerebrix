# backend/ingestion/video_stage.py
"""
Video stage: for each downloaded lecture, fetches the captions and finds the slides shown on screen.
Each slide is then transcribed by a vision model and uploaded to Cloudinary, one resumable step per slide.

    python -m backend.ingestion.video_stage --lectures 18 4
    python -m backend.ingestion.video_stage --lectures 18 --local
    python -m backend.ingestion.video_stage

Keyframes are filtered down to slide and screen captures before deduplication, since camera shots of
the lecturer never repeat exactly. Slides are then grouped by content rather than by perceptual hash:
the hash mostly sees the shared slide template, so it merged different text slides.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import cloudinary
import cloudinary.uploader
import numpy as np
import yt_dlp
from PIL import Image
from youtube_transcript_api import NoTranscriptFound, YouTubeTranscriptApi

from backend.config import settings
from backend.ingestion.runner import CACHE_DIR, connect, fingerprint, run_many, run_stage, stage_key, upsert_source
from backend.ingestion.vision import read_image, vision_client

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

# Manual captions first: they are punctuated and spell the maths terms correctly.
CAPTION_LANGUAGES = ["en-US", "en", "en-GB"]
FRAME_WIDTH = 1280
# A slide has a flat background: neighbouring pixels are equal, or one colour covers much of the frame.
SLIDE_MAX_NOISE = 0.25
SLIDE_MIN_FLAT = 0.4
# Grey-level difference that counts as a changed pixel, and the share of a frame's content that may
# change while it still counts as contained in another frame.
CHANGE_LEVEL = 24
CONTAINED = 0.1
# Bump when the frame selection changes, so cached slide sets are redone.
FRAMES_VERSION = "v1"
CLOUDINARY_FOLDER = "maths_ta/frames"
# Bump when the prompt changes, so cached slide transcriptions are redone.
PROMPT_VERSION = "v1"
PROMPT = (
    "This is a slide from a university lecture on probability. Transcribe it to markdown. "
    "Write every mathematical expression as LaTeX, inline as $...$ and display equations as $$...$$. "
    "Keep headings, lists and tables. For a chart, diagram or picture, write one line starting with "
    "'Figure:' that says what it shows. Ignore logos and watermarks. "
    "Output only the transcription, with no commentary."
)


def find_lectures() -> list[dict]:
    """Matches the files in VIDEO_DIR to the playlist entries by title. Returns them in lecture order."""
    playlist_path = CACHE_DIR / "playlist.json"
    if playlist_path.exists():
        entries = json.loads(playlist_path.read_text(encoding="utf-8"))
    else:
        with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "no_warnings": True}) as ydl:
            playlist = ydl.extract_info(settings.YOUTUBE_PLAYLIST_URL, download=False)
        entries = [{"video_id": e["id"], "title": e["title"]} for e in playlist["entries"]]
        playlist_path.parent.mkdir(parents=True, exist_ok=True)
        playlist_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    lectures = []
    for entry in entries:
        # download_videos.py saved each file under its title with these characters removed.
        path = Path(settings.VIDEO_DIR) / (re.sub(r'[\\/*?:"<>|]', "", entry["title"]).strip() + ".mp4")
        number = re.search(r"Lecture (\d+)\s*$", entry["title"])
        if not (path.exists() and number):
            print(f"  - No video file for: {entry['title']}")
            continue
        lectures.append({**entry, "lecture": int(number.group(1)), "path": path,
                         "url": f"https://www.youtube.com/watch?v={entry['video_id']}"})
    return sorted(lectures, key=lambda lecture: lecture["lecture"])


def _fetch_captions(video_id: str) -> dict:
    transcripts = YouTubeTranscriptApi().list(video_id)
    try:
        transcript = transcripts.find_manually_created_transcript(CAPTION_LANGUAGES)
    except NoTranscriptFound:
        transcript = transcripts.find_generated_transcript(CAPTION_LANGUAGES)
    fetched = transcript.fetch()
    return {
        "language": fetched.language_code,
        "generated": fetched.is_generated,
        "snippets": [{"start": s.start, "duration": s.duration, "text": " ".join(s.text.split())}
                     for s in fetched.snippets],
    }


def _keyframe_times(video: Path) -> list[float]:
    """Timestamps of the keyframes, read from the packet flags without decoding any video."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    )
    times = []
    for line in probe.stdout.splitlines():
        pts, _, flags = line.partition(",")
        if "K" in flags and pts != "N/A":
            times.append(float(pts))
    return sorted(times)


def _is_slide(image: Image.Image) -> bool:
    small = np.asarray(image.convert("RGB").resize((160, 90), Image.BILINEAR)).astype(np.int32)
    noise = np.median(np.abs(np.diff(small.mean(axis=2), axis=1)))
    # Share of the frame taken by its most common colour, at 5 bits per channel.
    colours = ((small[..., 0] >> 3) << 10) | ((small[..., 1] >> 3) << 5) | (small[..., 2] >> 3)
    flat = np.bincount(colours.ravel()).max() / colours.size
    return bool(noise < SLIDE_MAX_NOISE or flat >= SLIDE_MIN_FLAT)


def _thumbnail(path: Path) -> tuple[np.ndarray, bool]:
    """A 320x180 grey copy of the frame for comparisons, and whether the frame is a slide."""
    with Image.open(path) as image:
        image.draft("RGB", (320, 180))
        rgb = image.convert("RGB").resize((320, 180), Image.BILINEAR)
    return np.asarray(rgb.convert("L")).astype(np.int16), _is_slide(rgb)


def _content(grey: np.ndarray) -> np.ndarray:
    """
    Mask of the pixels that carry content. Any grey level that, with its near neighbours, covers a tenth
    of the frame is background: the slide colour, and the black bars beside a 4:3 slide.
    """
    nearby = np.convolve(np.bincount(grey.ravel(), minlength=256), np.ones(17), mode="same")
    return nearby[grey] < 0.1 * grey.size


def _is_crossfade(before: np.ndarray, frame: np.ndarray, after: np.ndarray) -> bool:
    """
    True when the frame is a mix of its neighbouring keyframes, caught mid-transition. The mix has to
    explain the frame much better than either neighbour alone, or than a black frame does.
    """
    a, b, x = (g.ravel().astype(np.float64) for g in (before, after, frame))
    baseline = min(np.abs(x - a).mean(), np.abs(x - b).mean(), np.abs(x).mean())
    if baseline < 2:
        return False
    (ca, cb), *_ = np.linalg.lstsq(np.stack([a, b], axis=1), x, rcond=None)
    fit = np.abs(x - ca * a - cb * b).mean()
    return bool(min(ca, cb) >= -0.05 and max(ca, cb) <= 0.9 and 0.1 <= ca + cb <= 1.1 and fit < 0.4 * baseline)


def _spans(seen: list[int], times: list[float]) -> list[list[float]]:
    """Turns the keyframe indexes a slide was seen at into [start, end] stretches of screen time."""
    step = times[-1] - times[-2]
    spans: list[list[float]] = []
    for index in seen:
        end = times[index + 1] if index + 1 < len(times) else times[index] + step
        if spans and spans[-1][1] == times[index]:
            spans[-1][1] = end
        else:
            spans.append([times[index], end])
    return [[round(start, 2), round(end, 2)] for start, end in spans]


def _select_slides(video: Path, folder: Path) -> dict:
    """Extracts the keyframes, keeps the slide captures and saves one image per distinct slide in folder."""
    times = _keyframe_times(video)

    with tempfile.TemporaryDirectory() as tmp:
        # -discard nokey drops packets in the demuxer, so it works for VP9 too (-skip_frame nokey does not).
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-discard", "nokey", "-i", str(video),
             "-vf", f"scale={FRAME_WIDTH}:-2", "-fps_mode", "vfr", "-q:v", "3", str(Path(tmp) / "f_%05d.jpg")],
            check=True, capture_output=True,
        )
        frames = sorted(Path(tmp).glob("f_*.jpg"))
        if len(frames) != len(times):
            raise RuntimeError(f"{video.name}: {len(frames)} frames extracted for {len(times)} keyframes")

        greys, is_slide = zip(*(_thumbnail(frame) for frame in frames))

        slides: list[dict] = []
        slide_frames = 0
        for index in range(len(frames)):
            if not is_slide[index]:
                continue
            if 0 < index < len(frames) - 1 and _is_crossfade(greys[index - 1], greys[index], greys[index + 1]):
                continue
            slide_frames += 1
            grey = greys[index]
            content = _content(grey)

            for slide in reversed(slides):
                changed = np.abs(grey - slide["grey"]) > CHANGE_LEVEL
                if (changed & slide["content"]).sum() <= CONTAINED * max(slide["content"].sum(), 1):
                    # Everything the slide showed is still there: the same slide, perhaps built further.
                    slide.update(grey=grey, content=content, frame=index)
                    slide["seen"].append(index)
                    break
                if (changed & content).sum() <= CONTAINED * max(content.sum(), 1):
                    # An earlier, less complete state of that slide.
                    slide["seen"].append(index)
                    break
            else:
                slides.append({"grey": grey, "content": content, "frame": index, "seen": [index]})

        folder.mkdir(parents=True, exist_ok=True)
        records = []
        for slide in slides:
            first = slide["seen"][0]
            target = folder / f"{first:05d}.jpg"
            shutil.copyfile(frames[slide["frame"]], target)
            records.append({
                "keyframe": first,
                "start_sec": round(times[first], 2),
                "spans": _spans(slide["seen"], times),
                "file": str(target),
                "sha": hashlib.sha256(target.read_bytes()).hexdigest()[:32],
            })

    return {"keyframes": len(frames), "slide_frames": slide_frames, "slides": records}


def run_video_stage(lecture: dict, local: bool = False) -> dict:
    """
    Returns the captions and slides of one lecture, doing only the steps that are not already cached.
    With local=True the slides are found but not transcribed or uploaded.
    """
    video_id, path = lecture["video_id"], lecture["path"]
    source_id = f"video:{video_id}"
    content_hash = fingerprint(path)
    with connect() as conn:
        upsert_source(conn, source_id, "video", lecture["title"], uri=lecture["url"],
                      content_hash=content_hash, metadata={"lecture": lecture["lecture"], "file": path.name})

    captions = run_stage(source_id, "video_captions",
                         stage_key("video_captions", video=video_id, languages=CAPTION_LANGUAGES),
                         lambda: _fetch_captions(video_id))

    frames_key = stage_key("video_frames", file=content_hash, width=FRAME_WIDTH, noise=SLIDE_MAX_NOISE,
                           flat=SLIDE_MIN_FLAT, level=CHANGE_LEVEL, contained=CONTAINED, version=FRAMES_VERSION)
    frames = run_stage(source_id, "video_frames", frames_key,
                       lambda: _select_slides(path, CACHE_DIR / "video_frames" / frames_key))
    slides = frames["slides"]

    texts: dict[str, str] = {}
    urls: dict[str, str] = {}
    if not local:
        client = vision_client()
        folder = f"{CLOUDINARY_FOLDER}/{video_id}"

        def transcribe(slide: dict) -> str:
            key = stage_key("video_vision", image=slide["sha"], model=settings.OLLAMA_VISION_MODEL,
                            prompt=PROMPT_VERSION)

            def call() -> dict:
                return {"model": settings.OLLAMA_VISION_MODEL,
                        "text": read_image(client, Path(slide["file"]).read_bytes(), PROMPT)}

            return run_stage(source_id, f"videovision_{slide['keyframe']:05d}", key, call)["text"]

        def upload(slide: dict) -> str:
            # The content hash is the public id, so a re-run never stores the same image twice.
            def call() -> dict:
                result = cloudinary.uploader.upload(slide["file"], public_id=slide["sha"], folder=folder,
                                                    overwrite=False, timeout=60)
                return {"url": result["secure_url"]}

            key = stage_key("video_upload", image=slide["sha"], folder=folder)
            return run_stage(source_id, f"videoupload_{slide['keyframe']:05d}", key, call)["url"]

        results, failures = run_many(slides, transcribe, max_workers=3)
        texts = {slide["sha"]: text for slide, text in results}
        results, upload_failures = run_many(slides, upload, max_workers=6)
        urls = {slide["sha"]: url for slide, url in results}
        if failures or upload_failures:
            print(f"  {len(failures)} transcription(s) and {len(upload_failures)} upload(s) failed; "
                  "re-run to retry them")

    return {
        "source_id": source_id,
        "lecture": lecture["lecture"],
        "title": lecture["title"],
        "url": lecture["url"],
        "captions": captions,
        "keyframes": frames["keyframes"],
        "slide_frames": frames["slide_frames"],
        "slides": [{**slide, "text": texts.get(slide["sha"]), "image_url": urls.get(slide["sha"])}
                   for slide in slides],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lectures", type=int, nargs="+", metavar="N", help="lecture numbers; default is all")
    parser.add_argument("--local", action="store_true", help="captions and slide selection only, no cloud calls")
    args = parser.parse_args()

    lectures = find_lectures()
    if args.lectures:
        lectures = [lecture for lecture in lectures if lecture["lecture"] in args.lectures]

    for lecture in lectures:
        result = run_video_stage(lecture, local=args.local)
        print(json.dumps({
            "lecture": result["lecture"],
            "captions": len(result["captions"]["snippets"]),
            "captions_generated": result["captions"]["generated"],
            "keyframes": result["keyframes"],
            "slide_frames": result["slide_frames"],
            "slides": len(result["slides"]),
            "transcribed": sum(slide["text"] is not None for slide in result["slides"]),
            "uploaded": sum(slide["image_url"] is not None for slide in result["slides"]),
        }))


if __name__ == "__main__":
    main()
