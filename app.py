import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sarvamai import SarvamAI
from matcher import compare_segments, comparison_metrics, extract_reference, extract_segments, choose_mode

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MAX_AUDIO_MB = int(os.getenv("MAX_AUDIO_MB", "20"))
MAX_AUDIO_BYTES = MAX_AUDIO_MB * 1024 * 1024
MODEL = os.getenv("SARVAM_MODEL", "saaras:v4")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "900"))
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3"}

app = FastAPI(title="Transcript Match", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def find_output_json(output_dir: Path) -> Path:
    json_files = sorted(output_dir.rglob("*.json"))
    if not json_files:
        raise RuntimeError("Transcription completed, but no JSON output file was returned.")
    return json_files[0]


def transcribe_with_batch(audio_path: Path, reference_text: str) -> Dict[str, Any]:
    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("API key is missing. Add your key to the .env file and restart the app.")

    mode = choose_mode(reference_text)
    client = SarvamAI(api_subscription_key=api_key)
    job = client.speech_to_text_job.create_job(
        model=MODEL,
        mode=mode,
        with_diarization=True,
        with_timestamps=True,
    )
    job.upload_files(file_paths=[str(audio_path)])
    job.start()
    job.wait_until_complete(poll_interval=POLL_INTERVAL_SECONDS, timeout=JOB_TIMEOUT_SECONDS)

    file_results = job.get_file_results()
    successful = file_results.get("successful", []) if isinstance(file_results, dict) else []
    failed = file_results.get("failed", []) if isinstance(file_results, dict) else []
    if not successful and failed:
        message = failed[0].get("error_message") if isinstance(failed[0], dict) else str(failed[0])
        raise RuntimeError(f"Audio transcription failed: {message or 'unknown processing error'}")

    with tempfile.TemporaryDirectory(prefix="transcript_match_output_") as output_temp:
        output_dir = Path(output_temp)
        job.download_outputs(output_dir=str(output_dir))
        output_file = find_output_json(output_dir)
        with output_file.open("r", encoding="utf-8") as handle:
            result = json.load(handle)

    if not isinstance(result, dict):
        raise RuntimeError("Unexpected transcription response format.")
    result["_comparison_mode"] = mode
    return result


@app.post("/api/compare")
def compare_transcript(
    audio: UploadFile = File(...),
    transcript: UploadFile = File(...),
) -> Dict[str, Any]:
    audio_name = audio.filename or "audio"
    transcript_name = transcript.filename or "transcript.json"
    audio_ext = Path(audio_name).suffix.lower()

    if audio_ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Audio must be a .wav or .mp3 file.")
    if Path(transcript_name).suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Transcript must be a .json file.")

    audio_bytes = audio.file.read(MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The audio file is empty.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio file must be {MAX_AUDIO_MB} MB or smaller.")

    transcript_bytes = transcript.file.read(5 * 1024 * 1024 + 1)
    if len(transcript_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Transcript JSON must be 5 MB or smaller.")

    try:
        reference_payload = json.loads(transcript_bytes.decode("utf-8-sig"))
        reference_text, reference_segments = extract_reference(reference_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON transcript: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temp_dir = Path(tempfile.mkdtemp(prefix="transcript_match_"))
    audio_path = temp_dir / f"input{audio_ext}"

    try:
        audio_path.write_bytes(audio_bytes)
        stt_result = transcribe_with_batch(audio_path, reference_text)

        model_text = str(stt_result.get("transcript") or "").strip()
        model_segments = extract_segments(stt_result)
        if not model_text and model_segments:
            model_text = " ".join(segment["text"] for segment in model_segments)
        if not model_text:
            raise RuntimeError("The speech service returned an empty transcription.")

        metrics = comparison_metrics(reference_text, model_text)
        segments = compare_segments(reference_segments, model_segments) if reference_segments else []

        return {
            "ok": True,
            "metrics": metrics,
            "referenceTranscript": reference_text,
            "modelTranscript": model_text,
            "languageCode": stt_result.get("language_code"),
            "comparisonMode": stt_result.get("_comparison_mode"),
            "segments": segments,
            "files": {
                "audio": audio_name,
                "transcript": transcript_name,
                "audioSizeBytes": len(audio_bytes),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).strip() or "Something went wrong while processing the audio."
        raise HTTPException(status_code=500, detail=message) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
