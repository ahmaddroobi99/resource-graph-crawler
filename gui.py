"""Desktop GUI for the Visualping crawler.

A thin Tkinter front-end over the same engine the CLI (``main.py``) drives.
It lets you configure a run, watch live progress and log output, and browse the
recovered ``VISUALPING{...}`` passwords without touching the command line.

Run with:  python gui.py     (Tkinter ships with CPython; no extra installs)
"""

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit

import config
from crawler import fetcher as fetcher_mod
from crawler import url_utils as url_utils_mod
from crawler.engine import Crawler
from crawler.fetcher import configure_proxy


# --- log plumbing ----------------------------------------------------------

class QueueLogHandler(logging.Handler):
    """Forward log records to a thread-safe queue drained by the Tk main loop."""

    def __init__(self, log_queue: "queue.Queue[tuple[str, str]]") -> None:
        super().__init__()
        self._queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put(("log", self.format(record)))
        except Exception:  # never let logging crash the crawl
            pass


class CrawlerGUI(ttk.Frame):
    POLL_MS = 120

    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.grid(row=0, column=0, sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.msg_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.crawler: Crawler | None = None
        self.started_at = 0.0

        self._build_widgets()
        self.after(self.POLL_MS, self._drain_queue)
        master.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout -------------------------------------------------------------

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="Visualping Crawler",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(head, foreground="#666",
                  text="Authenticated BFS crawl \u2192 recover every "
                       "VISUALPING{...} password").pack(anchor="w")

        self._build_settings()
        self._build_controls()
        self._build_body()
        self._build_statusbar()

    def _build_settings(self) -> None:
        box = ttk.LabelFrame(self, text="Settings", padding=10)
        box.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        for col in (1, 3):
            box.columnconfigure(col, weight=1)

        self.var_url = tk.StringVar(value=config.BASE_URL)
        self.var_user = tk.StringVar(value=config.USERNAME)
        self.var_pass = tk.StringVar(value=config.PASSWORD)
        self.var_proxy = tk.StringVar(value=config.PROXY or "")
        self.var_max = tk.StringVar(value=str(config.MAX_PAGES))
        self.var_workers = tk.StringVar(value="4")
        self.var_verbose = tk.BooleanVar(value=False)

        def row(r, label, var, col=0, show=None, width=28):
            ttk.Label(box, text=label).grid(row=r, column=col, sticky="w",
                                            padx=(0, 6), pady=3)
            entry = ttk.Entry(box, textvariable=var, show=show, width=width)
            entry.grid(row=r, column=col + 1, sticky="ew", padx=(0, 14), pady=3)
            return entry

        row(0, "Base URL", self.var_url, col=0, width=40)
        row(0, "Proxy", self.var_proxy, col=2, width=26)
        row(1, "Username", self.var_user, col=0)
        row(1, "Password", self.var_pass, col=2, show="\u2022")
        row(2, "Max pages", self.var_max, col=0, width=10)
        row(2, "Workers", self.var_workers, col=2, width=10)

        ttk.Checkbutton(box, text="Verbose logging",
                        variable=self.var_verbose).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(box, foreground="#888", font=("Segoe UI", 8),
                  text="Proxy reaches the DE geo-locked page, e.g. "
                       "socks5h://127.0.0.1:1080").grid(
            row=3, column=2, columnspan=2, sticky="w", pady=(6, 0))

    def _build_controls(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.btn_run = ttk.Button(bar, text="\u25B6  Run crawl", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="\u25A0  Stop", command=self.stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        self.btn_save = ttk.Button(bar, text="Save passwords\u2026",
                                   command=self.save_results, state="disabled")
        self.btn_save.pack(side="left", padx=(8, 0))
        self.btn_clear = ttk.Button(bar, text="Clear log", command=self.clear_log)
        self.btn_clear.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side="right")

    def _build_body(self) -> None:
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=3, column=0, sticky="nsew")

        # left: live log
        left = ttk.LabelFrame(pane, text="Activity log", padding=6)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.log = tk.Text(left, height=18, width=60, wrap="none",
                           background="#1e1e1e", foreground="#d4d4d4",
                           insertbackground="#d4d4d4", font=("Consolas", 9),
                           state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_sb = ttk.Scrollbar(left, orient="vertical", command=self.log.yview)
        log_sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_sb.set)
        pane.add(left, weight=3)

        # right: results
        right = ttk.LabelFrame(pane, text="Passwords found", padding=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.count_label = ttk.Label(right, text="0 found",
                                     font=("Segoe UI", 10, "bold"))
        self.count_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.results_list = tk.Listbox(right, font=("Consolas", 10),
                                       activestyle="none", height=12)
        self.results_list.grid(row=1, column=0, columnspan=2, sticky="nsew")
        res_sb = ttk.Scrollbar(right, orient="vertical",
                               command=self.results_list.yview)
        res_sb.grid(row=1, column=2, sticky="ns")
        self.results_list.configure(yscrollcommand=res_sb.set)

        ttk.Label(right, text="Likely genuine leaks (ADMIN_PASSWORD / FIXME):",
                  foreground="#a33").grid(row=2, column=0, columnspan=3,
                                          sticky="w", pady=(8, 2))
        self.leaks_list = tk.Listbox(right, font=("Consolas", 10),
                                     activestyle="none", height=4,
                                     foreground="#a33")
        self.leaks_list.grid(row=3, column=0, columnspan=3, sticky="ew")
        pane.add(right, weight=2)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.stat_vars = {name: tk.StringVar(value="\u2013")
                          for name in ("Visited", "Frontier", "Results",
                                       "Failed", "Elapsed")}
        for i, (name, var) in enumerate(self.stat_vars.items()):
            cell = ttk.Frame(bar)
            cell.grid(row=0, column=i, padx=(0, 18))
            ttk.Label(cell, text=name, foreground="#888",
                      font=("Segoe UI", 8)).pack(anchor="w")
            ttk.Label(cell, textvariable=var,
                      font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self.status, foreground="#666").grid(
            row=0, column=len(self.stat_vars), sticky="e")
        bar.columnconfigure(len(self.stat_vars), weight=1)

    # -- run lifecycle ------------------------------------------------------

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self._collect_settings()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.clear_log()
        self.results_list.delete(0, "end")
        self.leaks_list.delete(0, "end")
        self.count_label.config(text="0 found")
        self.btn_save.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress.start(12)
        self.status.set("Crawling\u2026")
        self.stop_event = threading.Event()
        self.started_at = time.monotonic()

        self.worker = threading.Thread(target=self._run_worker, args=(settings,),
                                       daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.status.set("Stopping after current batch\u2026")
        self.btn_stop.config(state="disabled")

    def _collect_settings(self) -> dict:
        url = self.var_url.get().strip()
        if not url:
            raise ValueError("Base URL is required.")
        host = urlsplit(url).hostname
        if not host:
            raise ValueError("Base URL must include a host, e.g. http://host/")
        try:
            max_pages = int(self.var_max.get())
            workers = int(self.var_workers.get())
        except ValueError:
            raise ValueError("Max pages and Workers must be integers.")
        if max_pages < 1 or workers < 1:
            raise ValueError("Max pages and Workers must be at least 1.")
        return {
            "url": url,
            "host": host,
            "username": self.var_user.get(),
            "password": self.var_pass.get(),
            "proxy": self.var_proxy.get().strip() or None,
            "max_pages": max_pages,
            "workers": workers,
            "verbose": self.var_verbose.get(),
        }

    def _run_worker(self, s: dict) -> None:
        handler = QueueLogHandler(self.msg_queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        pkg_logger = logging.getLogger("crawler")
        pkg_logger.addHandler(handler)
        pkg_logger.setLevel(logging.INFO if s["verbose"] else logging.WARNING)
        # Progress lines (engine INFO) are useful even when not verbose.
        logging.getLogger("crawler.engine").setLevel(logging.INFO)

        # Point the already-imported module globals at the GUI's settings so a
        # different host/credentials/proxy take effect without editing config.
        fetcher_mod.USERNAME = s["username"]
        fetcher_mod.PASSWORD = s["password"]
        url_utils_mod.ALLOWED_HOST = s["host"]
        configure_proxy(s["proxy"])

        self.msg_queue.put(("log", f"Starting crawl at {s['url']} "
                                   f"(host={s['host']}, workers={s['workers']}, "
                                   f"max_pages={s['max_pages']})"))
        try:
            self.crawler = Crawler(base_url=s["url"], verbose=s["verbose"],
                                   stop_event=self.stop_event)
            self.crawler.run(max_pages=s["max_pages"], workers=s["workers"])
            elapsed = time.monotonic() - self.started_at
            self.msg_queue.put(("done", {
                "passwords": self.crawler.results.get_all(),
                "leaks": sorted(self.crawler.credential_leaks),
                "stats": self.crawler.get_stats(),
                "stopped": self.stop_event.is_set(),
                "elapsed": elapsed,
            }))
        except Exception as exc:  # surface any failure in the UI
            logging.getLogger("crawler").exception("Crawl failed")
            self.msg_queue.put(("error", str(exc)))
        finally:
            pkg_logger.removeHandler(handler)

    # -- queue draining / live updates -------------------------------------

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    self._on_done(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._on_error(str(payload))
        except queue.Empty:
            pass

        if self.crawler is not None and self.worker and self.worker.is_alive():
            self._refresh_live_stats()
        self.after(self.POLL_MS, self._drain_queue)

    def _refresh_live_stats(self) -> None:
        c = self.crawler
        assert c is not None
        self.stat_vars["Visited"].set(str(len(c.visited)))
        self.stat_vars["Frontier"].set(str(len(c.frontier)))
        self.stat_vars["Results"].set(str(len(c.results)))
        self.stat_vars["Failed"].set(str(len(c.failed)))
        self.stat_vars["Elapsed"].set(f"{time.monotonic() - self.started_at:.0f}s")

    def _on_done(self, payload: dict) -> None:
        self.progress.stop()
        stats = payload["stats"]
        self.stat_vars["Visited"].set(str(stats["pages_visited"]))
        self.stat_vars["Frontier"].set(str(stats["frontier_remaining"]))
        self.stat_vars["Results"].set(str(stats["passwords_found"]))
        self.stat_vars["Failed"].set(str(stats["failed_fetches"]))
        self.stat_vars["Elapsed"].set(f"{payload['elapsed']:.1f}s")

        passwords = payload["passwords"]
        self.results_list.delete(0, "end")
        for pw in passwords:
            self.results_list.insert("end", pw)
        self.count_label.config(text=f"{len(passwords)} found")

        self.leaks_list.delete(0, "end")
        for leak in payload["leaks"]:
            self.leaks_list.insert("end", leak)

        complete = stats["complete"]
        if payload["stopped"]:
            verdict = "Stopped by user before completion."
        elif complete:
            verdict = ("Complete: frontier empty, no failures, every discovered "
                       "URL visited.")
        else:
            verdict = ("Incomplete: stopped before proving completeness "
                       "(max-pages hit or failed fetches).")
        self._append_log("\n=== Done ===")
        self._append_log(f"Passwords found: {len(passwords)}")
        self._append_log(verdict)
        self.status.set(verdict)

        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_save.config(state="normal" if passwords else "disabled")
        self._last_passwords = passwords

    def _on_error(self, message: str) -> None:
        self.progress.stop()
        self.status.set(f"Error: {message}")
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        messagebox.showerror("Crawl failed", message)

    # -- misc ---------------------------------------------------------------

    def _append_log(self, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def clear_log(self) -> None:
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def save_results(self) -> None:
        passwords = getattr(self, "_last_passwords", [])
        if not passwords:
            return
        path = filedialog.asksaveasfilename(
            title="Save passwords", defaultextension=".txt",
            initialfile="passwords.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(passwords))
            if passwords:
                fh.write("\n")
        self.status.set(f"Saved {len(passwords)} passwords to {path}")

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
        self.master.destroy()


def main() -> int:
    root = tk.Tk()
    root.title("Visualping Crawler")
    root.geometry("980x680")
    root.minsize(820, 560)
    try:
        ttk.Style().theme_use("vista")  # native look on Windows; ignored elsewhere
    except tk.TclError:
        pass
    CrawlerGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
