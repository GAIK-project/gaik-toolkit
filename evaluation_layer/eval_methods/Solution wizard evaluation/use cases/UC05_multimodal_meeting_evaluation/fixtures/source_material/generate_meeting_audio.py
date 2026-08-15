#!/usr/bin/env python3
"""Regenerate the synthetic UC05 meeting audio and evaluator reference files."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_AUDIO = ROOT / "input" / "project_nimbus_meeting.wav"
REFERENCE_TRANSCRIPT = ROOT / "reference_transcript.json"
EXPECTED_OUTPUT = ROOT / "expected_meeting_record.json"

SEGMENTS = [
    ("S01", "Elena Markovic", "slt", "Good morning. My name is Elena Markovic. I am the Project Manager for Project Nimbus. I chair this readiness review, coordinate the final go or no go recommendation, and review the meeting record before approval. I am opening the Project Nimbus pilot readiness review on September seventeenth, twenty twenty six at nine o'clock."),
    ("S02", "Liam Chen", "awb", "My name is Liam Chen. I am the Technical Lead for Project Nimbus. I am responsible for the pilot sandbox, technical readiness, and coordination of the single sign on question with the architecture board."),
    ("S03", "Sofia Niemi", "rms", "My name is Sofia Niemi. I am the Data Protection Specialist for Project Nimbus. I advise the team on permitted pilot data, privacy controls, and the data protection impact assessment."),
    ("S04", "Arjun Patel", "kal", "My name is Arjun Patel. I am the Project Coordinator for Project Nimbus. I organize the meeting, coordinate training and follow up activities, and prepare the meeting record for the Project Manager's review."),
    ("S05", "Mia Roberts", "kal16", "My name is Mia Roberts. I am the Procurement Specialist supporting Project Nimbus. I coordinate supplier quotations and report the procurement and budget position to the project team."),
    ("S06", "Arjun Patel", "kal", "Thank you. Attendance is complete and all five expected participants are present. We can proceed with the readiness review."),
    ("S07", "Elena Markovic", "slt", "Today we need to confirm the pilot scope, data protection conditions, procurement actions, training, and open technical risks. The agenda proposes October fifteenth as the launch date, but that date was drafted before the latest readiness review. We need an explicit decision today rather than copying the proposal into the meeting record."),
    ("S08", "Liam Chen", "awb", "My recommendation is to limit the pilot to the Helsinki customer service team, with thirty users, for two weeks. The sandbox will not be ready for the proposed October fifteenth date. A start on October twentieth is realistic."),
    ("S09", "Elena Markovic", "slt", "Decision: the pilot will cover only the Helsinki customer service team, with thirty users, for a two week period starting October twentieth. This replaces the proposed October fifteenth date in the agenda."),
    ("S10", "Sofia Niemi", "rms", "For data protection, the pilot should use synthetic or anonymized records only. Production customer data must not enter the pilot environment. I can complete the data protection impact assessment by September twenty ninth."),
    ("S11", "Elena Markovic", "slt", "Decision: no production customer data will be used in the pilot. Sofia owns the data protection impact assessment and the due date is September twenty ninth."),
    ("S12", "Mia Roberts", "kal16", "We expect three supplier quotations. I can compare them by September twenty fourth. The agenda mentions an eighteen thousand euro ceiling, but finance has not confirmed it. We are not approving a budget in this meeting."),
    ("S13", "Elena Markovic", "slt", "Action: Mia will compare the three supplier quotations by September twenty fourth. The final budget approval and confirmed ceiling remain unresolved until finance responds."),
    ("S14", "Liam Chen", "awb", "The single sign on approach is still with the architecture board. The board meets on September twenty second. There is no single sign on decision today, and no project team owner should be inferred for that decision."),
    ("S15", "Elena Markovic", "slt", "Action: Arjun will schedule the pilot training session by October third. The training itself should take place before the October twentieth pilot start."),
    ("S16", "Elena Markovic", "slt", "Action: Liam will configure and test the sandbox by September twenty fifth, using synthetic test data only."),
    ("S17", "Elena Markovic", "slt", "We also need a short support frequently asked questions document before training. Someone from support should draft it, but no owner or exact due date has been agreed. Record both values as unknown rather than assigning them."),
    ("S18", "Elena Markovic", "slt", "Action: I will send the consolidated go or no go summary to the steering group by October sixth, after the data protection, procurement, training, and sandbox updates are available."),
    ("S19", "Elena Markovic", "slt", "To recap, we approved the limited thirty user Helsinki pilot beginning October twentieth and the use of synthetic or anonymized data only. The budget and single sign on approach remain open. The named actions and dates should be recorded exactly. The meeting closes at nine eighteen."),
]


# Each participant has an independent base voice and acoustic profile. Pitch,
# formant, spectral balance, and cadence are varied strongly enough to support
# diarization while keeping the dialogue intelligible and natural.
VOICE_FILTERS = {
    "Elena Markovic": "rubberband=pitch=1.05:formant=preserved,highpass=f=120,equalizer=f=2800:t=q:w=1:g=2,atempo=1.00",
    "Liam Chen": "rubberband=pitch=0.78:formant=shifted,lowpass=f=3800,equalizer=f=180:t=q:w=1:g=5,atempo=1.03",
    "Sofia Niemi": "rubberband=pitch=1.30:formant=shifted,highpass=f=170,equalizer=f=3400:t=q:w=1:g=4,atempo=1.08",
    "Arjun Patel": "rubberband=pitch=0.90:formant=shifted,lowpass=f=4700,equalizer=f=900:t=q:w=1:g=-3,atempo=1.12",
    "Mia Roberts": "rubberband=pitch=1.52:formant=shifted,highpass=f=220,equalizer=f=4200:t=q:w=1:g=5,atempo=1.17",
}


def run(command):
    subprocess.run(command, check=True, text=True, capture_output=True)


def duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], check=True, text=True, capture_output=True)
    return float(result.stdout.strip())


def timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def citation(transcript, segment_id):
    """One audio citation as a single pipe-delimited string."""
    item = next(row for row in transcript if row["segment_id"] == segment_id)
    return "|".join([OUTPUT_AUDIO.name, item["start_timestamp"], item["end_timestamp"]])


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg and ffprobe are required to regenerate the fixture.")
    OUTPUT_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="uc05-audio-") as temp_name:
        temp = Path(temp_name)
        silence = temp / "silence.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.55", "-c:a", "pcm_s16le", str(silence)])
        concat_lines = []
        transcript = []
        cursor = 0.0
        for index, (segment_id, speaker, voice, text) in enumerate(SEGMENTS, start=1):
            text_path = temp / f"{index:02d}.txt"
            text_path.write_text(text, encoding="utf-8")
            raw_path = temp / f"{index:02d}_raw.wav"
            audio_path = temp / f"{index:02d}.wav"
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"flite=textfile={text_path}:voice={voice}", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(raw_path)])
            target_duration = duration(raw_path)
            audio_filter = VOICE_FILTERS[speaker] + f",apad=pad_dur={target_duration:.6f},atrim=duration={target_duration:.6f},loudnorm=I=-20:LRA=7:TP=-2"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_path), "-af", audio_filter, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio_path)])
            seconds = duration(audio_path)
            start = cursor
            end = cursor + seconds
            transcript.append({"segment_id": segment_id, "speaker": speaker, "start_timestamp": timestamp(start), "end_timestamp": timestamp(end), "text": text})
            concat_lines.append(f"file '{audio_path.as_posix()}'")
            if index != len(SEGMENTS):
                concat_lines.append(f"file '{silence.as_posix()}'")
                cursor = end + duration(silence)
            else:
                cursor = end
        concat_file = temp / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(OUTPUT_AUDIO)])

    reference = {
        "schema_version": "1.0.0",
        "scenario_id": "UC05",
        "meeting_id": "NIMBUS-PRR-2026-09-17",
        "audio_file": OUTPUT_AUDIO.name,
        "duration_seconds": round(duration(OUTPUT_AUDIO), 3),
        "note": "Evaluator-only reference. Do not provide this transcript to the wizard.",
        "segments": transcript,
    }
    REFERENCE_TRANSCRIPT.write_text(json.dumps(reference, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    expected = {
        "schema_version": "1.0.0",
        "scenario_id": "UC05",
        "meeting_id": "NIMBUS-PRR-2026-09-17",
        "title": "Project Nimbus Pilot Readiness Review",
        "meeting_date": "2026-09-17",
        "start_time": "09:00",
        "end_time": "09:18",
        "participants": [
            {"name": "Elena Markovic", "role": "Project Manager"},
            {"name": "Liam Chen", "role": "Technical Lead"},
            {"name": "Sofia Niemi", "role": "Data Protection Specialist"},
            {"name": "Arjun Patel", "role": "Project Coordinator"},
            {"name": "Mia Roberts", "role": "Procurement Specialist"},
        ],
        "topics": [
            {"title": "Pilot scope and timing", "discussion_summary": "The team replaced the proposed 15 October date with a limited 30-user Helsinki customer-service pilot starting 20 October for two weeks."},
            {"title": "Data protection", "discussion_summary": "The pilot will use synthetic or anonymized data only; a DPIA is required."},
            {"title": "Procurement and budget", "discussion_summary": "Three quotations will be compared; budget approval remains pending."},
            {"title": "Training and readiness", "discussion_summary": "Training, sandbox preparation, FAQ preparation, and a go/no-go summary are required before the pilot."},
            {"title": "Open technical risks", "discussion_summary": "The SSO approach remains with the architecture board."},
        ],
        "decisions": [
            {"decision_id": "D01", "statement": "Run a two-week pilot for 30 users in the Helsinki customer service team starting 2026-10-20.", "citations": [citation(transcript, "S09")]},
            {"decision_id": "D02", "statement": "Use only synthetic or anonymized data; do not use production customer data.", "citations": [citation(transcript, "S11")]},
        ],
        "action_items": [
            {"action_id": "A01", "description": "Complete the data protection impact assessment.", "owner": "Sofia Niemi", "due_date": "2026-09-29", "uncertainty_reason": None, "citations": [citation(transcript, "S11")]},
            {"action_id": "A02", "description": "Compare the three supplier quotations.", "owner": "Mia Roberts", "due_date": "2026-09-24", "uncertainty_reason": None, "citations": [citation(transcript, "S13")]},
            {"action_id": "A03", "description": "Schedule the pilot training session.", "owner": "Arjun Patel", "due_date": "2026-10-03", "uncertainty_reason": None, "citations": [citation(transcript, "S15")]},
            {"action_id": "A04", "description": "Configure and test the sandbox using synthetic data.", "owner": "Liam Chen", "due_date": "2026-09-25", "uncertainty_reason": None, "citations": [citation(transcript, "S16")]},
            {"action_id": "A05", "description": "Draft a short support FAQ before training.", "owner": None, "due_date": None, "uncertainty_reason": "No owner or exact due date was agreed.", "citations": [citation(transcript, "S17")]},
            {"action_id": "A06", "description": "Send the consolidated go/no-go summary to the steering group.", "owner": "Elena Markovic", "due_date": "2026-10-06", "uncertainty_reason": None, "citations": [citation(transcript, "S18")]},
        ],
        "unresolved_issues": [
            {"description": "Final pilot budget approval and the confirmed budget ceiling are pending finance confirmation.", "citations": [citation(transcript, "S13")]},
            {"description": "The SSO approach remains undecided pending the architecture board meeting on 2026-09-22.", "citations": [citation(transcript, "S14")]},
        ],
        "conflicts": [
            {"description": "The agenda proposed a 2026-10-15 launch, but the meeting explicitly decided on 2026-10-20.", "citations": ["project_nimbus_agenda.pdf|2", citation(transcript, "S09")]}
        ],
        "review_status": "pending_review",
        "must_not_assert": [
            "The 18,000 euro budget ceiling was approved.",
            "An SSO approach was selected.",
            "The support FAQ has a named owner or exact due date.",
            "The pilot starts on 2026-10-15."
        ]
    }
    EXPECTED_OUTPUT.write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created {OUTPUT_AUDIO} ({reference['duration_seconds']} seconds)")
    print(f"Created {REFERENCE_TRANSCRIPT}")
    print(f"Created {EXPECTED_OUTPUT}")


if __name__ == "__main__":
    main()
