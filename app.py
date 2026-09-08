"""
SIH 2026 Problem Statement Monitor
-----------------------------------
A small desktop app (Tkinter) that scrapes sih.gov.in/sih2026PS, lets you
pick which problem statements to keep an eye on, and auto-refreshes their
submitted-idea counts on a timer. Your watchlist is saved to disk so it's
still there next time you open the app.

Run:
    python3 app.py
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import scraper
import storage

DEFAULT_INTERVAL_SEC = 600  # 10 minutes


class SIHMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SIH 2026 Problem Statement Monitor")
        self.root.geometry("1180x640")

        self.all_ps: list[dict] = storage.load_cache()
        self.by_number: dict[str, dict] = {r["ps_number"]: r for r in self.all_ps}
        self.watchlist: set[str] = set(storage.load_watchlist())
        self.history: dict[str, int] = storage.load_history()

        self.result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.auto_refresh_on = tk.BooleanVar(value=True)
        self.interval_var = tk.IntVar(value=DEFAULT_INTERVAL_SEC // 60)  # shown in minutes
        self.status_var = tk.StringVar(value="Loading...")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_all_view())

        self._next_refresh_at = 0.0
        self._building = False

        self._build_ui()
        self.refresh_all_view()
        self.refresh_watch_view()

        # Kick off an immediate background fetch on startup, then start the
        # auto-refresh clock.
        self.trigger_fetch(manual=False)
        self.root.after(200, self._poll_queue)
        self.root.after(1000, self._tick)

    # ---------------------------------------------------------------- UI --
    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        # --- top bar -------------------------------------------------
        top = ttk.Frame(root, padding=(10, 8))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Search:").grid(row=0, column=0, padx=(0, 6))
        search_entry = ttk.Entry(top, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")

        ttk.Button(top, text="Refresh Now", command=lambda: self.trigger_fetch(manual=True)) \
            .grid(row=0, column=2, padx=6)

        ttk.Checkbutton(top, text="Auto-refresh every", variable=self.auto_refresh_on) \
            .grid(row=0, column=3, padx=(12, 4))
        interval_box = ttk.Spinbox(top, from_=1, to=180, width=4, textvariable=self.interval_var)
        interval_box.grid(row=0, column=4)
        ttk.Label(top, text="min").grid(row=0, column=5, padx=(4, 0))

        # --- left: all problem statements -----------------------------
        left = ttk.Frame(root, padding=(10, 0, 4, 10))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="All problem statements (select rows, then Add \u2192)",
                  font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))

        all_cols = ("ps", "title", "org", "ideas")
        self.all_tree = ttk.Treeview(left, columns=all_cols, show="headings", selectmode="extended")
        for col, label, width in (
            ("ps", "PS Number", 90),
            ("title", "Title", 420),
            ("org", "Organization", 220),
            ("ideas", "Ideas", 60),
        ):
            self.all_tree.heading(col, text=label)
            self.all_tree.column(col, width=width, anchor="w" if col != "ideas" else "center")
        self.all_tree.grid(row=1, column=0, sticky="nsew")
        all_scroll = ttk.Scrollbar(left, orient="vertical", command=self.all_tree.yview)
        self.all_tree.configure(yscrollcommand=all_scroll.set)
        all_scroll.grid(row=1, column=1, sticky="ns")
        self.all_tree.bind("<Double-1>", lambda e: self.add_selected_to_watchlist())

        ttk.Button(left, text="Add Selected to Monitor \u2192", command=self.add_selected_to_watchlist) \
            .grid(row=2, column=0, sticky="w", pady=6)

        # --- right: watchlist -------------------------------------------
        right = ttk.Frame(root, padding=(4, 0, 10, 10))
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Monitoring", font=("", 10, "bold")) \
            .grid(row=0, column=0, sticky="w", pady=(0, 4))

        watch_cols = ("ps", "title", "ideas", "delta", "updated")
        self.watch_tree = ttk.Treeview(right, columns=watch_cols, show="headings", selectmode="extended")
        for col, label, width in (
            ("ps", "PS Number", 85),
            ("title", "Title", 260),
            ("ideas", "Ideas", 55),
            ("delta", "\u0394", 45),
            ("updated", "Updated", 70),
        ):
            self.watch_tree.heading(col, text=label)
            self.watch_tree.column(col, width=width, anchor="w" if col in ("title",) else "center")
        self.watch_tree.grid(row=1, column=0, sticky="nsew")
        watch_scroll = ttk.Scrollbar(right, orient="vertical", command=self.watch_tree.yview)
        self.watch_tree.configure(yscrollcommand=watch_scroll.set)
        watch_scroll.grid(row=1, column=1, sticky="ns")
        self.watch_tree.tag_configure("up", foreground="#1a7f37")

        ttk.Button(right, text="\u2190 Remove Selected", command=self.remove_selected_from_watchlist) \
            .grid(row=2, column=0, sticky="w", pady=6)

        # --- status bar ---------------------------------------------------
        status = ttk.Frame(root, padding=(10, 4))
        status.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")

    # ------------------------------------------------------------ actions --
    def add_selected_to_watchlist(self):
        for item in self.all_tree.selection():
            ps_number = self.all_tree.set(item, "ps")
            self.watchlist.add(ps_number)
        storage.save_watchlist(self.watchlist)
        self.refresh_watch_view()

    def remove_selected_from_watchlist(self):
        for item in self.watch_tree.selection():
            ps_number = self.watch_tree.set(item, "ps")
            self.watchlist.discard(ps_number)
        storage.save_watchlist(self.watchlist)
        self.refresh_watch_view()

    # ------------------------------------------------------------- views --
    def refresh_all_view(self):
        query = self.search_var.get().strip().lower()
        self.all_tree.delete(*self.all_tree.get_children())
        for r in self.all_ps:
            haystack = f"{r['ps_number']} {r['title']} {r['org']}".lower()
            if query and query not in haystack:
                continue
            self.all_tree.insert(
                "", "end",
                values=(r["ps_number"], r["title"], r["org"],
                        r["ideas"] if r["ideas"] is not None else r["ideas_raw"]),
            )

    def refresh_watch_view(self):
        self.watch_tree.delete(*self.watch_tree.get_children())
        now = time.strftime("%H:%M:%S")
        for ps_number in sorted(self.watchlist):
            r = self.by_number.get(ps_number)
            if not r:
                self.watch_tree.insert("", "end", values=(ps_number, "(not loaded yet)", "-", "-", "-"))
                continue
            prev = self.history.get(ps_number)
            ideas = r["ideas"]
            delta = ""
            tag = ()
            if ideas is not None and prev is not None and ideas > prev:
                delta = f"+{ideas - prev}"
                tag = ("up",)
            self.watch_tree.insert(
                "", "end",
                values=(ps_number, r["title"], ideas if ideas is not None else r["ideas_raw"], delta, now),
                tags=tag,
            )

    # -------------------------------------------------------- fetch cycle --
    def trigger_fetch(self, manual: bool):
        if self._building:
            return
        self._building = True
        self.status_var.set("Refreshing from sih.gov.in ...")

        def worker():
            try:
                records = scraper.fetch_problem_statements()
                self.result_queue.put(("ok", records))
            except scraper.ScrapeError as e:
                self.result_queue.put(("error", str(e)))
            except Exception as e:  # noqa: BLE001
                self.result_queue.put(("error", f"Unexpected error: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._building = False
            if kind == "ok":
                self._apply_new_records(payload)
                self.status_var.set(f"Last refreshed {time.strftime('%H:%M:%S')} "
                                     f"\u00b7 {len(payload)} problem statements")
            else:
                self.status_var.set(f"Refresh failed: {payload}")
            self._next_refresh_at = time.time() + max(1, self.interval_var.get()) * 60
        self.root.after(200, self._poll_queue)

    def _apply_new_records(self, records: list[dict]):
        self.all_ps = records
        self.by_number = {r["ps_number"]: r for r in records}
        storage.save_cache(records)

        self.refresh_all_view()
        # refresh_watch_view() reads self.history, which at this point still
        # holds the *previous* snapshot - so the delta column compares old
        # vs. new correctly. Only after rendering do we roll history forward.
        self.refresh_watch_view()

        new_history = dict(self.history)
        for r in records:
            if r["ps_number"] in self.watchlist and r["ideas"] is not None:
                new_history[r["ps_number"]] = r["ideas"]
        self.history = new_history
        storage.save_history(self.history)

    def _tick(self):
        if self.auto_refresh_on.get() and not self._building:
            remaining = self._next_refresh_at - time.time()
            if remaining <= 0:
                self.trigger_fetch(manual=False)
            else:
                mins, secs = divmod(int(remaining), 60)
                base = self.status_var.get().split(" \u00b7 next")[0]
                self.status_var.set(f"{base} \u00b7 next refresh in {mins:02d}:{secs:02d}")
        self.root.after(1000, self._tick)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    SIHMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
