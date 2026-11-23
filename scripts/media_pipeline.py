"""本地试跑工具：检查素材、转写、按智能体审核结果剪辑。"""
import argparse
import json
import subprocess
from pathlib import Path


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def probe(path):
    import av
    with av.open(str(path)) as media:
        return {
            "duration": media.duration / av.time_base if media.duration else None,
            "streams": [{"type": s.type, "codec": s.codec_context.name,
                         "width": getattr(s.codec_context, "width", None),
                         "height": getattr(s.codec_context, "height", None)} for s in media.streams],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["probe", "transcribe", "render", "frames"])
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == "probe":
        result = probe(args.source)
        write_json(args.output / "media_info.json", result)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "transcribe":
        from faster_whisper import WhisperModel
        import imageio_ffmpeg
        import numpy as np
        decoded = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(args.source),
             "-vn", "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1"],
            capture_output=True, check=True,
        )
        audio = np.frombuffer(decoded.stdout, dtype=np.float32)
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, language="zh", vad_filter=True,
                                           word_timestamps=True, beam_size=5)
        rows = []
        for i, s in enumerate(segments):
            row = {"id": i, "start": s.start, "end": s.end, "text": s.text,
                   "words": [{"start": w.start, "end": w.end, "word": w.word,
                              "probability": w.probability} for w in (s.words or [])]}
            rows.append(row)
            print(f"{s.start:.2f}-{s.end:.2f} {s.text}", flush=True)
            write_json(args.output / "transcript.partial.json", rows)
        write_json(args.output / "transcript.json", {"language": info.language, "segments": rows})
    else:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if args.action == "frames":
            subprocess.run([ffmpeg, "-y", "-i", str(args.source), "-vf", "fps=1/30,scale=270:-2",
                            str(args.output / "frame_%03d.jpg")], check=True, capture_output=True)
            return
        if not args.selection:
            parser.error("render requires --selection")
        duration = probe(args.source)["duration"]
        selections = json.loads(args.selection.read_text(encoding="utf-8"))
        results = []
        for index, clip in enumerate(selections["clips"], 1):
            start, end = float(clip["start"]), float(clip["end"])
            if not (0 <= start < end <= duration and 10 <= end-start <= 30):
                raise ValueError(f"Invalid clip boundaries: {start}, {end}")
            if not clip.get("reason") or not clip.get("text"):
                raise ValueError("Every clip needs transcript and semantic selection reason")
            target = args.output / f"clip_{index:02d}.mp4"
            subprocess.run([ffmpeg, "-y", "-ss", str(start), "-i", str(args.source),
                            "-t", str(end-start), "-map", "0:v:0", "-map", "0:a:0",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac",
                            "-b:a", "192k", "-movflags", "+faststart", str(target)],
                           check=True, capture_output=True)
            result = probe(target)
            if abs(result["duration"] - (end-start)) > .3:
                raise ValueError(f"Unexpected output duration: {target}")
            results.append({**clip, "file": target.name, "verified_media": result})
        write_json(args.output / "rendered_clips.json", results)
        print(f"Rendered and verified {len(results)} clips")


if __name__ == "__main__":
    main()
