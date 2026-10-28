"""ควิซเต็มคลิป → vLLM ตรง (2026-10-28)

รันด้วย stdlib เท่านั้น (อิมเมจไม่มี pytest):
    python -m unittest discover -s tests -v

ใช้ stub HTTP server ในโปรเซส แทน vLLM — ไม่แตะเครือข่ายภายนอก ไม่แตะ Pinecone
"""

import importlib
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import quiz_analyzer as qa  # noqa: E402


def _item(n, answer_idx=1):
    options = [f"ตัวเลือก {n}-{i}" for i in range(1, 5)]
    return {"question": f"คำถามข้อ {n} เกี่ยวกับใจความของคลิป?", "options": options,
            "answer": options[answer_idx]}


QUIZ_8 = [_item(n) for n in range(1, 9)]


def _completion(content, finish="stop", reasoning=None):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"id": "chatcmpl-stub", "object": "chat.completion", "model": "aunjai-120b",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}}


class StubLLM:
    """vLLM ปลอม: คืนคำตอบตามคิวที่ตั้งไว้ · จดคำขอ · วัดจำนวนคำขอที่ค้างพร้อมกันสูงสุด"""

    def __init__(self):
        self.responses = []
        self.requests = []
        self.delay = 0.0
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with stub.lock:
                    stub.in_flight += 1
                    stub.max_in_flight = max(stub.max_in_flight, stub.in_flight)
                    stub.requests.append({"path": self.path, "body": body,
                                          "auth": self.headers.get("Authorization")})
                    status, payload = stub.responses.pop(0) if stub.responses else (200, _completion(json.dumps(QUIZ_8)))
                try:
                    if stub.delay:
                        time.sleep(stub.delay)
                    raw = payload.encode() if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                finally:
                    with stub.lock:
                        stub.in_flight -= 1

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


TRANSCRIPT = [{"start": 0.0, "text": "คุณยายคะ ถ้าเชื่อพระเจ้าแล้วเชื่อศาสนาอื่นด้วยได้ไหม"},
              {"start": 5.2, "text": "คำถามดีมาก ลองศึกษาแล้วอธิษฐานขอให้พระเจ้าช่วยให้เข้าใจ"}]


class VllmQuizTests(unittest.TestCase):
    def setUp(self):
        self.stub = StubLLM()
        self.patches = [
            mock.patch.object(qa, "QUIZ_LLM_BACKEND", "vllm"),
            mock.patch.object(qa, "QUIZ_LLM_BASE_URL", self.stub.url + "/v1"),
            mock.patch.object(qa, "QUIZ_LLM_MODEL", "aunjai-120b"),
            mock.patch.object(qa, "QUIZ_LLM_API_KEY", ""),
            mock.patch.object(qa, "QUIZ_LLM_REASONING_EFFORT", "low"),
            mock.patch.object(qa, "QUIZ_LLM_MAX_TOKENS", 6000),
            mock.patch.object(qa, "_vllm_gate", threading.BoundedSemaphore(1)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.stub.close()

    def test_happy_path_request_shape_and_output(self):
        self.stub.responses = [(200, _completion(json.dumps(QUIZ_8, ensure_ascii=False)))]
        out = qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertEqual(out, QUIZ_8)
        self.assertEqual(len(self.stub.requests), 1)
        req = self.stub.requests[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        body = req["body"]
        self.assertEqual(body["model"], "aunjai-120b")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["max_tokens"], 6000)
        self.assertEqual(body["temperature"], 0.3)
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertIn("=== TRANSCRIPT ===", body["messages"][1]["content"])
        self.assertIn("[0:05]", body["messages"][1]["content"])
        self.assertNotIn("openclaw", json.dumps(body))
        self.assertIsNone(req["auth"])

    def test_reasoning_trap_retries_once_with_double_budget(self):
        self.stub.responses = [
            (200, _completion(None, finish="length", reasoning="คิด..." * 500)),
            (200, _completion(json.dumps(QUIZ_8, ensure_ascii=False))),
        ]
        out = qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertEqual(len(out), 8)
        self.assertEqual([r["body"]["max_tokens"] for r in self.stub.requests], [6000, 12000])

    def test_reasoning_trap_twice_returns_empty_and_never_uses_reasoning(self):
        # reasoning มี JSON ที่ parse ได้ — ต้องไม่ถูกหยิบมาเป็นควิซ
        leaked = json.dumps(QUIZ_8, ensure_ascii=False)
        self.stub.responses = [
            (200, _completion(None, finish="length", reasoning=leaked)),
            (200, _completion("", finish="length", reasoning=leaked)),
        ]
        self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
        self.assertEqual(len(self.stub.requests), 2)

    def test_truncated_json_retries_with_bigger_budget(self):
        cut = json.dumps(QUIZ_8, ensure_ascii=False)[:300]
        self.stub.responses = [
            (200, _completion(cut, finish="length")),
            (200, _completion(json.dumps(QUIZ_8, ensure_ascii=False))),
        ]
        self.assertEqual(len(qa.analyze_full_clip_quiz(TRANSCRIPT)), 8)
        self.assertEqual(self.stub.requests[1]["body"]["max_tokens"], 12000)

    def test_budget_ceiling_no_second_call(self):
        with mock.patch.object(qa, "QUIZ_LLM_MAX_TOKENS", 16000):
            self.stub.responses = [(200, _completion(None, finish="length", reasoning="x"))]
            self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
        self.assertEqual(len(self.stub.requests), 1)

    def test_effort_none_omits_field(self):
        with mock.patch.object(qa, "QUIZ_LLM_REASONING_EFFORT", "none"):
            qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertNotIn("reasoning_effort", self.stub.requests[0]["body"])

    def test_api_key_sent_when_configured(self):
        with mock.patch.object(qa, "QUIZ_LLM_API_KEY", "stub-key"):
            qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertEqual(self.stub.requests[0]["auth"], "Bearer stub-key")

    def test_http_error_and_bad_body_return_empty(self):
        self.stub.responses = [(500, {"error": "boom"})]
        self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
        self.stub.responses = [(200, "not json")]
        self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
        self.stub.responses = [(200, {"choices": []})]
        self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])

    def test_connection_refused_returns_empty_and_releases_gate(self):
        with mock.patch.object(qa, "QUIZ_LLM_BASE_URL", "http://127.0.0.1:9/v1"):
            self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
            self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])  # ไม่ค้างคิว

    def test_empty_transcript_makes_no_call(self):
        self.assertEqual(qa.analyze_full_clip_quiz([]), [])
        self.assertEqual(self.stub.requests, [])

    def test_concurrency_capped_by_gate(self):
        for cap in (1, 2):
            self.stub.max_in_flight = 0
            self.stub.delay = 0.3
            with mock.patch.object(qa, "_vllm_gate", threading.BoundedSemaphore(cap)):
                threads = [threading.Thread(target=qa.analyze_full_clip_quiz, args=(TRANSCRIPT,))
                           for _ in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(10)
            self.assertEqual(self.stub.max_in_flight, cap)

    def test_queue_timeout_gives_up_without_call(self):
        gate = threading.BoundedSemaphore(1)
        gate.acquire()
        with mock.patch.object(qa, "_vllm_gate", gate), mock.patch.object(qa, "QUIZ_LLM_QUEUE_WAIT", 0.1):
            self.assertEqual(qa.analyze_full_clip_quiz(TRANSCRIPT), [])
        self.assertEqual(self.stub.requests, [])

    def test_openclaw_switch_keeps_old_request(self):
        with mock.patch.object(qa, "QUIZ_LLM_BACKEND", "openclaw"), \
             mock.patch.object(qa, "OPENCLAW_API_URL", self.stub.url), \
             mock.patch.object(qa, "OPENCLAW_AGENT_ID", "unjai"), \
             mock.patch.object(qa, "OPENCLAW_API_KEY", ""):
            out = qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertEqual(len(out), 8)
        body = self.stub.requests[0]["body"]
        self.assertEqual(self.stub.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(body["model"], "openclaw:unjai")
        self.assertEqual([m["role"] for m in body["messages"]], ["user"])
        self.assertNotIn("max_tokens", body)

    def test_unknown_backend_falls_to_vllm(self):
        with mock.patch.object(qa, "QUIZ_LLM_BACKEND", "gpt"):
            qa.analyze_full_clip_quiz(TRANSCRIPT)
        self.assertEqual(self.stub.requests[0]["body"]["model"], "aunjai-120b")


class ParserTests(unittest.TestCase):
    def test_plain_fenced_wrapped_and_prose(self):
        arr = json.dumps(QUIZ_8, ensure_ascii=False)
        for text in (arr, f"```json\n{arr}\n```", json.dumps({"quiz": QUIZ_8}, ensure_ascii=False),
                     f"```json\n{json.dumps({'questions': QUIZ_8}, ensure_ascii=False)}\n```",
                     f"นี่คือแบบทดสอบ:\n{arr}"):
            self.assertEqual(qa._parse_quiz_response(text), QUIZ_8, text[:40])

    def test_answer_must_match_an_option(self):
        good = _item(1)
        spaced = {**_item(2), "answer": "  ตัวเลือก 2-3 "}
        letter = {**_item(3), "answer": "B"}
        wrong = {**_item(4), "answer": "ไม่มีในตัวเลือก"}
        three = {**_item(5), "options": ["a", "b", "c"], "answer": "a"}
        out = qa._validate_quiz([good, spaced, letter, wrong, three, "ข้อความ", None])
        self.assertEqual([q["question"] for q in out], [good["question"], spaced["question"]])
        self.assertEqual(out[1]["answer"], "ตัวเลือก 2-3")

    def test_garbage_returns_empty(self):
        self.assertEqual(qa._parse_quiz_response("ขอโทษ ฉันทำไม่ได้"), [])
        self.assertEqual(qa._parse_quiz_response('{"error": "x"}'), [])


class ConfigTests(unittest.TestCase):
    KEYS = ("QUIZ_LLM_BACKEND", "QUIZ_LLM_BASE_URL", "QUIZ_LLM_MODEL", "QUIZ_LLM_REASONING_EFFORT",
            "QUIZ_LLM_MAX_TOKENS", "QUIZ_LLM_MAX_CONCURRENCY")

    def _reload(self, env):
        clean = {k: v for k, v in os.environ.items() if k not in self.KEYS}
        clean.update(env)
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch("dotenv.load_dotenv"):
            return importlib.reload(config)

    def tearDown(self):
        self._reload({})

    def test_defaults(self):
        c = self._reload({})
        self.assertEqual((c.QUIZ_LLM_BACKEND, c.QUIZ_LLM_BASE_URL, c.QUIZ_LLM_MODEL,
                          c.QUIZ_LLM_REASONING_EFFORT, c.QUIZ_LLM_MAX_TOKENS, c.QUIZ_LLM_MAX_CONCURRENCY),
                         ("vllm", "http://10.10.10.1:8010/v1", "aunjai-120b", "low", 6000, 1))

    def test_blank_values_mean_default(self):
        c = self._reload({k: "  " for k in self.KEYS})
        self.assertEqual((c.QUIZ_LLM_BACKEND, c.QUIZ_LLM_MODEL, c.QUIZ_LLM_MAX_TOKENS), ("vllm", "aunjai-120b", 6000))

    def test_concurrency_and_budget_clamped(self):
        c = self._reload({"QUIZ_LLM_MAX_CONCURRENCY": "8", "QUIZ_LLM_MAX_TOKENS": "999999", "QUIZ_LLM_BACKEND": "OpenClaw"})
        self.assertEqual((c.QUIZ_LLM_MAX_CONCURRENCY, c.QUIZ_LLM_MAX_TOKENS, c.QUIZ_LLM_BACKEND), (2, 16000, "openclaw"))
        c = self._reload({"QUIZ_LLM_MAX_CONCURRENCY": "abc", "QUIZ_LLM_MAX_TOKENS": "0"})
        self.assertEqual((c.QUIZ_LLM_MAX_CONCURRENCY, c.QUIZ_LLM_MAX_TOKENS), (1, 1000))


if __name__ == "__main__":
    unittest.main()
