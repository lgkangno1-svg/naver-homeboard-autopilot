# -*- coding: utf-8 -*-
"""Windows desktop app for on-demand Naver blog draft creation.

The app intentionally exposes draft-save only. There is no live-publish button.
User data is stored under %LOCALAPPDATA%\NaverBlogWriter so replacing the EXE
will not erase API settings, Naver session state, or logs.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

# PyInstaller --windowed can set stdout/stderr to None. Several legacy modules
# call sys.stdout.reconfigure() during import, so give them a real text stream.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from dotenv import load_dotenv, set_key


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


RESOURCE_DIR = _resource_dir()
DATA_DIR = Path(
    os.getenv(
        "NAVER_BLOG_WRITER_DATA_DIR",
        str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "NaverBlogWriter"),
    )
).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "logs").mkdir(exist_ok=True)
(DATA_DIR / "downloads").mkdir(exist_ok=True)
(DATA_DIR / "images_pool").mkdir(exist_ok=True)

CONFIG_PATH = DATA_DIR / "config.json"
ENV_PATH = DATA_DIR / ".env"
STATE_PATH = DATA_DIR / "storage_state.json"

if not CONFIG_PATH.exists():
    source_cfg = RESOURCE_DIR / "config.json"
    if not source_cfg.exists():
        raise RuntimeError(f"config.json을 찾을 수 없습니다: {source_cfg}")
    shutil.copy2(source_cfg, CONFIG_PATH)

if not ENV_PATH.exists():
    ENV_PATH.write_text(
        "NAVER_BLOG_ID=issuemans\n"
        "OPENCODE_GO_API_KEY=\n"
        "OPENCODE_GO_MODEL=mimo-v2.5-pro\n"
        "OPENCODE_GO_REVIEW_MODEL=deepseek-v4-pro\n"
        "OPENCODE_GO_VISION_MODEL=deepseek-v4-flash-vision-exp\n"
        "OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1\n"
        "OPENCODE_GO_FALLBACK_MODELS=mimo-v2.5-pro,mimo-v2.5,deepseek-v4-pro,kimi-k2.7-code,kimi-k3\n"
        "BROWSER_CHANNEL=chrome\n"
        "HEADLESS=0\n",
        encoding="utf-8",
    )

load_dotenv(ENV_PATH, override=True)
os.chdir(DATA_DIR)

# Import the existing engine only after loading the desktop app environment.
import images as imgmod
import llm
import manual_login
import naver
import publish_guard
import quality_feedback
import writer_v2 as writer


KST_NAME = "Asia/Seoul"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _patch_runtime_paths() -> None:
    """Route stateful module paths away from the PyInstaller bundle directory."""
    base = str(DATA_DIR)
    writer.BASE = base
    imgmod.BASE = base

    naver.BASE = base
    naver.STATE = str(STATE_PATH)

    publish_guard.LOG = str(DATA_DIR / "logs" / "published.jsonl")

    quality_feedback.BASE = base
    quality_feedback.LOGDIR = str(DATA_DIR / "logs")
    quality_feedback.PUBLISH_LOG = str(DATA_DIR / "logs" / "published.jsonl")
    quality_feedback.LIVE_FEEDBACK = str(DATA_DIR / "logs" / "live_feedback.json")

    manual_login.BASE = base
    manual_login.STATE = str(STATE_PATH)


_patch_runtime_paths()


class QueueWriter:
    def __init__(self, q: queue.Queue[str]):
        self.q = q

    def write(self, text):
        if text:
            self.q.put(str(text))
        return len(str(text or ""))

    def flush(self):
        return None

    def reconfigure(self, **kwargs):
        return None


class BlogWriterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("네이버 블로그 글쓰기")
        self.root.geometry("860x720")
        self.root.minsize(760, 620)
        self.busy = False
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.style = ttk.Style()
        try:
            self.style.theme_use("vista")
        except Exception:
            pass

        self.topic_var = tk.StringVar()
        self.api_key_var = tk.StringVar(value=os.getenv("OPENCODE_GO_API_KEY", ""))
        self.blog_id_var = tk.StringVar(value=os.getenv("NAVER_BLOG_ID", "issuemans"))
        self.writer_model_var = tk.StringVar(value=os.getenv("OPENCODE_GO_MODEL", "mimo-v2.5-pro"))
        self.status_var = tk.StringVar(value="준비됨")
        self.api_status_var = tk.StringVar(value="API: 확인 필요")
        self.naver_status_var = tk.StringVar(value="네이버: 확인 필요")

        self._build_ui()
        sys.stdout = QueueWriter(self.log_queue)
        sys.stderr = QueueWriter(self.log_queue)
        self.root.after(120, self._drain_logs)
        self.root.after(500, self._initial_checks)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="네이버 블로그 글쓰기", font=("Malgun Gothic", 20, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            outer,
            text="원하는 주제를 입력하면 자료조사 → AI 작성/검수 → 이미지 수집 → 네이버 임시저장까지 자동으로 처리합니다.",
            font=("Malgun Gothic", 10),
        ).pack(anchor="w", pady=(4, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        write_tab = ttk.Frame(notebook, padding=14)
        settings_tab = ttk.Frame(notebook, padding=14)
        notebook.add(write_tab, text="글 작성")
        notebook.add(settings_tab, text="설정")

        status_frame = ttk.Frame(write_tab)
        status_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(status_frame, textvariable=self.api_status_var).pack(side="left")
        ttk.Label(status_frame, text="   |   ").pack(side="left")
        ttk.Label(status_frame, textvariable=self.naver_status_var).pack(side="left")

        ttk.Label(write_tab, text="글 주제", font=("Malgun Gothic", 11, "bold")).pack(anchor="w")
        topic = ttk.Entry(write_tab, textvariable=self.topic_var, font=("Malgun Gothic", 12))
        topic.pack(fill="x", pady=(5, 12), ipady=6)
        topic.focus_set()
        topic.bind("<Return>", lambda _e: self.start_draft())

        ttk.Label(write_tab, text="추가 요청 (선택)", font=("Malgun Gothic", 10, "bold")).pack(anchor="w")
        self.extra_text = tk.Text(write_tab, height=4, wrap="word", font=("Malgun Gothic", 10))
        self.extra_text.pack(fill="x", pady=(5, 12))
        self.extra_text.insert("1.0", "예: 초보자 기준으로 쉽게, 가격은 근거가 있을 때만, 광고처럼 쓰지 말기")

        action_row = ttk.Frame(write_tab)
        action_row.pack(fill="x", pady=(0, 10))
        self.write_btn = ttk.Button(action_row, text="글 작성 후 네이버 임시저장", command=self.start_draft)
        self.write_btn.pack(side="left", ipadx=14, ipady=7)
        ttk.Button(action_row, text="네이버 로그인", command=self.start_login).pack(side="left", padx=8, ipady=7)
        ttk.Button(action_row, text="상태 확인", command=self.start_checks).pack(side="left", ipady=7)

        self.progress = ttk.Progressbar(write_tab, mode="indeterminate")
        self.progress.pack(fill="x", pady=(2, 8))
        ttk.Label(write_tab, textvariable=self.status_var).pack(anchor="w", pady=(0, 5))

        self.log = ScrolledText(write_tab, height=17, wrap="word", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)

        # Settings tab
        form = ttk.Frame(settings_tab)
        form.pack(fill="x")

        ttk.Label(form, text="네이버 블로그 ID").grid(row=0, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.blog_id_var).grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=7)

        ttk.Label(form, text="OpenCode Go API Key").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.api_key_var, show="●").grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=7)

        ttk.Label(form, text="글쓰기 모델").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.writer_model_var).grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=7)
        form.columnconfigure(1, weight=1)

        settings_actions = ttk.Frame(settings_tab)
        settings_actions.pack(fill="x", pady=(14, 6))
        ttk.Button(settings_actions, text="설정 저장", command=self.save_settings).pack(side="left")
        ttk.Button(settings_actions, text="API 연결 테스트", command=self.start_api_probe).pack(side="left", padx=8)
        ttk.Button(settings_actions, text="데이터 폴더 열기", command=self.open_data_dir).pack(side="left")

        ttk.Separator(settings_tab).pack(fill="x", pady=15)
        ttk.Label(
            settings_tab,
            text=f"설정/로그/네이버 로그인 세션 저장 위치\n{DATA_DIR}\n\n이 앱에는 실발행 버튼이 없습니다. 생성된 글은 항상 네이버 임시저장으로만 저장됩니다.",
            justify="left",
        ).pack(anchor="w")

    def _drain_logs(self):
        chunks = []
        while True:
            try:
                chunks.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if chunks:
            self.log.configure(state="normal")
            self.log.insert("end", "".join(chunks))
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(120, self._drain_logs)

    def _set_busy(self, busy: bool, status: str = ""):
        self.busy = busy
        self.write_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        if status:
            self.status_var.set(status)

    def _run_background(self, label: str, fn, on_success=None):
        if self.busy:
            messagebox.showinfo("작업 진행 중", "현재 작업이 끝난 뒤 다시 실행해 주세요.")
            return
        self._set_busy(True, label)

        def worker():
            try:
                result = fn()
                self.root.after(0, lambda: self._task_done(True, result, on_success))
            except Exception as e:
                traceback.print_exc()
                self.root.after(0, lambda err=e: self._task_done(False, err, None))

        threading.Thread(target=worker, daemon=True).start()

    def _task_done(self, ok: bool, result, on_success):
        self._set_busy(False, "완료" if ok else "오류 발생")
        if ok:
            if on_success:
                on_success(result)
        else:
            messagebox.showerror("작업 실패", str(result))

    def _apply_settings_runtime(self):
        blog_id = self.blog_id_var.get().strip() or "issuemans"
        key = self.api_key_var.get().strip()
        model = self.writer_model_var.get().strip() or "mimo-v2.5-pro"

        os.environ["NAVER_BLOG_ID"] = blog_id
        os.environ["OPENCODE_GO_API_KEY"] = key
        os.environ["OPENCODE_GO_MODEL"] = model
        os.environ["BROWSER_CHANNEL"] = "chrome"
        os.environ["HEADLESS"] = "0"

        naver.BLOG_ID = blog_id
        llm.OPENCODE_GO_KEY = key
        llm.OPENCODE_GO_MODEL = model
        return blog_id, key, model

    def save_settings(self, quiet=False):
        blog_id, key, model = self._apply_settings_runtime()
        ENV_PATH.touch(exist_ok=True)
        set_key(str(ENV_PATH), "NAVER_BLOG_ID", blog_id, quote_mode="always")
        set_key(str(ENV_PATH), "OPENCODE_GO_API_KEY", key, quote_mode="always")
        set_key(str(ENV_PATH), "OPENCODE_GO_MODEL", model, quote_mode="always")
        set_key(str(ENV_PATH), "OPENCODE_GO_REVIEW_MODEL", os.getenv("OPENCODE_GO_REVIEW_MODEL", "deepseek-v4-pro"), quote_mode="always")
        set_key(str(ENV_PATH), "OPENCODE_GO_VISION_MODEL", os.getenv("OPENCODE_GO_VISION_MODEL", "deepseek-v4-flash-vision-exp"), quote_mode="always")
        set_key(str(ENV_PATH), "OPENCODE_GO_BASE_URL", os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"), quote_mode="always")
        set_key(str(ENV_PATH), "BROWSER_CHANNEL", "chrome", quote_mode="always")
        set_key(str(ENV_PATH), "HEADLESS", "0", quote_mode="always")
        if not quiet:
            messagebox.showinfo("저장 완료", "설정을 저장했습니다.")

    def _initial_checks(self):
        if self.api_key_var.get().strip():
            self.api_status_var.set("API: 키 설정됨")
        else:
            self.api_status_var.set("API: 키 입력 필요")
        self.naver_status_var.set("네이버: 로그인됨" if STATE_PATH.exists() else "네이버: 로그인 필요")

    def start_api_probe(self):
        self.save_settings(quiet=True)

        def task():
            print("\n=== OpenCode Go 연결 테스트 ===")
            code = llm.probe_go()
            if code != 0:
                raise RuntimeError("사용 가능한 OpenCode Go 모델을 찾지 못했습니다.")
            return True

        self._run_background(
            "API 연결 확인 중...",
            task,
            lambda _r: self.api_status_var.set("API: 연결됨"),
        )

    def start_login(self):
        self.save_settings(quiet=True)

        def task():
            print("\n=== 네이버 로그인 ===")
            code = manual_login.main(timeout_minutes=15)
            if code != 0 or not STATE_PATH.exists():
                raise RuntimeError("네이버 로그인 세션 저장에 실패했습니다.")
            return True

        def done(_r):
            self.naver_status_var.set("네이버: 로그인됨")
            messagebox.showinfo("로그인 완료", "네이버 로그인 세션을 저장했습니다.")

        self._run_background("브라우저에서 네이버 로그인 중...", task, done)

    def _check_naver(self):
        if not STATE_PATH.exists():
            return False
        pw = browser = None
        try:
            # Explicitly headless for the health check even though the desktop app uses headed Chrome.
            old = os.environ.get("HEADLESS")
            os.environ["HEADLESS"] = "1"
            pw, browser, ctx, page = naver.launch(headless=True)
            return bool(naver.is_logged_in(page))
        finally:
            os.environ["HEADLESS"] = old if old is not None else "0"
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass

    def start_checks(self):
        self.save_settings(quiet=True)

        def task():
            print("\n=== 상태 확인 ===")
            api_ok = bool(llm.OPENCODE_GO_KEY)
            naver_ok = self._check_naver()
            print("API 키:", "설정됨" if api_ok else "없음")
            print("네이버 로그인:", "정상" if naver_ok else "재로그인 필요")
            return api_ok, naver_ok

        def done(result):
            api_ok, naver_ok = result
            self.api_status_var.set("API: 키 설정됨" if api_ok else "API: 키 입력 필요")
            self.naver_status_var.set("네이버: 로그인됨" if naver_ok else "네이버: 재로그인 필요")

        self._run_background("상태 확인 중...", task, done)

    def _create_draft(self, topic: str, extra: str):
        self.save_settings(quiet=True)
        if not llm.OPENCODE_GO_KEY:
            raise RuntimeError("설정 탭에서 OpenCode Go API Key를 먼저 입력해 주세요.")
        if not STATE_PATH.exists():
            raise RuntimeError("네이버 로그인이 필요합니다. '네이버 로그인' 버튼을 먼저 눌러 주세요.")

        seed = topic.strip()
        if extra.strip() and not extra.strip().startswith("예:"):
            # Keep the search seed focused while still giving the planner a concise user direction.
            seed = f"{seed} - {extra.strip()[:160]}"

        print("\n" + "=" * 58)
        print("요청 주제:", topic)
        if extra.strip() and not extra.strip().startswith("예:"):
            print("추가 요청:", extra.strip())
        print("글 생성 시작...")

        post = writer.generate_post(seed_hint=seed)
        cid = publish_guard.content_id(post)
        print("제목:", post.get("title"))
        print("본문:", post.get("_chars"), "자")
        quality = post.get("_quality", {})
        if quality:
            print("품질 평균:", quality.get("editor_average"), "/ 출처:", quality.get("evidence_sources"))

        cfg = _load_config()
        n_img = min(len(post.get("image_queries", [])), cfg["format"]["image_max"])
        print("이미지 수집 중...")
        imgs = imgmod.fetch_images(post.get("image_queries", []), n_img)
        print("이미지", len(imgs), "장 확보")

        print("네이버 에디터에 입력 후 임시저장 중...")
        result = naver.write_post(post, imgs, mode="draft")
        ok = bool(result.get("ok"))

        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "title": post.get("title"),
            "mode": "draft",
            "slot_id": "desktop",
            "content_id": cid,
            "chars": post.get("_chars"),
            "images": len(imgs),
            "angle": post.get("_angle", {}).get("angle"),
            "keyword": post.get("_angle", {}).get("keyword"),
            "quality": quality,
            "source_domains": list(dict.fromkeys(
                x.get("domain") for x in post.get("_sources", []) if isinstance(x, dict) and x.get("domain")
            ))[:10],
            "status": "draft" if ok else "failed",
            "ok": ok,
        }
        with open(publish_guard.LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if not ok:
            raise RuntimeError("네이버 임시저장 결과를 확인하지 못했습니다.")
        print("임시저장 완료:", post.get("title"))
        return post

    def start_draft(self):
        topic = self.topic_var.get().strip()
        if not topic:
            messagebox.showwarning("주제 필요", "작성할 글의 주제를 입력해 주세요.")
            return
        extra = self.extra_text.get("1.0", "end").strip()

        def done(post):
            self.status_var.set("네이버 임시저장 완료")
            self.naver_status_var.set("네이버: 로그인됨")
            messagebox.showinfo(
                "임시저장 완료",
                f"네이버에 임시저장했습니다.\n\n제목: {post.get('title', '')}",
            )

        self._run_background(
            "자료조사와 글 작성을 시작합니다...",
            lambda: self._create_draft(topic, extra),
            done,
        )

    def start_checks(self):
        self.save_settings(quiet=True)

        def task():
            api_ok = bool(llm.OPENCODE_GO_KEY)
            print("\n=== 연결 상태 확인 ===")
            print("OpenCode Go API Key:", "설정됨" if api_ok else "없음")
            naver_ok = self._check_naver()
            print("네이버 로그인:", "정상" if naver_ok else "로그인 필요")
            return api_ok, naver_ok

        def done(result):
            api_ok, naver_ok = result
            self.api_status_var.set("API: 키 설정됨" if api_ok else "API: 키 입력 필요")
            self.naver_status_var.set("네이버: 로그인됨" if naver_ok else "네이버: 로그인 필요")

        self._run_background("연결 상태 확인 중...", task, done)

    def open_data_dir(self):
        try:
            os.startfile(DATA_DIR)  # type: ignore[attr-defined]
        except Exception:
            webbrowser.open(DATA_DIR.as_uri())


def main():
    root = tk.Tk()
    app = BlogWriterApp(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()
