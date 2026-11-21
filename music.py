# -*- coding: utf-8 -*-
"""
🎵 音乐重命名工具
功能：读取音频标签（歌名/作者）→ 按规则批量重命名（默认 歌名 + 作者）
依赖：pip install mutagen
"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None


# ==================== 主题配色 ====================
BG        = "#15171c"
CARD      = "#1f232b"
CARD2     = "#262b35"
CARD2_HO  = "#333a47"
ROW_ALT   = "#232831"
FG        = "#e8eaf0"
SUB       = "#8b93a7"
ACCENT    = "#6c5ce7"
ACCENT_HO = "#5b4bd6"
GREEN     = "#22c55e"
GREEN_HO  = "#16a34a"
RED       = "#ef4444"
YELLOW    = "#f59e0b"
BORDER    = "#333a47"

FONT      = ("Microsoft YaHei UI", 10)
FONT_SM   = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")

AUDIO_EXTS = (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".wma", ".aac", ".ape")

TEMPLATES = {
    "歌名 + 作者": "{title} - {artist}",
    "作者 + 歌名": "{artist} - {title}",
    "仅歌名":     "{title}",
    "仅作者":     "{artist}",
    "歌名(作者)": "{title}({artist})",
}

ILLEGAL = r'[\\/:*?"<>|\r\n\t]'


# ==================== 工具函数 ====================
def read_tags(path):
    if MutagenFile is None:
        return None, None, None, "未安装 mutagen"
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return None, None, None, "无法解析标签"

        def first(key):
            v = audio.get(key)
            if not v:
                return None
            v = v[0] if isinstance(v, (list, tuple)) else v
            v = str(v).strip()
            return v or None

        return first("title"), first("artist"), first("album"), None
    except Exception as e:
        return None, None, None, f"读取失败: {e}"


def compose_name(template, title, artist, album):
    t, a, al = (title or ""), (artist or ""), (album or "")
    s = template.replace("{title}", t).replace("{artist}", a).replace("{album}", al)
    s = re.sub(r"[\(（\[【]\s*[\)）\]】]", "", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"^[\s\-_–—·|\.]+", "", s)
    s = re.sub(r"[\s\-_–—·|\.]+$", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def sanitize(name, max_len=120):
    name = re.sub(ILLEGAL, "_", name or "")
    name = re.sub(r"\s{2,}", " ", name).strip(" .")
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name


def collect_audio_files(root_dir, recursive):
    files = []
    if recursive:
        for dirpath, _, filenames in os.walk(root_dir):
            for fn in filenames:
                if fn.lower().endswith(AUDIO_EXTS):
                    files.append(os.path.join(dirpath, fn))
    else:
        for fn in os.listdir(root_dir):
            p = os.path.join(root_dir, fn)
            if os.path.isfile(p) and fn.lower().endswith(AUDIO_EXTS):
                files.append(p)
    files.sort()
    return files


def plan_targets(rows, out_dir):
    if not out_dir:
        for r in rows:
            r["new_name"] = f'{r["new_stem"]}{r["ext"]}'
            r["target"] = None
        return

    out_exists = os.path.isdir(out_dir)
    used = set()
    for r in rows:
        base, ext, src = r["new_stem"], r["ext"], r["src"]
        i = 0
        while True:
            name = f"{base}{ext}" if i == 0 else f"{base} ({i}){ext}"
            target = os.path.join(out_dir, name)
            same = (os.path.normcase(os.path.abspath(target)) ==
                    os.path.normcase(os.path.abspath(src)))
            conflict = (out_exists and os.path.exists(target) and not same) \
                       or (name.lower() in used)
            if not conflict:
                break
            i += 1
        used.add(name.lower())
        r["new_name"] = name
        r["target"] = target


# ==================== 自绘圆角按钮 ====================
class RoundButton(tk.Canvas):
    def __init__(self, parent, text, command, bg=ACCENT, fg="#ffffff",
                 hover=None, width=160, height=42, radius=10, font=FONT_BOLD):
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            parent_bg = BG
        super().__init__(parent, width=width, height=height,
                         bg=parent_bg, highlightthickness=0, bd=0)
        # 注意：这里避开了 self._w，改用 self._cw 防止覆盖 Tkinter 内部属性
        self._cw, self._ch, self._cr = width, height, radius
        self._bg, self._fg = bg, fg
        self._hover = hover or bg
        self._cur = bg
        self._text, self._font = text, font
        self._command = command
        self._state = "normal"
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.configure(cursor="hand2")

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self):
        self.delete("all")
        self._round_rect(1, 1, self._cw - 1, self._ch - 1, self._cr,
                         fill=self._cur, outline="")
        fg = self._fg if self._state == "normal" else SUB
        self.create_text(self._cw / 2, self._ch / 2, text=self._text,
                         fill=fg, font=self._font)

    def _on_enter(self, _):
        if self._state == "normal":
            self._cur = self._hover
            self._draw()

    def _on_leave(self, _):
        if self._state == "normal":
            self._cur = self._bg
            self._draw()

    def _on_click(self, _):
        if self._state == "normal" and self._command:
            self._command()

    def set_state(self, state):
        self._state = state
        if state == "normal":
            self._cur = self._bg
            self.configure(cursor="hand2")
        else:
            self._cur = CARD2
            self.configure(cursor="arrow")
        self._draw()


# ==================== 自绘圆角进度条 ====================
class RoundProgressBar(tk.Canvas):
    def __init__(self, parent, bg=CARD2, fg=ACCENT, height=18, radius=9):
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            parent_bg = BG
        super().__init__(parent, bg=parent_bg, height=height,
                         highlightthickness=0, bd=0)
        self._bg, self._fg = bg, fg
        self._ch, self._cr = height, radius
        self._value = 0
        self._max = 1
        self.bind("<Configure>", lambda e: self._draw())
        self.after(20, self._draw)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        r = h // 2
        self._round_rect(0, 0, w, h, r, fill=self._bg, outline="")
        ratio = max(0.0, min(1.0, self._value / self._max if self._max else 0))
        if ratio > 0:
            fw = max(h, int(w * ratio))
            self._round_rect(0, 0, fw, h, r, fill=self._fg, outline="")

    def set_max(self, m):
        self._max = max(1, int(m))
        self._draw()

    def set_value(self, v):
        self._value = max(0, int(v))
        self._draw()

    def reset(self):
        self._value = 0
        self._max = 1
        self._draw()


# ==================== 主界面 ====================
class MusicRenamerApp:
    def __init__(self, root):
        self.root = root
        self.rows = []
        self.busy = False

        self.in_var        = tk.StringVar()
        self.out_var       = tk.StringVar()
        self.pattern_var   = tk.StringVar(value="歌名 + 作者")
        self.recursive_var = tk.BooleanVar(value=False)
        self.action_var    = tk.StringVar(value="copy")
        self.status_var    = tk.StringVar(value="就绪")

        self._setup_style()
        self._build_ui()

        if MutagenFile is None:
            self.status_var.set("⚠ 未检测到 mutagen，请先运行：pip install mutagen")

    # ---------- 样式 ----------
    def _setup_style(self):
        root = self.root
        root.title("🎵 音乐重命名工具")
        root.geometry("1040x760")
        root.minsize(900, 640)
        root.configure(bg=BG)

        root.option_add("*TCombobox*Listbox.background", CARD2)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        root.option_add("*TCombobox*Listbox.font", FONT)

        st = ttk.Style(root)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        st.configure(".", background=BG, foreground=FG, font=FONT)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG, font=FONT)

        st.configure("TCheckbutton", background=CARD, foreground=FG, font=FONT_SM)
        st.map("TCheckbutton",
               background=[("active", CARD)], foreground=[("active", FG)])

        st.configure("TRadiobutton", background=CARD, foreground=FG, font=FONT_SM)
        st.map("TRadiobutton",
               background=[("active", CARD)], foreground=[("active", FG)])

        st.configure("TCombobox",
                     fieldbackground=CARD2, background=CARD2, foreground=FG,
                     arrowcolor=FG, bordercolor=BORDER, lightcolor=CARD2,
                     darkcolor=CARD2, selectbackground=CARD2,
                     selectforeground=FG, padding=4)
        st.map("TCombobox",
               fieldbackground=[("readonly", CARD2)],
               background=[("readonly", CARD2)],
               foreground=[("readonly", FG)],
               selectbackground=[("readonly", CARD2)],
               selectforeground=[("readonly", FG)])

        st.configure("Treeview",
                     background=CARD, fieldbackground=CARD, foreground=FG,
                     rowheight=30, borderwidth=0, font=FONT_SM)
        st.map("Treeview",
               background=[("selected", ACCENT)],
               foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading",
                     background=CARD2, foreground=SUB, font=FONT_SM,
                     relief="flat", borderwidth=0, padding=8)
        st.map("Treeview.Heading", background=[("active", CARD2_HO)])

    # ---------- 界面 ----------
    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        # 标题
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="🎵 音乐重命名工具", bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 17, "bold")).pack(side="left")
        tk.Label(head, text="读取音频标签 · 按规则批量重命名", bg=BG, fg=SUB,
                 font=FONT_SM).pack(side="left", padx=12, pady=(8, 0))

        # 路径卡片
        card = tk.Frame(outer, bg=CARD)
        card.pack(fill="x")
        ci = tk.Frame(card, bg=CARD)
        ci.pack(fill="x", padx=16, pady=14)
        ci.columnconfigure(1, weight=1)
        self._path_row(ci, 0, "输入文件夹", self.in_var, self.browse_in)
        self._path_row(ci, 1, "输出文件夹", self.out_var, self.browse_out)

        # 选项卡片
        opt = tk.Frame(outer, bg=CARD)
        opt.pack(fill="x", pady=(12, 0))
        oi = tk.Frame(opt, bg=CARD)
        oi.pack(fill="x", padx=16, pady=14)
        oi.columnconfigure(2, weight=1)

        tk.Label(oi, text="命名规则", bg=CARD, fg=SUB, font=FONT_SM,
                 width=9, anchor="w").grid(row=0, column=0, sticky="w")

        self.cbo = ttk.Combobox(oi, textvariable=self.pattern_var,
                                values=list(TEMPLATES.keys()),
                                state="readonly", width=20, font=FONT)
        self.cbo.grid(row=0, column=1, sticky="w")

        tk.Label(oi, text="  例如「歌名 + 作者」→ 晴天 - 周杰伦.mp3",
                 bg=CARD, fg=SUB, font=FONT_SM)\
            .grid(row=0, column=2, sticky="w", padx=(12, 0))

        opts_row = tk.Frame(oi, bg=CARD)
        opts_row.grid(row=1, column=0, columnspan=3, sticky="w", pady=(14, 0))
        ttk.Checkbutton(opts_row, text="包含子文件夹",
                        variable=self.recursive_var).pack(side="left")
        tk.Label(opts_row, text="处理方式：", bg=CARD, fg=SUB,
                 font=FONT_SM).pack(side="left", padx=(26, 4))
        ttk.Radiobutton(opts_row, text="复制到输出文件夹", value="copy",
                        variable=self.action_var).pack(side="left", padx=4)
        ttk.Radiobutton(opts_row, text="移动到输出文件夹", value="move",
                        variable=self.action_var).pack(side="left", padx=4)

        # 按钮栏 + 统计
        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(14, 10))

        self.btn_scan = RoundButton(bar, "🔍  扫描预览", self.on_scan,
                                    bg=ACCENT, hover=ACCENT_HO)
        self.btn_scan.pack(side="left")
        self.btn_run = RoundButton(bar, "▶  开始重命名", self.on_run,
                                   bg=GREEN, hover=GREEN_HO)
        self.btn_run.pack(side="left", padx=10)
        self.btn_clear = RoundButton(bar, "✕  清空列表", self.on_clear,
                                     bg=CARD2, hover=CARD2_HO, width=140)
        self.btn_clear.pack(side="left")

        # 统计块（右侧，从右往左：失败 / 成功 / 总数）
        self.stat_fail = self._stat_block(bar, "失败", RED)
        self.stat_ok = self._stat_block(bar, "成功", GREEN)
        self.stat_total = self._stat_block(bar, "总数", ACCENT, pad_right=False)

        # 列表
        listwrap = tk.Frame(outer, bg=CARD)
        listwrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(listwrap, columns=("orig", "new", "status"),
                                 show="headings", selectmode="browse")
        self.tree.heading("orig", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.heading("status", text="状态")
        self.tree.column("orig", width=400, anchor="w")
        self.tree.column("new", width=400, anchor="w")
        self.tree.column("status", width=160, anchor="center")

        self.tree.tag_configure("even", background=CARD)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("ok", foreground=FG)
        self.tree.tag_configure("warn", foreground=YELLOW)
        self.tree.tag_configure("err", foreground=RED)
        self.tree.tag_configure("done", foreground=GREEN)

        vsb = ttk.Scrollbar(listwrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        vsb.pack(side="right", fill="y")

        # 进度栏
        progress_row = tk.Frame(outer, bg=BG)
        progress_row.pack(fill="x", pady=(12, 0))

        self.pbar = RoundProgressBar(progress_row, bg=CARD2, fg=ACCENT, height=18)
        self.pbar.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self.pct_label = tk.Label(progress_row, text="0%", bg=BG, fg=FG,
                                  font=("Microsoft YaHei UI", 10, "bold"),
                                  width=5, anchor="e")
        self.pct_label.pack(side="left")

        tk.Label(progress_row, textvariable=self.status_var, bg=BG, fg=SUB,
                 font=FONT_SM).pack(side="left", padx=(16, 0))

    def _path_row(self, parent, row, label, var, cmd):
        tk.Label(parent, text=label, bg=CARD, fg=SUB, font=FONT_SM,
                 width=9, anchor="w").grid(row=row, column=0, sticky="w", pady=6)
        e = tk.Entry(parent, textvariable=var, bg=CARD2, fg=FG,
                     insertbackground=FG, relief="flat", font=FONT,
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
        e.grid(row=row, column=1, sticky="ew", ipady=6, pady=6)
        RoundButton(parent, "浏览…", cmd, bg=CARD2, hover=CARD2_HO,
                    width=82, height=34, radius=8, font=FONT)\
            .grid(row=row, column=2, padx=(10, 0), pady=6)

    def _stat_block(self, parent, title, color, pad_right=True):
        box = tk.Frame(parent, bg=BG)
        box.pack(side="right", padx=((20 if pad_right else 0), 0))
        val = tk.Label(box, text="0", bg=BG, fg=color,
                       font=("Microsoft YaHei UI", 15, "bold"))
        val.pack(side="right")
        tk.Label(box, text=f"{title} ", bg=BG, fg=SUB, font=FONT_SM)\
            .pack(side="right", pady=(6, 0))
        return val

    # ---------- 事件 ----------
    def browse_in(self):
        d = filedialog.askdirectory(title="选择输入文件夹")
        if d:
            self.in_var.set(d)
            if not self.out_var.get().strip():
                self.out_var.set(os.path.join(d, "renamed"))

    def browse_out(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.out_var.set(d)

    def get_template(self):
        return TEMPLATES.get(self.pattern_var.get(), "{title} - {artist}")

    def set_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        for b in (self.btn_scan, self.btn_run, self.btn_clear):
            b.set_state(state)

    def _reset_progress(self):
        self.pbar.reset()
        self.pct_label.config(text="0%")

    def _update_stats(self, total=None, ok=None, fail=None):
        if total is not None:
            self.stat_total.config(text=str(total))
        if ok is not None:
            self.stat_ok.config(text=str(ok))
        if fail is not None:
            self.stat_fail.config(text=str(fail))

    def _set_progress(self, cur, total, prefix):
        self.pbar.set_max(total)
        self.pbar.set_value(cur)
        pct = int(cur / total * 100) if total else 0
        self.pct_label.config(text=f"{pct}%")
        self.status_var.set(f"{prefix} {cur}/{total}")

    def on_clear(self):
        if self.busy:
            return
        self.rows = []
        self.tree.delete(*self.tree.get_children())
        self._reset_progress()
        self._update_stats(total=0, ok=0, fail=0)
        self.status_var.set("就绪")

    # ---------- 扫描 ----------
    def on_scan(self):
        if self.busy:
            return
        if MutagenFile is None:
            messagebox.showerror("缺少依赖",
                                 "未安装 mutagen 库。\n\n请在命令行运行：\npip install mutagen")
            return
        in_dir = self.in_var.get().strip()
        if not os.path.isdir(in_dir):
            messagebox.showwarning("提示", "请选择有效的输入文件夹")
            return

        self.busy = True
        self.set_buttons(False)
        self.status_var.set("正在扫描…")
        self._reset_progress()
        self._update_stats(total=0, ok=0, fail=0)
        self.tree.delete(*self.tree.get_children())
        self.rows = []

        template = self.get_template()
        recursive = self.recursive_var.get()
        threading.Thread(target=self._scan_worker,
                         args=(in_dir, recursive, template), daemon=True).start()

    def _scan_worker(self, in_dir, recursive, template):
        try:
            files = collect_audio_files(in_dir, recursive)
            total = len(files)
            self.root.after(0, self._set_progress, 0, total, "正在扫描…")

            rows = []
            for idx, p in enumerate(files, 1):
                title, artist, album, err = read_tags(p)
                stem, ext = os.path.splitext(os.path.basename(p))
                new_stem, status = stem, "就绪"

                if err:
                    status = err
                elif not title and not artist:
                    status = "无标签信息，保持原名"
                else:
                    built = sanitize(compose_name(template, title, artist, album))
                    if built:
                        new_stem = built
                    else:
                        status = "标签为空，保持原名"

                rows.append({
                    "src": p, "ext": ext,
                    "new_stem": new_stem,
                    "new_name": new_stem + ext,
                    "target": None, "status": status, "iid": None,
                })

                if idx % 3 == 0 or idx == total:
                    self.root.after(0, self._set_progress, idx, total, "正在扫描…")

            self.root.after(0, self._scan_done, rows)
        except Exception as e:
            self.root.after(0, self._scan_fail, str(e))

    def _scan_fail(self, msg):
        self.busy = False
        self.set_buttons(True)
        self.status_var.set("扫描失败")
        messagebox.showerror("错误", f"扫描时出错：\n{msg}")

    def _scan_done(self, rows):
        self.busy = False
        self.set_buttons(True)

        out_dir = self.out_var.get().strip()
        if rows and out_dir:
            plan_targets(rows, out_dir)

        self.rows = rows
        self.tree.delete(*self.tree.get_children())

        for i, r in enumerate(rows):
            orig_name = os.path.basename(r["src"])
            new_name = r["new_name"]
            status = r["status"]
            tag = "ok" if status == "就绪" else "warn"

            if status == "就绪" and r.get("target"):
                if os.path.normcase(os.path.abspath(r["target"])) == \
                   os.path.normcase(os.path.abspath(r["src"])):
                    status, tag = "无需修改", "warn"

            zebra = "even" if i % 2 == 0 else "odd"
            iid = self.tree.insert("", "end",
                                   values=(orig_name, new_name, status),
                                   tags=(tag, zebra))
            r["iid"] = iid

        self.pbar.set_max(max(1, len(rows)))
        self.pbar.set_value(len(rows))
        self.pct_label.config(text="100%")
        self._update_stats(total=len(rows), ok=0, fail=0)
        self.status_var.set(f"共找到 {len(rows)} 个音频文件，点击「开始重命名」执行")

    # ---------- 执行 ----------
    def on_run(self):
        if self.busy:
            return
        if not self.rows:
            messagebox.showinfo("提示", "请先点击「扫描预览」")
            return
        out_dir = self.out_var.get().strip()
        if not out_dir:
            messagebox.showwarning("提示", "请选择输出文件夹")
            return

        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出文件夹：\n{e}")
            return

        plan_targets(self.rows, out_dir)

        todo = []
        for r in self.rows:
            if not r.get("target"):
                continue
            same = (os.path.normcase(os.path.abspath(r["target"])) ==
                    os.path.normcase(os.path.abspath(r["src"])))
            if same:
                self._update_row(r["iid"], "无需修改", "warn")
            else:
                todo.append(r)

        if not todo:
            messagebox.showinfo("提示", "没有需要处理的文件")
            return

        if not messagebox.askyesno(
                "确认",
                f"即将处理 {len(todo)} 个文件\n"
                f"方式：{'移动' if self.action_var.get() == 'move' else '复制'}\n"
                f"输出：{out_dir}\n\n是否继续？"):
            return

        self.busy = True
        self.set_buttons(False)
        self._reset_progress()
        self._update_stats(ok=0, fail=0)
        self.status_var.set("正在处理…")

        move = (self.action_var.get() == "move")
        threading.Thread(target=self._run_worker,
                         args=(todo, move), daemon=True).start()

    def _run_worker(self, todo, move):
        ok = fail = 0
        total = len(todo)
        for idx, r in enumerate(todo, 1):
            src, dst = r["src"], r["target"]
            try:
                if not os.path.exists(src):
                    raise FileNotFoundError("源文件不存在")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if move:
                    shutil.move(src, dst)
                else:
                    shutil.copy2(src, dst)
                ok += 1
                self.root.after(0, self._update_row, r["iid"], "✔ 完成", "done")
            except Exception as e:
                fail += 1
                self.root.after(0, self._update_row, r["iid"], f"✘ {e}", "err")

            if idx % 3 == 0 or idx == total:
                self.root.after(0, self._run_progress, idx, total, ok, fail)

        self.root.after(0, self._run_done, ok, fail)

    def _run_progress(self, cur, total, ok, fail):
        self._set_progress(cur, total, "处理中…")
        self._update_stats(ok=ok, fail=fail)

    def _update_row(self, iid, status, tag):
        if not iid:
            return
        try:
            vals = list(self.tree.item(iid, "values"))
            vals[2] = status
            old_tags = list(self.tree.item(iid, "tags")) or []
            zebra = "even"
            for t in old_tags:
                if t in ("even", "odd"):
                    zebra = t
                    break
            self.tree.item(iid, values=vals, tags=(tag, zebra))
        except Exception:
            pass

    def _run_done(self, ok, fail):
        self.busy = False
        self.set_buttons(True)
        self.pct_label.config(text="100%")
        self.status_var.set(f"完成：成功 {ok} 个，失败 {fail} 个")
        if fail:
            messagebox.showwarning("处理完成",
                                   f"成功：{ok} 个\n失败：{fail} 个\n\n"
                                   f"失败项见列表中的红色记录。")
        else:
            messagebox.showinfo("处理完成", f"全部完成！\n成功重命名 {ok} 个文件。")


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    MusicRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()