"""Walk a set of use cases through a running Solution Wizard v2 API and check the result.

    python run_usecases.py                      # every case in usecases.json, one after another
    python run_usecases.py --only policy-rag    # one case (comma-separated ids)
    python run_usecases.py --stop-at-gate 1     # quick pass: stop once Gate 1 is approved
    python run_usecases.py --run                # also start the PoC test run (needs the sandbox)
    python run_usecases.py --pace quick         # start as the web app's Quick choice does
    python run_usecases.py --list
    python run_usecases.py --from-evaluation <folder>   # write a cases file from evaluation cases

Each case plays the user: it describes the use case, answers a question with the
case's scripted answer for it when it has one and anything else with
"make sensible assumptions and go on", approves each gate, and at set points
does what a tester would try by hand (reload during a reply, reopen a gate,
ask for a change after approval, write in another language, end the session).
It talks to wizard_api only; the web app is not involved.

Standard library only. Needs a running wizard_api (see WIZARD-DEV.md).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE_AT = {4: 1, 9: 2, 11: 3, 13: 4}
GO_ON = {
    "fi": "Hyvä. Tee järkevät oletukset avoimiin kohtiin, kirjaa ne ja jatka seuraavaan vaiheeseen ilman lisäkysymyksiä.",
    "en": "Good. Make sensible assumptions for anything open, record them, and go on to the next step without further questions.",
}
WAKE = {
    "fi": "Gate {n} hyväksytty paneelista, jatka.",
    "en": "Gate {n} approved in the panel, continue.",
}
OTHER_LANGUAGE = {
    "fi": "From now on, could you answer me in English?",
    "en": "Voisitko vastata tästä eteenpäin suomeksi?",
}
# The line the web app's pace choice puts ahead of the user's first message.
PACE = {
    "quick": {
        "fi": "Tahti: nopea. Kysy vain se, mitä et voi kohtuudella olettaa, mieluiten yhdellä "
        "kierroksella; ehdota muuhun oletukset ja listaa ne oletuksina.",
        "en": "Pace: quick. Ask only what you cannot reasonably assume, in one round if you can; "
        "propose defaults for the rest and list them as assumptions.",
    },
    "thorough": {
        "fi": "Tahti: perusteellinen. Kysy se, mitä tarvitset yksityiskohtien saamiseksi oikein.",
        "en": "Pace: thorough. Ask what you need to get the details right.",
    },
}
ALSO_NOTE = {"fi": "Huomioi myös:", "en": "Also note:"}
RUN_FAILED = {
    "fi": "Testiajo epäonnistui. Lue ajon loki, korjaa PoC-paketti ja kerro, kun se on valmis uuteen ajoon.",
    "en": "The test run failed. Read the run's log, fix the PoC package and tell me when it is ready for a new run.",
}
MAX_RUNS = 3  # test runs a case: the first, and two more after the wizard has mended the package
MAX_MESSAGE = 15_000  # characters in one chat message; the API takes 20 000 by default
WORD = re.compile(r"[^\W_]+")
# Words that say nothing about a question's topic.
STOP = frozenset(
    """
    a about all also an and any are as at be been both but by can could did do does each else
    for from had has have how if in into is it its may more must no not of on only or other
    our out over per should so some such than that the their them then there these they this
    those to under up use used uses using was we were what when where which who whom whose
    why will with would you your
    ja tai on ei että kun jos mikä mitä miten kuka missä onko voiko myös sekä
    """.split()
)
LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|(\d{1,2})[.)])\s+(.*)$")
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
NOT_ASKING = (
    re.compile(r"(`+).*?\1(?!`)"),  # inline code
    re.compile(r"\]\([^)]*\)"),  # a link's address
    re.compile(r"(?:https?://|www\.)[^\s<>]*[^\s<>?.,!;:'\")\]]", re.I),  # a bare address
)
LOST_STREAM = (OSError, http.client.HTTPException)
QUIET_FRAMES = {"delta", "narration_end", "activity", "heartbeat", "done"}
PRINT_LOCK = threading.Lock()


class Api:
    def __init__(self, base: str, user: str, token: str | None) -> None:
        self.base = base.rstrip("/")
        self.user = user
        self.token = token

    def call(
        self,
        method: str,
        path: str,
        body=None,
        stream: bool = False,
        raw: tuple[bytes, str] | None = None,
    ):
        """JSON in, JSON out. An HTTP error comes back as {"_error": code, "_body": text}."""
        headers = {"X-Wizard-User-Id": self.user}
        if self.token:
            headers["X-Wizard-Service-Token"] = self.token
        data = None
        if raw is not None:
            data, headers["Content-Type"] = raw
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        # A read is safe to repeat, and a port-forward drops a connection now and then.
        tries = 4 if method == "GET" and not stream else 1
        lost = ""
        for attempt in range(tries):
            if attempt:
                time.sleep(3 * attempt)
            try:
                # A chat reply or a run streams for many minutes; any other call answers at once.
                response = urllib.request.urlopen(request, timeout=3600 if stream else 120)
                if stream:
                    if response.status == 204:
                        return {"_error": 204, "_body": "nothing running"}
                    return response
                text = response.read().decode()
                return json.loads(text) if text else {}
            except urllib.error.HTTPError as err:
                return {"_error": err.code, "_body": err.read().decode(errors="replace")[:600]}
            except LOST_STREAM as err:
                lost = str(err)[:300]
        return {"_error": 0, "_body": lost}


def read_reply(response) -> tuple[str, int, list[dict], set[str]]:
    """Read one chat stream to its end: the reply, tool calls, error frames, frame kinds seen."""
    text: list[str] = []
    tools, problems, kinds = 0, [], set()
    for raw in response:
        line = raw.decode(errors="replace").strip()
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        kinds.update(event.keys())
        if "delta" in event:
            text.append(event["delta"])
        elif event.get("narration_end"):
            text.clear()
        elif "activity" in event:
            tools += 1
        elif event.get("error"):
            problems.append(event)
    return "".join(text), tools, problems, kinds


def _asks(text: str) -> bool:
    """A "?" in the text's own words, not in inline code or a web address."""
    for pattern in NOT_ASKING:
        text = pattern.sub(" ", text)
    return "?" in text


def questions_in(markdown: str) -> list[str]:
    """The questions a reply asks, by the rule of the web app's answer form
    (``questionsIn`` in solution_wizard_v2/lib/chat-questions.ts).

    A question is a list item (bulleted or numbered, with its wrapped lines) that has a
    "?" outside inline code and web addresses; nothing in a fenced code block counts.
    A bullet indented under an item is one of its options unless it asks something
    itself, and then it is a question of its own; so is a bullet at the margin right
    after a numbered question. The lines after an item that ends in a colon are what
    it lists, not more of its text. A reply with no such item still asks one question
    when its last line of prose ends in "?" (the runner's rule, not the form's).
    """
    items: list[dict] = []
    prose: list[str] = []
    owner: dict | None = None  # the item the bullets below belong to
    open_: dict | None = None  # the item or option a wrapped line continues
    fence = ""
    for line in markdown.splitlines():
        mark = FENCE.match(line)
        if fence:
            if mark and mark[2][0] == fence[0] and len(mark[2]) >= len(fence):
                fence = ""
            continue
        if mark:
            # An indented block belongs to the item above it; any other ends it.
            if len(mark[1]) < 2:
                owner = open_ = None
            fence = mark[2]
            continue
        item = LIST_ITEM.match(line)
        indent = len(item[1]) if item else 0
        under = bool(item) and owner is not None and indent >= owner["indent"] + 2
        after = (
            bool(item)
            and not under
            and owner is not None
            and item[2] is None
            and owner["number"] is not None
            and indent <= owner["indent"] + 1
            and _asks(owner["text"])
        )
        indented = re.match(r"\s{2,}\S", line) is not None
        if item and (under or after) and not _asks(item[3]):
            open_ = {"text": item[3]}  # an option of the item above: never a question
        elif item and (under or indent <= 3):
            new = {"text": item[3], "indent": indent, "number": None if under else item[2]}
            items.append(new)
            if not under:  # a question under a question: the bullets after it are its siblings
                owner = new
            open_ = new
        elif owner is not None and indented and (open_ is None or _lists_lines(open_, owner)):
            # A paragraph under the item after a blank line, or a line of what an item
            # that ends in a colon lists: it stays under the item, outside its text.
            open_ = {"text": line.strip(), "listed": open_ is not None}
        elif open_ is not None and indented:
            open_["text"] += " " + line.strip()  # a wrapped line of the same item
        elif not line.strip():
            open_ = None  # a blank line ends the item's text; bullets after it may be its own
        else:
            owner = open_ = None
            prose.append(line.strip())
    asked = [i["text"] for i in items if _asks(i["text"])]
    if not asked and prose and prose[-1].rstrip("*_ ").endswith("?") and _asks(prose[-1]):
        asked = [prose[-1]]
    return asked


def _lists_lines(open_: dict, owner: dict) -> bool:
    """Whether an indented line is a line of its own under ``owner``, not its wrapped text."""
    if open_ is owner:
        return re.search(r"[:：]\s*(\*\*|__|\*|_)?$", owner["text"].strip()) is not None
    return bool(open_.get("listed"))


def words_of(text: str) -> list[str]:
    """The words of a text that can name a topic: lower case, three letters or more, once each."""
    seen: dict[str, None] = {}
    for word in WORD.findall(text.lower()):
        if len(word) >= 3 and word not in STOP:
            seen.setdefault(word)
    return list(seen)


def answer_keywords(answer: dict) -> list[str]:
    """A scripted answer's keywords: its own 'keywords', or else the words of its 'topic'."""
    given = answer.get("keywords")
    return words_of(" ".join(given) if given else answer.get("topic", ""))


def answer_label(answer: dict, index: int) -> str:
    return str(answer.get("id") or answer.get("topic") or f"answer {index + 1}")


def _hit(keyword: str, words: list[str]) -> bool:
    """A keyword hits a word when they are the same, or one begins the other (four letters up)."""
    return any(
        word == keyword
        or (
            min(len(word), len(keyword)) >= 4
            and (word.startswith(keyword) or keyword.startswith(word))
        )
        for word in words
    )


def match_answers(
    questions: list[str], answers: list[dict], sent: set[int] | frozenset = frozenset()
) -> list[tuple[int | None, list[str]]]:
    """For each question, the scripted answer to give: its index and the keywords that chose it.

    A question takes the answer whose keywords hit most of its words. A keyword that
    several answers share counts for less (one divided by the number of answers that have
    it), so the word that tells two answers apart decides. A tie goes to the answer listed
    first, and a question no keyword hits gets (None, []). An answer goes to one question
    a reply, and one whose index is in 'sent' is left out unless it is 'repeatable'.
    """
    keywords = [answer_keywords(a) for a in answers]
    shared: dict[str, int] = {}
    for own in keywords:
        for keyword in own:
            shared[keyword] = shared.get(keyword, 0) + 1
    taken: set[int] = set()
    picks: list[tuple[int | None, list[str]]] = []
    for question in questions:
        text = question
        for pattern in NOT_ASKING:
            text = pattern.sub(" ", text)
        words = words_of(text)
        best: tuple[float, int | None, list[str]] = (0.0, None, [])
        for index, answer in enumerate(answers):
            if index in taken or (index in sent and not answer.get("repeatable")):
                continue
            why = [k for k in keywords[index] if _hit(k, words)]
            score = sum(1 / shared[k] for k in why)
            if score > best[0] + 1e-9:
                best = (score, index, why)
        if best[1] is not None:
            taken.add(best[1])
        picks.append((best[1], best[2]))
    return picks


def run_due(
    runs: int,
    last_ok: bool,
    version_then: str | None,
    version_now: str | None,
    replied_since: bool,
    limit: int = MAX_RUNS,
) -> bool:
    """Whether to start a test run of the package now.

    The first run is always due. A later one is due while fewer than 'limit' have been
    started and the package is not the one the last run ran: by what the API reports
    for the package (``package_id``), or, where it reports nothing, when the last run
    failed and the wizard has replied since.
    """
    if runs == 0:
        return True
    if runs >= limit:
        return False
    if version_then and version_now:
        return version_now != version_then
    return not last_ok and replied_since


def fixture_inputs(fixtures: Path) -> list[Path]:
    """The files of an evaluation case's fixtures/ that a PoC run reads.

    Everything under poc_input/ or input/ when the case has such a folder, with the
    poc_input_bundle.json beside it that names those files; otherwise the files of
    fixtures/ itself that are not .json, .txt or .md (the expected results, the manifest
    and the facts sit there beside the input).
    """
    for name in ("poc_input", "input"):
        if (fixtures / name).is_dir():
            bundle = fixtures / "poc_input_bundle.json"
            found = sorted(p for p in (fixtures / name).rglob("*") if p.is_file())
            return found + ([bundle] if bundle.is_file() else [])
    if not fixtures.is_dir():
        return []
    return sorted(
        p
        for p in fixtures.iterdir()
        if p.is_file() and p.suffix.lower() not in (".json", ".txt", ".md")
    )


def answers_from_sheet(sheet: Path) -> tuple[list[dict], list[str]]:
    """A case's scripted answers, and a note for each part of the sheet left out.

    The sheet is an object with its list under ``answers`` or ``scripted_answers``, or the
    list itself. A sheet that cannot be read, and an entry that is not an object or has
    no answer text, is left out with a note: one odd sheet does not stop the others.
    """
    try:
        data = json.loads(sheet.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [], [f"{sheet.name} is not read: {type(error).__name__}"]
    entries = data
    if isinstance(data, dict):
        entries = data.get("answers") or data.get("scripted_answers") or []
    if not isinstance(entries, list):
        return [], [f"{sheet.name} has no list of answers"]
    answers, notes = [], []
    for at, entry in enumerate(entries, 1):
        text = entry.get("answer") if isinstance(entry, dict) else None
        if not isinstance(text, str) or not text.strip():
            notes.append(f"{sheet.name}: entry {at} has no answer and is left out")
            continue
        topic = str(entry.get("topic") or "")
        answers.append(
            {
                "id": entry.get("id") or entry.get("answer_id") or topic or f"answer-{at}",
                "topic": topic,
                "keywords": words_of(f"{topic} {entry.get('trigger') or ''}"),
                "text": text,
            }
        )
    return answers, notes


def cases_from_evaluation(folder: Path, notes: list[str] | None = None) -> list[dict]:
    """Cases for this runner from a folder of evaluation cases.

    Each subfolder with an initial_prompt.txt is a case: the prompt is the description,
    the fixtures a run reads are the inputs (as absolute paths), and each entry of
    scripted_answers.json is an answer whose keywords are the words of its topic and its
    trigger. What a sheet holds that is not an answer is left out and named in ``notes``.
    """
    cases = []
    for uc in sorted(p for p in folder.iterdir() if (p / "initial_prompt.txt").is_file()):
        name = re.sub(r"_evaluation$", "", uc.name)
        answers = []
        sheet = uc / "scripted_answers.json"
        if sheet.is_file():
            answers, left_out = answers_from_sheet(sheet)
            if notes is not None:
                notes.extend(f"{name}: {note}" for note in left_out)
        cases.append(
            {
                "id": name.lower().replace("_", "-"),
                "title": name.replace("_", " "),
                "locale": "en",
                "description": (uc / "initial_prompt.txt").read_text(encoding="utf-8").strip(),
                "scenarios": [],
                "inputs": [str(p.resolve()) for p in fixture_inputs(uc / "fixtures")],
                "answers": answers,
            }
        )
    return cases


def repository_of(path: Path) -> Path | None:
    """The git checkout a path is in, if any."""
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return folder
    return None


def content_digest(detail: dict) -> str:
    """What the gates approve, hashed over the parts the API itself compares."""
    parts = ("id", "type", "component", "parameters", "depends_on")
    steps = [{k: st.get(k) for k in parts} for st in detail.get("blueprint", {}).get("steps") or []]
    approved = {"steps": steps, "output": detail.get("target_output_spec")}
    return hashlib.sha256(
        json.dumps(approved, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def package_id(files: dict) -> str | None:
    """What a test run is tied to, from ``GET /sessions/{id}/poc/files``, or None.

    Gate 3 takes a successful run only of the package as it is now, compared by
    ``package_digest``: the code, the settings and the schema (``version``) and the
    prompts under ``prompts/`` too. An API that reports no digest gives its version.
    """
    if not isinstance(files, dict) or not files.get("generated"):
        return None
    return files.get("package_digest") or files.get("version")


def is_turn_limit(event: dict) -> bool:
    """The frame of a reply stopped at the most steps one message may take.

    It carries ``error: true`` for the chat, but the API counts it as the agent
    working as configured, not as a failed turn; the next message lets it go on.
    """
    return event.get("limit") == "turns"


def quick_pace_result(rounds: int, lost_replies: int) -> str:
    """The quick pace's verdict: one round of questions at most. A lost reply may
    have asked a round that was not counted, so it leaves the check open (info)."""
    if rounds > 1:
        return "fail"
    return "info" if lost_replies else "pass"


class Walk:
    def __init__(self, api: Api, case: dict, out: Path, opts: argparse.Namespace) -> None:
        self.api, self.case, self.opts = api, case, opts
        self.id = case["id"]
        self.locale = case.get("locale", "fi")
        self.pace = opts.pace or case.get("pace") or ""
        self.rounds = self.questions = self.lost_replies = 0
        self.unread_reply: str | None = None  # a reply not yet looked at for questions
        self.gate1_approved = False
        self.todo = set(case.get("scenarios", []))
        self.answers: list[dict] = case.get("answers") or []
        self.sent: set[int] = set()  # indexes of the scripted answers already given
        self.answer_log: list[tuple[str, str]] = []  # (answer, where it was sent)
        # The scripted answers in the message about to be said: (index, label, where).
        # They count as given only once the API has taken the message.
        self.pending: list[tuple[int, str, str]] = []
        self.runs: list[dict] = []  # the test runs started, in order
        self.no_sandbox = False
        self.checks: list[dict] = []
        self.stream_errors: list[dict] = []
        self.turn_limits = 0  # replies stopped at the most steps one message may take
        self.last_kinds: set[str] = set()
        self.sid = ""
        self.replies = 0
        self.refused = ""
        self.package_version = None
        self.version_before_reopen = None
        self.out = out
        self.log_file = (out / f"{self.id}.log").open("w", encoding="utf-8")
        self.started = time.time()

    # -- output ---------------------------------------------------------
    def log(self, *parts) -> None:
        self.log_file.write(" ".join(str(p) for p in parts) + "\n")
        self.log_file.flush()

    def note(self, text: str) -> None:
        self.log(text)
        with PRINT_LOCK:
            print(f"{datetime.now():%H:%M:%S} [{self.id}] {text}", flush=True)

    def check(self, name: str, result: str, detail: str = "") -> None:
        self.checks.append({"name": name, "result": result, "detail": detail})
        self.note(f"CHECK {name}: {result}{' · ' + detail if detail else ''}")

    # -- the wizard ------------------------------------------------------
    def detail(self) -> dict:
        return self.api.call("GET", f"/sessions/{self.sid}")

    def say(self, message: str) -> str:
        started = time.time()
        pending, self.pending = self.pending, []
        body = {"message": message, "locale": self.locale}
        response = None
        for _ in range(30):
            response = self.api.call("POST", f"/sessions/{self.sid}/chat", body, stream=True)
            # The API lets one user have a few sessions working at a time (429), and a
            # turn runs on after its stream closes (409 until it ends): wait, do not give up.
            if isinstance(response, dict) and response.get("_error") in (409, 429):
                self.refused = f"{response['_error']}: " + response["_body"][:200]
                time.sleep(20)
                continue
            break
        if isinstance(response, dict):
            self.refused = f"{response.get('_error')}: {response.get('_body', '')[:200]}"
            self.note(f"! chat refused: {self.refused}")
            if pending:
                # Not given: a later question or the note before Gate 1 can carry them.
                self.note(f"! answers not sent: {', '.join(label for _, label, _ in pending)}")
            self.last_kinds = set()
            return ""
        for index, label, where in pending:
            self.sent.add(index)
            self.answer_log.append((label, where))
        try:
            reply, tools, problems, kinds = read_reply(response)
        except LOST_STREAM as err:
            # The turn runs on in the API: read its reply from the start, as a reload does.
            self.note(f"! the reply's stream was lost ({err}); joining it again")
            reply, tools, problems, kinds = self.rejoin()
        self.replies += 1
        self.unread_reply = reply
        self.last_kinds = kinds
        self.log(f"USER: {message}")
        self.log(
            f"WIZARD ({time.time() - started:.0f} s, {tools} tool calls, frames {sorted(kinds - QUIET_FRAMES)}):"
        )
        self.log(reply)
        self.take_problems(problems)
        return reply

    def take_problems(self, problems: list[dict]) -> None:
        """Keep a reply's error frames; a stop at the turn limit is counted on its own."""
        for problem in problems:
            if is_turn_limit(problem):
                self.turn_limits += 1
                self.note("! the reply stopped at the turn limit")
            else:
                self.stream_errors.append(problem)
                self.note(f"! stream error: {json.dumps(problem, ensure_ascii=False)[:300]}")

    def rejoin(self) -> tuple[str, int, list[dict], set[str]]:
        for _ in range(5):
            time.sleep(3)
            joined = self.api.call("GET", f"/sessions/{self.sid}/chat/stream", stream=True)
            if isinstance(joined, dict):
                if joined.get("_error") == 0:
                    continue
                break  # 204: the reply has ended, and its text is not in the log
            try:
                return read_reply(joined)
            except LOST_STREAM:
                continue
        # The reply's text is lost: wait for the turn to end, but not for ever.
        waited = 0
        while (self.detail() or {}).get("pending_turn"):
            if waited >= 1800:
                raise RuntimeError("a reply whose stream was lost did not end within 30 minutes")
            time.sleep(10)
            waited += 10
        self.lost_replies += 1
        self.log("LOST REPLY: its text is not in this log, and its questions are not counted")
        return "", 0, [], set()

    def count_questions(self, step: int) -> list[str]:
        """The last reply's questions, counted, if it came before the specification (step 4)."""
        reply, self.unread_reply = self.unread_reply, None
        if reply is None or self.gate1_approved or step >= 4:
            return []
        asked = questions_in(reply)
        if asked:
            self.rounds += 1
            self.questions += len(asked)
            self.log(f"QUESTIONS round {self.rounds}: {len(asked)}")
        return asked

    def reply_to(self, asked: list[str]) -> tuple[str, bool]:
        """What to say to a reply's questions, and whether a scripted answer is in it."""
        go_on = GO_ON[self.locale]
        if not self.answers or not asked:
            return go_on, False
        lines, notes = [], []
        picks = match_answers(asked, self.answers, self.sent)
        for question, (index, why) in zip(asked, picks):
            if index is None:
                continue
            label = answer_label(self.answers[index], index)
            self.pending.append((index, label, f"round {self.rounds}"))
            lines.append("- " + self.answers[index]["text"])
            notes.append(f'{label} <- "{question[:90]}" [{", ".join(why)}]')
        unmatched = len(asked) - len(lines)
        self.note(
            f"ANSWERS round {self.rounds}: "
            + ("; ".join(notes) or "no scripted answer matched")
            + (
                f"; {unmatched} of {len(asked)} questions unmatched -> the generic line"
                if unmatched
                else ""
            )
        )
        if not lines:
            return go_on, False
        return "\n".join(lines) + (f"\n\n{go_on}" if unmatched else ""), True

    def send_unsent_answers(self) -> bool:
        """Before Gate 1: give the scripted answers no question drew out, once."""
        left = [i for i in range(len(self.answers)) if i not in self.sent]
        if not left:
            return False
        head = ALSO_NOTE[self.locale]
        labels = [answer_label(self.answers[i], i) for i in left]
        self.note(f"ANSWERS before Gate 1 (also note): {', '.join(labels)}")
        message = head
        for index, label in zip(left, labels):
            line = "\n- " + self.answers[index]["text"]
            if len(message) + len(line) > MAX_MESSAGE and message != head:
                self.say(message)
                message = head
            self.pending.append((index, label, "before Gate 1"))
            message += line
        self.say(message)
        return True

    def state_line(self, d: dict) -> str:
        steps = d.get("blueprint", {}).get("steps") or []
        return json.dumps(
            {
                "step": d.get("step"),
                "gates": "".join(
                    str(d["gate_statuses"].get(f"gate_{n}", "?"))[0] for n in (1, 2, 3, 4)
                ),
                "status": d.get("status"),
                "steps": [
                    f"{s.get('name')} [{s.get('type')}{':' + s['component'] if s.get('component') else ''}]"
                    for s in steps
                ],
                "reopened": (d.get("metadata") or {}).get("gate_reopened"),
            },
            ensure_ascii=False,
        )

    # -- what a tester tries by hand --------------------------------------
    def say_with_reload(self, message: str) -> None:
        """Send a message, then act like a page reload: the reply must still be reachable."""
        result: dict = {}
        sender = threading.Thread(target=lambda: result.update(reply=self.say(message)))
        sender.start()
        pending = None
        # The turn is registered only once the agent has started, which on a session's
        # first message is its setup query: give it a minute.
        for _ in range(120):  # until the API says a reply is under way
            pending = (self.detail() or {}).get("pending_turn")
            if pending or not sender.is_alive():
                break
            time.sleep(0.5)
        if not pending:
            sender.join()
            self.check("reload_mid_reply", "skip", "no reply was under way to reload into")
            return
        second = self.api.call(
            "POST",
            f"/sessions/{self.sid}/chat",
            {"message": "hei", "locale": self.locale},
            stream=True,
        )
        refused = isinstance(second, dict) and second.get("_error") == 409
        if not isinstance(second, dict):
            # Accepted after all (the first reply had just ended): it is a turn of its
            # own now, which runs on even if its stream is closed. Read it to its end so
            # the walk does not run into it, and keep it in the log.
            probe_reply, _, probe_problems, _ = read_reply(second)
            self.log("USER: hei")
            self.log("WIZARD (probe accepted):")
            self.log(probe_reply)
            self.take_problems(probe_problems)
        joined = self.api.call("GET", f"/sessions/{self.sid}/chat/stream", stream=True)
        if isinstance(joined, dict):
            sender.join(timeout=15)
            code = joined.get("_error")
            if code in (404, 405):
                self.check("reload_mid_reply", "skip", "this API has no /chat/stream")
            elif code == 204 and not sender.is_alive():
                self.check("reload_mid_reply", "skip", "the reply had ended before the reload")
            else:
                self.check(
                    "reload_mid_reply", "fail", f"could not join the running reply: {joined}"
                )
        else:
            reply, _, _, _ = read_reply(joined)
            sender.join()
            same = reply.strip() == (result.get("reply") or "").strip()
            self.check(
                "reload_mid_reply",
                "pass" if reply.strip() and refused else "fail",
                f"joined reply {len(reply)} chars, same text as the first reader: {same}; "
                f"a second message while replying was {'refused (409)' if refused else 'NOT refused'}",
            )
        sender.join()

    def language_offer(self) -> None:
        self.say(OTHER_LANGUAGE[self.locale])
        offered = "offer_locale" in self.last_kinds
        self.check(
            "language_offer",
            "pass" if offered else "fail",
            "" if offered else "no offer_locale frame in the reply",
        )

    def reopen_in_panel(self) -> None:
        res = self.api.call("POST", f"/sessions/{self.sid}/gates/1/reopen")
        if res.get("_error") in (404, 405):
            self.check("reopen_in_panel", "skip", "this API has no gate reopening")
            return
        if "_error" in res:
            self.check("reopen_in_panel", "fail", str(res)[:300])
            return
        pending = all(res["gate_statuses"].get(f"gate_{n}") != "approved" for n in (1, 2, 3, 4))
        ok = pending and res.get("step") == 4
        self.check(
            "reopen_in_panel",
            "pass" if ok else "fail",
            f"step {res.get('step')}, gates {res['gate_statuses']}",
        )

    def change(self, name: str) -> None:
        text = self.case.get("change")
        if not text:
            self.check(name, "skip", "the case has no 'change' text")
            return
        before = self.detail()
        before_package = self.package_version_now()
        self.say(text)
        after = self.detail()
        after_package = self.package_version_now()
        reopened = [
            n
            for n in (1, 2, 3, 4)
            if before["gate_statuses"].get(f"gate_{n}") == "approved"
            and after["gate_statuses"].get(f"gate_{n}") != "approved"
        ]
        if reopened:
            self.version_before_reopen = self.package_version
            by = json.dumps((after.get("metadata") or {}).get("gate_reopened"), ensure_ascii=False)
            self.check(name, "pass", f"gates {reopened} reopened, step {after.get('step')}, {by}")
        elif (content_digest(before), before_package) != (content_digest(after), after_package):
            self.check(name, "fail", "approved content changed and no gate was reopened")
        else:
            self.check(name, "fail", "the wizard neither changed the solution nor reopened a gate")

    def package_version_now(self):
        """The package as the API identifies it now (``package_id``), or None.

        What a gate approves is the solution and the package; the blueprint alone
        misses a change made only in the package.
        """
        return package_id(self.api.call("GET", f"/sessions/{self.sid}/poc/files"))

    def after_gate(self, gate: int) -> None:
        if gate == 1 and "language_offer" in self.todo:
            self.todo.discard("language_offer")
            self.language_offer()
        elif gate == 2 and "reopen_in_panel" in self.todo:
            self.todo.discard("reopen_in_panel")
            self.reopen_in_panel()
        elif gate == 2 and "change_in_chat" in self.todo:
            self.todo.discard("change_in_chat")
            self.change("change_in_chat")
        elif gate == 3 and "change_after_gate3" in self.todo:
            self.todo.discard("change_after_gate3")
            self.change("change_after_gate3")

    # -- the package and its run ------------------------------------------
    def record(self, name: str, result: str, detail: str = "") -> None:
        """A check a reopened gate can reach twice: the latest result stands."""
        self.checks = [c for c in self.checks if c["name"] != name]
        self.check(name, result, detail)

    def package_ready(self) -> bool:
        files = self.api.call("GET", f"/sessions/{self.sid}/poc/files")
        names = [
            (f.get("path") or f.get("name") or str(f)) if isinstance(f, dict) else str(f)
            for f in files.get("files", [])
        ]
        if not files.get("generated") or not names:
            return False
        problems = files.get("problems") or []
        if files.get("ready") is False or problems:
            self.record("package", "fail", f"{len(names)} files, not complete: {problems}")
            return False
        self.package = names
        self.package_version = package_id(files)
        self.record("package", "pass", f"{len(names)} files, package {self.package_version}")
        if self.version_before_reopen is not None:
            # A change that reopened a gate has to end in a new package.
            fresh = self.package_version != self.version_before_reopen
            self.record(
                "package_after_change",
                "pass" if fresh else "fail",
                "" if fresh else "the package is the one from before the change",
            )
        return True

    def another_run_due(self) -> bool:
        """After a run: has the package changed (or the wizard replied to a failed run)?"""
        last = self.runs[-1]
        return run_due(
            len(self.runs),
            last["ok"],
            last["version"],
            self.package_version_now(),
            self.replies > last["replies"],
        )

    def upload_inputs(self) -> None:
        names = self.case.get("inputs", [])
        accepted, refused = [], []
        for name in names:
            path = (Path(self.opts.cases).resolve().parent / name).resolve()
            if not path.is_file():
                refused.append(f"{name}: no such file")
                continue
            boundary = uuid.uuid4().hex
            body = (
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                    "Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
                + path.read_bytes()
                + f"\r\n--{boundary}--\r\n".encode()
            )
            sent = self.api.call(
                "POST",
                f"/sessions/{self.sid}/poc/input",
                raw=(body, f"multipart/form-data; boundary={boundary}"),
            )
            self.log(f"input {path.name}: {sent}")
            if "_error" in sent:
                refused.append(f"{path.name}: {sent['_error']} {sent['_body'][:160]}")
            else:
                accepted.append(path.name)
        if names:
            # The API takes only the file types the session's blueprint names as input.
            self.record(
                "sample_input",
                "pass" if accepted else "fail",
                f"uploaded {accepted or 'nothing'}"
                + (f"; not taken: {refused}" if refused else ""),
            )

    def run_poc(self) -> None:
        if not self.runs:
            self.upload_inputs()  # the package keeps them when the wizard builds it again
        number = len(self.runs) + 1
        version = self.package_version_now()
        self.note(f"RUN {number} of at most {MAX_RUNS}: package {version}")
        started = self.api.call("POST", f"/sessions/{self.sid}/runs")
        for _ in range(30):
            # The sandbox takes a few runs at a time (429 sandbox_busy): wait, as for chat.
            if started.get("_error") != 429:
                break
            self.note(f"sandbox busy, waiting: {started['_body'][:200]}")
            time.sleep(20)
            started = self.api.call("POST", f"/sessions/{self.sid}/runs")
        if started.get("_error") == 503:
            self.no_sandbox = True
            self.record("poc_run", "skip", "no sandbox behind this API")
            return
        run = {"number": number, "version": version, "ok": False, "replies": self.replies}
        self.runs.append(run)
        if "_error" in started:
            self.record("poc_run", "fail", f"run {number} did not start: {str(started)[:300]}")
            return
        run_id = started["run_id"]
        # Follow the run the way the PoC tab does: the API records a successful run
        # (which Gate 3 asks for) and saves its log for the agent as this stream ends.
        stream = self.api.call("GET", f"/sessions/{self.sid}/runs/{run_id}/stream", stream=True)
        if not isinstance(stream, dict):
            for _ in stream:
                pass
        status = self.api.call("GET", f"/sessions/{self.sid}/runs/{run_id}")
        deadline = time.time() + 20 * 60
        while not status.get("finished") and "_error" not in status and time.time() < deadline:
            time.sleep(10)
            status = self.api.call("GET", f"/sessions/{self.sid}/runs/{run_id}")
        ok = run["ok"] = bool(status.get("finished")) and status.get("exit_code") == 0
        self.record(
            "poc_run",
            "pass" if ok else "fail",
            f"run {number}: " + json.dumps(status, ensure_ascii=False)[:300],
        )
        self.keep_run_output(number, run_id)
        if not ok and number < MAX_RUNS:
            # What a user does next: the wizard reads the run's log and mends the package.
            self.say(RUN_FAILED[self.locale])

    def keep_run_output(self, number: int, run_id: str) -> None:
        """Save what the run wrote to output/, and log the fields of its record."""
        output = self.api.call("GET", f"/sessions/{self.sid}/runs/{run_id}/output")
        if "_error" in output:
            self.log(f"RUN {number} output: not readable ({output['_error']})")
            return
        (self.out / f"{self.id}.run{number}.output.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record = output.get("record")
        self.log(
            f"RUN {number} output: files {[f.get('name') for f in output.get('files') or []]}; "
            f"record fields {sorted(record) if isinstance(record, dict) else None}"
        )

    # -- one use case from start to finish ---------------------------------
    def walk(self) -> dict:
        try:
            self._walk()
        except Exception as err:  # one broken case must not stop the set
            self.check("walk", "fail", f"{type(err).__name__}: {err}")
        return self.finish()

    def _walk(self) -> None:
        c = self.case
        created = self.api.call(
            "POST", "/sessions", {"user_id": self.api.user, "title": c["title"]}
        )
        if "_error" in created:
            raise RuntimeError(f"could not create a session: {created}")
        self.sid = created["id"]
        self.note(f"SESSION {self.sid} · {c['title']}")
        first = c["description"]
        if self.pace:
            first = f"{PACE[self.pace][self.locale]}\n{first}"
        if "reload_mid_reply" in self.todo:
            self.todo.discard("reload_mid_reply")
            self.say_with_reload(first)
        else:
            self.say(first)
        idle = refusals = 0
        seen = None
        for _ in range(80):
            d = self.detail()
            self.note("STATE " + self.state_line(d))
            step = d["step"]
            asked = self.count_questions(step)
            gate = GATE_AT.get(step)
            if (step, content_digest(d)) != seen:  # it moved: not idle
                seen, idle = (step, content_digest(d)), 0
            if (
                self.opts.run
                and not self.no_sandbox
                and (step == 10 if not self.runs else step in (10, 11))
                and (not self.runs or self.another_run_due())
                and self.package_ready()
            ):
                # The PoC step's test run, and one more when the wizard has mended the
                # package after a run: Gate 3 asks for a successful run of this package.
                self.run_poc()
                continue
            if gate and d["gate_statuses"].get(f"gate_{gate}") != "approved":
                if gate == 1 and self.answers and self.send_unsent_answers():
                    continue  # the wizard has heard every scripted answer before Gate 1
                approval = {"gate_statuses": {f"gate_{gate}": "approved"}}
                res = self.api.call("PATCH", f"/sessions/{self.sid}", approval)
                if "_error" in res:
                    self.note(f"Gate {gate} not approvable yet: {res['_body'][:300]}")
                    refusals += 1
                    if gate == 3 and len(self.runs) >= MAX_RUNS and not self.runs[-1]["ok"]:
                        self.note(f"gave up: {MAX_RUNS} test runs started and the last one failed")
                        return
                    if refusals > 6:
                        self.note("gave up: the gate stays refused")
                        return
                    self.say(GO_ON[self.locale])
                    continue
                self.note(f"GATE {gate} approved")
                self.gate1_approved = True
                idle = refusals = 0
                if gate < 4:
                    self.api.call("PATCH", f"/sessions/{self.sid}", {"step": step + 1})
                else:
                    self.api.call(
                        "PATCH", f"/sessions/{self.sid}", {"metadata": {"status": "done"}}
                    )
                if gate == self.opts.stop_at_gate:
                    return
                self.say(WAKE[self.locale].format(n=gate))
                if gate == 4:
                    return
                self.after_gate(gate)
                continue
            if step == 10 and self.package_ready():
                # The PoC step: the package is built here, the test run (above) belongs
                # here, and the page's "Next step" takes the session on to Gate 3.
                self.api.call("PATCH", f"/sessions/{self.sid}", {"step": 11})
                continue
            if step == 12:
                # The page's "Next step" from the documentation phase onto Gate 4.
                self.api.call("PATCH", f"/sessions/{self.sid}", {"step": 13})
                continue
            idle += 1
            if idle > 10:
                self.note("gave up: the session does not move on")
                return
            message, answered = self.reply_to(asked)
            if answered:
                idle = 0  # a round of questions that got its answers is not a stall
            self.say(message)

    def finish(self) -> dict:
        final = self.detail() if self.sid else {}
        gates = final.get("gate_statuses", {})
        steps = final.get("blueprint", {}).get("steps") or []
        components = sorted({s["component"] for s in steps if s.get("component")})
        if self.opts.stop_at_gate == 1:
            components = []  # still the placeholder: the components are chosen after Gate 1
        stop = self.opts.stop_at_gate
        wanted = range(1, (stop or 4) + 1)
        reached = bool(final) and all(gates.get(f"gate_{n}") == "approved" for n in wanted)
        self.check(
            "reaches_the_end" if not stop else f"reaches_gate_{stop}",
            "pass" if reached else "fail",
            f"step {final.get('step')}, gates {gates}"
            + (f"; last refusal: {self.refused}" if self.refused and not reached else ""),
        )
        pattern = (self.case.get("expect") or {}).get("component")
        if pattern and stop == 1:
            self.check("expected_component", "skip", "the components are chosen after Gate 1")
        elif pattern:
            hit = [name for name in components if re.search(pattern, name, re.I)]
            self.check(
                "expected_component",
                "pass" if hit else "fail",
                f"{hit or components} (wanted /{pattern}/)"
                if steps
                else "the blueprint has no steps",
            )
        asked = (
            f"{self.rounds} question rounds, {self.questions} questions before the specification"
            + (f"; {self.lost_replies} lost replies not counted" if self.lost_replies else "")
        )
        if self.pace == "quick":
            self.check(
                "quick_pace_one_round", quick_pace_result(self.rounds, self.lost_replies), asked
            )
        else:
            self.check("question_rounds", "info", asked)
        if self.answers:
            where = {
                place: [label for label, at in self.answer_log if (at == "before Gate 1") == late]
                for place, late in (("to questions", False), ("before Gate 1", True))
            }
            unsent = len(self.answers) - len(self.sent)
            self.check(
                "scripted_answers",
                "info",
                f"{len(self.answers)} answers: "
                + "; ".join(f"{len(v)} {k} ({', '.join(v) or '-'})" for k, v in where.items())
                + (f"; {unsent} not sent, the walk ended before Gate 1" if unsent else ""),
            )
        if self.runs:
            self.check(
                "poc_runs",
                "info",
                f"{len(self.runs)} started (at most {MAX_RUNS}): "
                + ", ".join(
                    f"run {r['number']} {'passed' if r['ok'] else 'failed'} on package {r['version']}"
                    for r in self.runs
                ),
            )
        self.check(
            "no_stream_errors",
            "fail" if self.stream_errors else "pass",
            f"{len(self.stream_errors)} error frames",
        )
        if self.turn_limits:
            self.check(
                "turn_limits",
                "info",
                f"{self.turn_limits} replies stopped at the turn limit (not counted as error frames)",
            )
        if (not stop or stop >= 3) and not any(c["name"] == "package" for c in self.checks):
            self.check("package", "fail", "no PoC package was generated")
        for left in sorted(self.todo - {"end_session"}):
            self.check(left, "skip", "the walk ended before this point")
        if "end_session" in self.case.get("scenarios", []) and self.sid:
            ended = self.api.call("POST", f"/sessions/{self.sid}/agent/end")
            if not self.replies:
                self.check("end_session", "skip", "the wizard never replied in this walk")
            elif ended.get("_error") in (404, 405):
                self.check("end_session", "skip", "this API has no /agent/end")
            else:
                live = (self.detail() or {}).get("agent_live")
                self.check(
                    "end_session",
                    "pass" if "_error" not in ended and not live else "fail",
                    f"agent_live {live}",
                )
        (self.out / f"{self.id}.json").write_text(
            json.dumps(
                {
                    k: final.get(k)
                    for k in (
                        "id",
                        "step",
                        "status",
                        "gate_statuses",
                        "blueprint",
                        "target_output_spec",
                        "metadata",
                    )
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.log_file.close()
        return {
            "id": self.id,
            "title": self.case["title"],
            "session": self.sid,
            "step": final.get("step"),
            "minutes": round((time.time() - self.started) / 60, 1),
            "pace": self.pace or None,
            "question_rounds": self.rounds,
            "questions": self.questions,
            "components": components,
            "package_files": len(getattr(self, "package", [])),
            "runs": len(self.runs),
            "answers_sent": [{"answer": label, "at": at} for label, at in self.answer_log],
            "checks": self.checks,
        }


def write_summary(out: Path, results: list[dict], args: argparse.Namespace) -> None:
    mark = {"pass": "ok", "fail": "FAIL", "skip": "skip", "info": "info"}
    lines = [
        "# Wizard use case run",
        "",
        f"{datetime.now():%Y-%m-%d %H:%M} · API `{args.base}` · PoC run {'on' if args.run else 'off'}"
        + (f" · pace {args.pace}" if args.pace else "")
        + (f" · stopped at Gate {args.stop_at_gate}" if args.stop_at_gate else ""),
        "",
        "| Case | Result | Step | Min | Question rounds | Questions | Components | Package files | Runs |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        counts = {k: sum(1 for c in r["checks"] if c["result"] == k) for k in mark}
        verdict = f"{counts['fail']} failed" if counts["fail"] else "all passed"
        verdict += f" ({counts['pass']} ok, {counts['skip']} skipped)"
        lines.append(
            f"| {r['id']} | {verdict} | {r['step']} | {r['minutes']} | {r['question_rounds']} | {r['questions']} | {', '.join(r['components']) or '-'} | {r['package_files']} | {r['runs']} |"
        )
    for r in results:
        lines += [
            "",
            f"## {r['id']}: {r['title']}",
            "",
            f"Session `{r['session']}` · log `{r['id']}.log` · final state `{r['id']}.json`",
            "",
        ]
        lines += [
            f"- **{mark[c['result']]}** {c['name']}" + (f": {c['detail']}" if c["detail"] else "")
            for c in r["checks"]
        ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default=os.environ.get("WIZARD_API_URL", "http://localhost:8100"))
    parser.add_argument("--user", default=os.environ.get("WIZARD_USER_ID", "dev@gaik.local"))
    parser.add_argument(
        "--token-env",
        default="WIZARD_API_TOKEN",
        help="environment variable that holds the service token, if the API wants one",
    )
    parser.add_argument("--cases", default=str(HERE / "usecases.json"))
    parser.add_argument("--only", default="", help="comma-separated case ids")
    parser.add_argument("--parallel", type=int, default=1, help="sessions at a time")
    parser.add_argument(
        "--run",
        action="store_true",
        help="start the PoC test run before Gate 3 (needs the sandbox)",
    )
    parser.add_argument(
        "--pace",
        choices=["quick", "thorough"],
        help="start each case with the web app's pace line (default: the case's 'pace', or none)",
    )
    parser.add_argument(
        "--stop-at-gate",
        type=int,
        default=0,
        choices=[0, 1, 2, 3],
        help="stop once this gate is approved",
    )
    parser.add_argument(
        "--out",
        default="",
        help="folder for logs and the summary (default: a new folder in the temp directory)",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--from-evaluation",
        metavar="FOLDER",
        help="write a cases file from a folder of evaluation cases (initial_prompt.txt, "
        "fixtures/, scripted_answers.json in each subfolder) and stop",
    )
    parser.add_argument(
        "--write-cases",
        metavar="FILE",
        help="where --from-evaluation writes (default: evaluation-cases.json in the temp "
        "directory); it holds paths of this machine, so not inside a repository",
    )
    args = parser.parse_args()

    if args.from_evaluation:
        target = Path(
            args.write_cases
            or Path(tempfile.gettempdir()) / "wizard-usecase-runs" / "evaluation-cases.json"
        ).resolve()
        if repository_of(target.parent):
            parser.error(f"{target} is inside a repository: write the cases file outside it")
        left_out: list[str] = []
        built = cases_from_evaluation(Path(args.from_evaluation), left_out)
        if not built:
            parser.error(f"no subfolder of {args.from_evaluation} has an initial_prompt.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        about = "Built by run_usecases.py --from-evaluation. 'inputs' are paths on this machine."
        target.write_text(
            json.dumps({"about": about, "cases": built}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for c in built:
            print(f"{c['id']:32} {len(c['inputs'])} inputs  ·  {len(c['answers'])} answers")
        for note in left_out:
            print(f"! {note}")
        print(f"Cases file: {target}")
        return 0

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = [x.strip() for x in args.only.split(",") if x.strip()]
        unknown = set(wanted) - {c["id"] for c in cases}
        if unknown:
            parser.error(f"unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in wanted]
    if args.list:
        for c in cases:
            print(
                f"{c['id']:24} {c.get('locale', 'fi')}  {', '.join(c.get('scenarios', [])) or '-'}"
                f"  ·  {len(c.get('inputs', []))} inputs  ·  {len(c.get('answers', []))} answers"
                f"  ·  {c['title']}"
            )
        return 0

    out = (
        Path(args.out)
        if args.out
        else Path(tempfile.gettempdir()) / "wizard-usecase-runs" / f"{datetime.now():%Y%m%d-%H%M%S}"
    )
    out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get(args.token_env, "").strip() or None
    parsed = urllib.parse.urlsplit(args.base)
    if (
        token
        and parsed.scheme != "https"
        and parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    ):
        print(
            f"Not sending the service token to {args.base}: "
            "use https, or a port-forward to localhost."
        )
        return 2
    api = Api(args.base, args.user, token)
    probe = api.call("GET", "/sessions/00000000-0000-0000-0000-000000000000")
    if probe.get("_error") == 0:
        print(f"No wizard_api at {args.base}: {probe['_body']}")
        return 2
    print(f"{len(cases)} use cases against {args.base}; results in {out}", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        results = list(pool.map(lambda c: Walk(api, c, out, args).walk(), cases))
    write_summary(out, results, args)
    failed = sum(1 for r in results for c in r["checks"] if c["result"] == "fail")
    print(f"Summary: {out / 'summary.md'} · {failed} failed checks")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
