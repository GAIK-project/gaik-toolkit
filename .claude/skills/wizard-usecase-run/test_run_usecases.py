"""Offline checks of the runner's own logic.

Run in this folder: python -m unittest test_run_usecases
"""

import argparse
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import make_inputs
import run_usecases

HERE = Path(__file__).resolve().parent
EVALUATION = HERE.parents[2] / "evaluation_layer/eval_methods/Solution wizard evaluation/use cases"
ANSWERS = [
    {"id": "A1", "topic": "users_and_reviewers", "text": "Technicians use it."},
    {"id": "A2", "keywords": ["schema", "fields", "types"], "text": "Use the Ticket schema."},
    {"id": "A3", "keywords": ["privacy", "retention", "fields"], "text": "Keep nothing."},
    {"id": "A4", "topic": "budget", "text": "No budget is set.", "repeatable": True},
]


class FakeApi:
    """A chat that takes every message and replies "ok", or refuses each one."""

    user = "u"

    def __init__(self, refuse=False):
        self.refuse = refuse
        self.said = []

    def call(self, method, path, body=None, stream=False, raw=None):
        if self.refuse:
            return {"_error": 500, "_body": "refused"}
        self.said.append(body["message"])
        return [b'data: {"delta": "ok"}\n', b'data: {"done": true}\n']


class QuestionsIn(unittest.TestCase):
    def test_list_items_that_ask_are_the_questions(self):
        reply = (
            "Tarvitsen vielä muutaman tiedon:\n\n"
            "1. Missä muodossa laskut tulevat?\n"
            "2. Kuka tarkistaa tuloksen,\n   ja kuinka usein?\n"
            "- Oletan, että kieli on suomi.\n"
        )
        self.assertEqual(len(run_usecases.questions_in(reply)), 2)

    def test_code_addresses_and_fenced_blocks_do_not_ask(self):
        reply = (
            "- Run `ls ?` first\n"
            "- See https://example.org/search?q=1 for more.\n"
            "```\n- is this a question?\n```\n"
        )
        self.assertEqual(run_usecases.questions_in(reply), [])

    def test_a_closing_question_in_prose_is_one_question(self):
        self.assertEqual(len(run_usecases.questions_in("Got it.\n\nWho reads the result?")), 1)
        self.assertEqual(run_usecases.questions_in("Is it? Yes.\n\nI will go on."), [])

    def test_a_statement_asks_nothing(self):
        self.assertEqual(run_usecases.questions_in("Here is the specification.\n- Input: PDF"), [])

    def test_a_bullet_that_asks_under_a_question_is_a_question_of_its_own(self):
        # As the web app's form reads it, whatever the indent: two questions.
        for indent in ("   ", "    ", "      "):
            reply = f"1. Which fields do you need?\n{indent}- And which of them are required?\n"
            self.assertEqual(
                run_usecases.questions_in(reply),
                ["Which fields do you need?", "And which of them are required?"],
                repr(indent),
            )

    def test_options_under_a_question_are_no_questions(self):
        reply = (
            "1. Which format do the invoices come in?\n"
            "    - PDF\n"
            "    - Scanned images\n"
            "- Is one invoice one file?\n"
        )
        self.assertEqual(len(run_usecases.questions_in(reply)), 2)

    def test_what_an_item_ending_in_a_colon_lists_is_not_its_text(self):
        reply = "- My default is:\n  Who reviews it?\n"
        self.assertEqual(run_usecases.questions_in(reply), [])
        wrapped = "- Who reviews\n  the result?\n"
        self.assertEqual(run_usecases.questions_in(wrapped), ["Who reviews the result?"])


class PackageAndTurnLimit(unittest.TestCase):
    def test_the_package_is_named_by_the_digest_gate_3_compares(self):
        files = {"generated": True, "version": "v1", "package_digest": "d1"}
        self.assertEqual(run_usecases.package_id(files), "d1")
        # A changed prompt changes the digest and not the version: a new run is due.
        changed = dict(files, package_digest="d2")
        self.assertTrue(
            run_usecases.run_due(
                1, True, run_usecases.package_id(files), run_usecases.package_id(changed), False
            )
        )

    def test_an_older_api_names_the_package_by_its_version(self):
        self.assertEqual(run_usecases.package_id({"generated": True, "version": "v1"}), "v1")
        self.assertIsNone(run_usecases.package_id({"generated": False, "files": []}))
        self.assertIsNone(run_usecases.package_id({"_error": 0, "_body": "lost"}))

    def test_a_stop_at_the_turn_limit_is_no_error_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            case = {"id": "t", "title": "t", "locale": "en", "description": "d"}
            walk = run_usecases.Walk(None, case, Path(folder), argparse.Namespace(pace=None))
            limit = {"error": True, "limit": "turns", "message": "stopped"}
            walk.take_problems([limit, {"error": True, "message": "failed"}])
            self.assertEqual(walk.turn_limits, 1)
            self.assertEqual(walk.stream_errors, [{"error": True, "message": "failed"}])
            walk.log_file.close()


class ScriptedAnswers(unittest.TestCase):
    def picks(self, questions, sent=frozenset()):
        return [index for index, _ in run_usecases.match_answers(questions, ANSWERS, sent)]

    def test_a_question_takes_the_answer_its_words_name(self):
        asked = ["Who are the users?", "What is the retention period?", "Which colour is best?"]
        self.assertEqual(self.picks(asked), [0, 2, None])

    def test_keywords_come_from_the_topic_when_none_are_given(self):
        self.assertEqual(run_usecases.answer_keywords(ANSWERS[0]), ["users", "reviewers"])
        self.assertEqual(run_usecases.answer_keywords(ANSWERS[1]), ["schema", "fields", "types"])

    def test_a_keyword_two_answers_share_does_not_decide(self):
        # "fields" is in A2 and A3; "privacy" is in A3 alone.
        self.assertEqual(self.picks(["Which fields raise privacy concerns?"]), [2])
        self.assertEqual(self.picks(["Which fields are there?"]), [1])  # a tie: the first listed

    def test_a_word_form_still_hits(self):
        self.assertEqual(self.picks(["Who will review the result?"]), [0])
        self.assertEqual(self.picks(["What field type is the date?"]), [1])

    def test_an_answer_goes_out_once_unless_repeatable(self):
        self.assertEqual(self.picks(["What is the schema?", "And its types?"]), [1, None])
        self.assertEqual(self.picks(["What is the schema?"], sent={1}), [None])
        self.assertEqual(self.picks(["Is there a budget?"], sent={3}), [3])

    def test_code_and_addresses_in_a_question_do_not_match(self):
        self.assertEqual(self.picks(["Is `schema` at https://example.org/fields fine?"]), [None])

    def walk(self, folder, answers, api=None):
        case = {"id": "t", "title": "t", "locale": "en", "description": "d", "answers": answers}
        walk = run_usecases.Walk(api, case, Path(folder), argparse.Namespace(pace=None))
        walk.sid = "s"
        return walk

    def test_the_reply_carries_the_matched_answers_and_the_generic_line(self):
        with tempfile.TemporaryDirectory() as folder:
            api = FakeApi()
            walk = self.walk(folder, ANSWERS, api)
            message, answered = walk.reply_to(["What is the schema?", "Which colour?"])
            self.assertTrue(answered)
            self.assertEqual(message, "- Use the Ticket schema.\n\n" + run_usecases.GO_ON["en"])
            self.assertEqual(walk.sent, set())  # given once the API takes the message
            walk.say(message)
            self.assertEqual(walk.sent, {1})
            self.assertEqual(walk.reply_to(["Which colour?"]), (run_usecases.GO_ON["en"], False))
            self.assertTrue(walk.send_unsent_answers())
            self.assertEqual(
                api.said[-1],
                "Also note:\n- Technicians use it.\n- Keep nothing.\n- No budget is set.",
            )
            self.assertFalse(walk.send_unsent_answers())  # each of them once
            walk.log_file.close()

    def test_answers_in_a_refused_message_are_still_to_give(self):
        with tempfile.TemporaryDirectory() as folder:
            api = FakeApi(refuse=True)
            walk = self.walk(folder, ANSWERS, api)
            message, _ = walk.reply_to(["What is the schema?"])
            walk.say(message)
            self.assertEqual((walk.sent, walk.answer_log), (set(), []))
            api.refuse = False
            self.assertTrue(walk.send_unsent_answers())
            self.assertIn("- Use the Ticket schema.", api.said[-1])
            self.assertEqual(walk.sent, {0, 1, 2, 3})
            walk.log_file.close()

    def test_a_case_without_answers_says_the_generic_line(self):
        with tempfile.TemporaryDirectory() as folder:
            walk = self.walk(folder, [])
            said = walk.reply_to(["What is the schema?"])
            self.assertEqual(said, (run_usecases.GO_ON["en"], False))
            walk.log_file.close()


class RunDue(unittest.TestCase):
    def test_the_first_run_is_due(self):
        self.assertTrue(run_usecases.run_due(0, False, None, "v1", False))

    def test_a_changed_package_is_run_again(self):
        self.assertTrue(run_usecases.run_due(1, False, "v1", "v2", True))
        self.assertTrue(run_usecases.run_due(1, True, "v1", "v2", False))  # after a reopened gate

    def test_the_same_package_is_not_run_again(self):
        self.assertFalse(run_usecases.run_due(1, False, "v1", "v1", True))
        self.assertFalse(run_usecases.run_due(1, True, "v1", "v1", True))

    def test_without_a_version_a_reply_after_a_failed_run_is_enough(self):
        self.assertTrue(run_usecases.run_due(1, False, None, None, True))
        self.assertFalse(run_usecases.run_due(1, False, None, None, False))
        self.assertFalse(run_usecases.run_due(1, True, None, None, True))

    def test_three_runs_a_case(self):
        self.assertTrue(run_usecases.run_due(2, False, "v2", "v3", True))
        self.assertFalse(run_usecases.run_due(3, False, "v3", "v4", True))


class AnswerSheets(unittest.TestCase):
    """A sheet of scripted answers in a shape the conversion did not expect."""

    def convert(self, sheets: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
        with tempfile.TemporaryDirectory() as folder:
            for name, sheet in sheets.items():
                uc = Path(folder) / f"{name}_evaluation"
                uc.mkdir()
                (uc / "initial_prompt.txt").write_text("Describe.", encoding="utf-8")
                (uc / "scripted_answers.json").write_text(sheet, encoding="utf-8")
            notes: list[str] = []
            cases = run_usecases.cases_from_evaluation(Path(folder), notes)
        return {c["id"]: c for c in cases}, notes

    def test_an_entry_without_an_answer_is_left_out_and_the_rest_are_kept(self):
        sheet = json.dumps(
            {
                "answers": [
                    {"id": "SA01", "topic": "output fields", "answer": "Use these."},
                    {"id": "SA02", "topic": "privacy"},
                    "not an entry",
                    {"id": "SA04", "topic": "language", "answer": "   "},
                    {"topic": "review", "trigger": None, "answer": "A person checks."},
                ]
            }
        )
        cases, notes = self.convert({"UC01_a": sheet})
        answers = cases["uc01-a"]["answers"]
        self.assertEqual([a["id"] for a in answers], ["SA01", "review"])
        self.assertEqual(answers[1]["keywords"], run_usecases.words_of("review"))
        self.assertEqual(len(notes), 3)
        self.assertTrue(
            all(note.startswith("UC01_a: scripted_answers.json: entry ") for note in notes)
        )

    def test_a_sheet_that_is_a_list_is_read_as_its_answers(self):
        cases, notes = self.convert(
            {"UC02_b": json.dumps([{"topic": "fields", "answer": "Three."}])}
        )
        self.assertEqual([a["text"] for a in cases["uc02-b"]["answers"]], ["Three."])
        self.assertEqual(notes, [])

    def test_an_odd_sheet_does_not_stop_the_other_cases(self):
        good = json.dumps(
            {"scripted_answers": [{"answer_id": "A1", "topic": "t", "answer": "Yes."}]}
        )
        cases, notes = self.convert(
            {"UC03_c": "{ not json", "UC04_d": '{"answers": "none"}', "UC05_e": good}
        )
        self.assertEqual(sorted(cases), ["uc03-c", "uc04-d", "uc05-e"])
        self.assertEqual(cases["uc03-c"]["answers"], [])
        self.assertEqual(cases["uc04-d"]["answers"], [])
        self.assertEqual([a["id"] for a in cases["uc05-e"]["answers"]], ["A1"])
        self.assertEqual(len(notes), 2)


@unittest.skipUnless(EVALUATION.is_dir(), "the evaluation cases are not in this checkout")
class FromEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in run_usecases.cases_from_evaluation(EVALUATION)}

    def test_every_evaluation_case_becomes_a_case(self):
        self.assertEqual(len(self.cases), 5)
        for case in self.cases.values():
            self.assertTrue(case["description"], case["id"])
            self.assertGreaterEqual(len(case["answers"]), 9, case["id"])
            for answer in case["answers"]:
                self.assertRegex(answer["id"], r"^SA\d\d$")
                self.assertTrue(answer["text"] and answer["keywords"], answer["id"])
            self.assertTrue(case["inputs"], case["id"])
            for name in case["inputs"]:
                self.assertTrue(Path(name).is_file(), name)

    def test_the_inputs_are_what_a_run_reads_not_what_it_is_checked_against(self):
        names = [Path(p).name for p in self.cases["uc01-audio-incident"]["inputs"]]
        self.assertEqual(names, ["incident_report_fi.wav"])
        names = {Path(p).name for p in self.cases["uc03-document-rag"]["inputs"]}
        self.assertEqual(len(names), 6)  # three documents, two JSON files and the bundle
        self.assertIn("poc_input_bundle.json", names)
        for case in self.cases.values():
            for name in case["inputs"]:
                self.assertNotIn("expected", Path(name).name)

    def test_a_question_about_the_schema_gets_the_schema_answer(self):
        answers = self.cases["uc01-audio-incident"]["answers"]
        asked = [
            "Which fields should the ticket contain, and which are required?",
            "Who reviews the ticket before it goes into the system?",
        ]
        picked = [answers[i]["id"] for i, _ in run_usecases.match_answers(asked, answers)]
        self.assertEqual(picked[0], "SA03")
        self.assertIn(picked[1], ("SA01", "SA05"))

    def test_the_cases_file_is_not_written_into_a_repository(self):
        self.assertIsNotNone(run_usecases.repository_of(HERE))
        self.assertIsNone(run_usecases.repository_of(Path(tempfile.gettempdir())))


class Cases(unittest.TestCase):
    def test_every_listed_input_exists_and_is_small(self):
        cases = json.loads((HERE / "usecases.json").read_text(encoding="utf-8"))["cases"]
        total = 0
        for case in cases:
            self.assertIn(case.get("pace"), (None, "quick", "thorough"), case["id"])
            for name in case.get("inputs", []):
                path = HERE / name
                self.assertTrue(path.is_file(), f"{case['id']}: {name}")
                total += path.stat().st_size
        self.assertLess(total, 600_000)

    def test_pace_lines_exist_in_both_languages(self):
        for pace in ("quick", "thorough"):
            self.assertEqual(set(run_usecases.PACE[pace]), {"fi", "en"})

    def test_generated_inputs_are_the_committed_ones(self):
        files = make_inputs.generated()
        self.assertEqual(
            set(files),
            {"invoice-1001.pdf", "invoice-1002.pdf", "condition-earlier-report.pdf"}
            | {"condition-notes.txt", "sales-rows.xlsx"}
            | {"policy-leave.pdf", "policy-remote-work.pdf", "policy-questions.txt"}
            | {"sales-questions.txt"},
        )
        for name, data in files.items():
            with self.subTest(name):
                self.assertEqual(data, (HERE / "inputs" / name).read_bytes())
        for name in sorted(name for name in files if name.endswith(".pdf")):
            self.assertTrue(
                files[name].startswith(b"%PDF-") and files[name].rstrip().endswith(b"%%EOF")
            )

    def test_the_spreadsheet_names_one_creating_system_on_every_os(self):
        # ZipInfo takes the creating system from the OS it runs on: without a
        # fixed one the bytes differ between Windows and macOS or Linux.
        with zipfile.ZipFile(io.BytesIO(make_inputs.generated()["sales-rows.xlsx"])) as archive:
            self.assertEqual({info.create_system for info in archive.infolist()}, {0})


class QuickPace(unittest.TestCase):
    def test_one_round_passes_and_two_fail(self):
        self.assertEqual(run_usecases.quick_pace_result(0, 0), "pass")
        self.assertEqual(run_usecases.quick_pace_result(1, 0), "pass")
        self.assertEqual(run_usecases.quick_pace_result(2, 0), "fail")

    def test_a_lost_reply_leaves_it_open(self):
        self.assertEqual(run_usecases.quick_pace_result(1, 1), "info")
        self.assertEqual(run_usecases.quick_pace_result(0, 2), "info")
        # Two counted rounds fail whatever was lost.
        self.assertEqual(run_usecases.quick_pace_result(2, 1), "fail")


if __name__ == "__main__":
    unittest.main()
