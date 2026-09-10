# Transcript Match

A small local web app for comparing an audio transcription against a reference JSON transcript.

The browser UI never displays or receives your speech API key. The key is read only by the Python backend from `.env`.

## What it does

- Upload one `.wav` or `.mp3` file, up to **20 MB**.
- Upload one reference `.json` transcript.
- Sends the audio to the configured speech-to-text API using its **batch** workflow.
- Automatically compares the generated text with the uploaded reference.
- Shows:
  - Overall match percentage
  - Word accuracy
  - Character similarity
  - Word error rate (WER)
  - Reference/model word counts
  - Reference and generated transcripts side by side
  - Segment-by-segment scores when timestamps are available

## 1. Add your API key

Open the included `.env` file and paste the key after `SARVAM_API_KEY=`:

```env
SARVAM_API_KEY=your_key_here
```

You do not need to change anything else for the normal setup.

## 2. Run locally

### Windows - easiest

Double-click `run.bat`, or open a terminal inside this folder and run:

```bat
run.bat
```

### Linux / macOS - easiest

```bash
./run.sh
```

### Manual setup

```bash
python -m venv .venv
```

Activate it:

**Windows**

```bat
.venv\Scripts\activate
```

**Linux / macOS**

```bash
source .venv/bin/activate
```

Install dependencies and start:

```bash
python -m pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Reference JSON format

Your timestamped format works directly:

```json
[
  {
    "end_time": 5.78,
    "speaker_type": "owner",
    "start_time": 2.34,
    "transcript": "Hai, main Traya se Deepak baat kar raha hun."
  },
  {
    "end_time": 6.97,
    "speaker_type": "client",
    "start_time": 6.09,
    "transcript": "Haan, boliye."
  }
]
```

A `sample-transcript.json` file is included.

The parser also understands common structures such as:

```json
{"transcript": "full transcript here"}
```

and objects containing `segments`, `entries`, `utterances`, or `items` arrays where each item has a `transcript` or `text` field.

## How the score is calculated

The app normalizes capitalization, punctuation, Unicode, and repeated spaces before comparison.

- **Overall match**: normalized word-level edit similarity between the two complete transcripts.
- **Word accuracy**: reference words that remain correct after substitutions/deletions are counted.
- **WER**: `(substitutions + deletions + insertions) / reference words`. Lower is better.
- **Character similarity**: character-level sequence similarity after normalization.

The overall match is intentionally symmetric so a transcript with many extra words is penalized as well as one that misses words.

## Romanized Hindi / Hinglish

`SARVAM_MODE=auto` is enabled by default. If the reference transcript is written mainly in Latin/Roman characters, the backend requests transliterated output. If the reference uses an Indic script such as Devanagari, it requests normal transcription. This avoids comparing Romanized Hindi against Devanagari and getting an artificially low score.

You can force a mode in `.env` if needed:

```env
SARVAM_MODE=transcribe
```

or

```env
SARVAM_MODE=translit
```

## Project structure

```text
transcript-match-app/
├── app.py
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── sample-transcript.json
├── run.bat
├── run.sh
└── static/
    ├── index.html
    ├── styles.css
    └── app.js
```

## Notes

- Only WAV and MP3 are enabled in the UI/backend because those are the formats requested for this app.
- The batch speech endpoint is used so recordings are not restricted to the short real-time endpoint's duration limit.
- The temporary uploaded audio and downloaded transcription output are deleted after each request.
- Do not commit `.env` to Git. It is already listed in `.gitignore`.
