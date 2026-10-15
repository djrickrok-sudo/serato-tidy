import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import serato_tidy as engine


class SeratoTidyApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Serato Tidy")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.music_folder = ""
        self.tracks = []
        self.duplicate_groups = []

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        ttk.Label(
            top,
            text="Serato Tidy",
            font=("Arial", 22, "bold")
        ).pack(side="left")

        ttk.Button(
            top,
            text="Choose Music Folder",
            command=self.choose_folder
        ).pack(side="right")

        self.folder_label = ttk.Label(
            self,
            text="No music folder selected",
            padding=(12, 0)
        )
        self.folder_label.pack(fill="x")

        self.status = ttk.Label(
            self,
            text="Choose your DJ music folder to begin.",
            padding=12
        )
        self.status.pack(fill="x")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=8)

        self.library_tab = ttk.Frame(self.tabs)
        self.duplicates_tab = ttk.Frame(self.tabs)
        self.organize_tab = ttk.Frame(self.tabs)

        self.tabs.add(self.library_tab, text="Library")
        self.tabs.add(self.duplicates_tab, text="Duplicates")
        self.tabs.add(self.organize_tab, text="Organize")

        self._build_library()
        self._build_duplicates()
        self._build_organize()

    def _build_library(self):
        info = ttk.Frame(self.library_tab, padding=10)
        info.pack(fill="x")

        self.library_stats = ttk.Label(
            info,
            text="No library scanned yet."
        )
        self.library_stats.pack(side="left")

        ttk.Button(
            info,
            text="Scan Library",
            command=self.scan_library
        ).pack(side="right")

        columns = ("artist", "title", "genre", "year", "format", "path")

        self.library_tree = ttk.Treeview(
            self.library_tab,
            columns=columns,
            show="headings"
        )

        widths = {
            "artist": 150,
            "title": 200,
            "genre": 120,
            "year": 70,
            "format": 70,
            "path": 380,
        }

        for col in columns:
            self.library_tree.heading(
                col,
                text=col.title()
            )
            self.library_tree.column(
                col,
                width=widths[col],
                anchor="w"
            )

        scroll = ttk.Scrollbar(
            self.library_tab,
            orient="vertical",
            command=self.library_tree.yview
        )

        self.library_tree.configure(
            yscrollcommand=scroll.set
        )

        scroll.pack(side="right", fill="y")
        self.library_tree.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10)
        )

    def _build_duplicates(self):
        controls = ttk.Frame(
            self.duplicates_tab,
            padding=10
        )
        controls.pack(fill="x")

        ttk.Button(
            controls,
            text="Find Duplicates",
            command=self.find_duplicates
        ).pack(side="left")

        ttk.Button(
            controls,
            text="Select All Duplicates",
            command=self.select_all_duplicates
        ).pack(side="left", padx=8)

        ttk.Button(
            controls,
            text="Move Selected to Quarantine",
            command=self.quarantine_selected
        ).pack(side="right")

        ttk.Label(
            self.duplicates_tab,
            text=(
                "The recommended copy is marked KEEP. "
                "Nothing is automatically deleted."
            ),
            padding=(10, 0, 10, 8)
        ).pack(fill="x")

        columns = (
            "action",
            "type",
            "artist",
            "title",
            "format",
            "bitrate",
            "path"
        )

        self.dupe_tree = ttk.Treeview(
            self.duplicates_tab,
            columns=columns,
            show="headings",
            selectmode="extended"
        )

        widths = {
            "action": 70,
            "type": 70,
            "artist": 140,
            "title": 190,
            "format": 70,
            "bitrate": 80,
            "path": 390,
        }

        for col in columns:
            self.dupe_tree.heading(
                col,
                text=col.title()
            )
            self.dupe_tree.column(
                col,
                width=widths[col],
                anchor="w"
            )

        self.dupe_tree.tag_configure(
            "keep",
            background="#d9f7d9"
        )

        scroll = ttk.Scrollbar(
            self.duplicates_tab,
            orient="vertical",
            command=self.dupe_tree.yview
        )

        self.dupe_tree.configure(
            yscrollcommand=scroll.set
        )

        scroll.pack(side="right", fill="y")
        self.dupe_tree.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

    def _build_organize(self):
        frame = ttk.Frame(
            self.organize_tab,
            padding=20
        )
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Organize Music",
            font=("Arial", 18, "bold")
        ).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(0, 15)
        )

        ttk.Label(
            frame,
            text="Folder layout:"
        ).grid(
            row=1,
            column=0,
            sticky="w"
        )

        self.layout = tk.StringVar(
            value="Genre / Artist"
        )

        layouts = [
            "Genre / Artist",
            "Year / Artist",
            "Decade / Genre / Artist",
            "Artist / Year",
            "Genre / Year / Artist",
        ]

        ttk.Combobox(
            frame,
            textvariable=self.layout,
            values=layouts,
            state="readonly",
            width=30
        ).grid(
            row=1,
            column=1,
            sticky="w",
            padx=10
        )

        ttk.Label(
            frame,
            text="Destination:"
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=15
        )

        self.destination = tk.StringVar()

        ttk.Entry(
            frame,
            textvariable=self.destination,
            width=55
        ).grid(
            row=2,
            column=1,
            sticky="ew",
            padx=10
        )

        ttk.Button(
            frame,
            text="Browse",
            command=self.choose_destination
        ).grid(
            row=2,
            column=2
        )

        self.copy_mode = tk.BooleanVar(
            value=True
        )

        ttk.Checkbutton(
            frame,
            text=(
                "Copy files instead of moving them "
                "(recommended for Serato)"
            ),
            variable=self.copy_mode
        ).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=10
        )

        ttk.Button(
            frame,
            text="Preview Organization",
            command=self.preview_organization
        ).grid(
            row=4,
            column=0,
            pady=15,
            sticky="w"
        )

        ttk.Button(
            frame,
            text="Apply Organization",
            command=self.apply_organization
        ).grid(
            row=4,
            column=1,
            pady=15,
            sticky="w"
        )

        self.preview_box = tk.Text(
            frame,
            height=20,
            wrap="none"
        )
        self.preview_box.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=10
        )

        frame.columnconfigure(
            1,
            weight=1
        )
        frame.rowconfigure(
            5,
            weight=1
        )

    def choose_folder(self):
        folder = filedialog.askdirectory(
            title="Choose your DJ music folder"
        )

        if not folder:
            return

        self.music_folder = folder
        self.folder_label.config(
            text=folder
        )

        self.scan_library()

    def scan_library(self):
        if not self.music_folder:
            self.choose_folder()
            return

        self.status.config(
            text="Scanning music library..."
        )
        self.update_idletasks()

        try:
            serato_paths = engine.load_serato_paths(
                self.music_folder
            )

            self.tracks = engine.scan(
                [self.music_folder],
                serato_paths
            )

        except Exception as exc:
            messagebox.showerror(
                "Scan Error",
                str(exc)
            )
            return

        for item in self.library_tree.get_children():
            self.library_tree.delete(item)

        missing_artist = 0
        missing_genre = 0
        missing_year = 0

        for track in self.tracks:
            if not track.get("artist"):
                missing_artist += 1
            if not track.get("genre"):
                missing_genre += 1
            if not track.get("year"):
                missing_year += 1

            self.library_tree.insert(
                "",
                "end",
                values=(
                    track.get("artist", ""),
                    track.get("title", ""),
                    track.get("genre", ""),
                    track.get("year", ""),
                    track.get("ext", ""),
                    track.get("path", ""),
                )
            )

        self.library_stats.config(
            text=(
                f"{len(self.tracks)} tracks | "
                f"Missing Artist: {missing_artist} | "
                f"Missing Genre: {missing_genre} | "
                f"Missing Year: {missing_year}"
            )
        )

        self.status.config(
            text=f"Scan complete: {len(self.tracks)} tracks."
        )

    def find_duplicates(self):
        if not self.tracks:
            self.scan_library()

        if not self.tracks:
            return

        self.status.config(
            text="Analyzing duplicate tracks..."
        )
        self.update_idletasks()

        try:
            self.duplicate_groups = (
                engine.find_duplicates(
                    self.tracks
                )
            )
        except Exception as exc:
            messagebox.showerror(
                "Duplicate Scan Error",
                str(exc)
            )
            return

        for item in self.dupe_tree.get_children():
            self.dupe_tree.delete(item)

        duplicate_count = 0

        for kind, group in self.duplicate_groups:
            for index, track in enumerate(group):

                keep = index == 0
                action = "KEEP" if keep else "DUPLICATE"

                if not keep:
                    duplicate_count += 1

                bitrate = track.get(
                    "bitrate",
                    0
                )

                bitrate_text = (
                    f"{bitrate // 1000} kbps"
                    if bitrate
                    else ""
                )

                self.dupe_tree.insert(
                    "",
                    "end",
                    values=(
                        action,
                        kind.upper(),
                        track.get("artist", ""),
                        track.get("title", ""),
                        track.get("ext", ""),
                        bitrate_text,
                        track.get("path", ""),
                    ),
                    tags=("keep",) if keep else ()
                )

        self.status.config(
            text=(
                f"Duplicate scan complete: "
                f"{duplicate_count} duplicate copies found."
            )
        )

        self.tabs.select(
            self.duplicates_tab
        )

    def select_all_duplicates(self):
        selections = []

        for item in self.dupe_tree.get_children():
            values = self.dupe_tree.item(
                item,
                "values"
            )

            if values and values[0] == "DUPLICATE":
                selections.append(item)

        self.dupe_tree.selection_set(
            selections
        )

    def quarantine_selected(self):
        selected = self.dupe_tree.selection()

        if not selected:
            messagebox.showinfo(
                "Serato Tidy",
                "Select one or more duplicate files first."
            )
            return

        paths = []

        for item in selected:
            values = self.dupe_tree.item(
                item,
                "values"
            )

            if not values:
                continue

            if values[0] == "KEEP":
                continue

            paths.append(values[-1])

        if not paths:
            messagebox.showinfo(
                "Serato Tidy",
                "The KEEP copies will never be quarantined."
            )
            return

        destination = filedialog.askdirectory(
            title="Choose a quarantine folder"
        )

        if not destination:
            return

        if not messagebox.askyesno(
            "Confirm Quarantine",
            (
                f"Move {len(paths)} selected duplicate "
                f"file(s) to:\n\n{destination}\n\n"
                "Nothing will be deleted."
            )
        ):
            return

        moved = 0

        try:
            for source in paths:
                source_path = Path(source)

                target = engine.unique_path(
                    Path(destination)
                    / source_path.name
                )

                Path(target).parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                shutil.move(
                    str(source_path),
                    str(target)
                )

                moved += 1

        except Exception as exc:
            messagebox.showerror(
                "Quarantine Error",
                str(exc)
            )
            return

        messagebox.showinfo(
            "Serato Tidy",
            f"{moved} duplicate file(s) moved safely."
        )

        self.scan_library()
        self.find_duplicates()

    def choose_destination(self):
        folder = filedialog.askdirectory(
            title="Choose organized music destination"
        )

        if folder:
            self.destination.set(folder)

    def template_for_layout(self):
        mapping = {
            "Genre / Artist":
                "{genre}/{artist}",

            "Year / Artist":
                "{year}/{artist}",

            "Decade / Genre / Artist":
                "{decade}/{genre}/{artist}",

            "Artist / Year":
                "{artist}/{year}",

            "Genre / Year / Artist":
                "{genre}/{year}/{artist}",
        }

        return mapping[
            self.layout.get()
        ]

    def planned_organization(self):
        if not self.tracks:
            self.scan_library()

        destination = self.destination.get()

        if not destination:
            raise ValueError(
                "Choose a destination folder first."
            )

        template = self.template_for_layout()

        planned = []

        for track in self.tracks:
            year = (
                track.get("year")
                or "Unknown Year"
            )

            decade = (
                f"{year[:3]}0s"
                if track.get("year")
                else "Unknown Decade"
            )

            fields = {
                "artist": engine.safe(
                    track.get("artist"),
                    "Unknown Artist"
                ),

                "genre": engine.safe(
                    track.get("genre"),
                    "Unknown Genre"
                ),

                "year": engine.safe(year),

                "decade": decade,
            }

            subfolder = template.format(
                **fields
            )

            artist = engine.safe(
                track.get("artist"),
                "Unknown Artist"
            )

            title = engine.safe(
                track.get("title"),
                "Unknown Title"
            )

            filename = (
                f"{artist} - {title}"
                f"{track.get('ext', '')}"
            )

            target = (
                Path(destination)
                / subfolder
                / filename
            )

            planned.append(
                (
                    Path(track["path"]),
                    target
                )
            )

        return planned

    def preview_organization(self):
        try:
            planned = self.planned_organization()
        except Exception as exc:
            messagebox.showerror(
                "Preview Error",
                str(exc)
            )
            return

        self.preview_box.delete(
            "1.0",
            "end"
        )

        for source, target in planned:
            self.preview_box.insert(
                "end",
                f"{source}\n  → {target}\n\n"
            )

        self.status.config(
            text=(
                f"Preview ready: "
                f"{len(planned)} files. "
                "No files have been changed."
            )
        )

    def apply_organization(self):
        try:
            planned = self.planned_organization()
        except Exception as exc:
            messagebox.showerror(
                "Organization Error",
                str(exc)
            )
            return

        mode = (
            "COPY"
            if self.copy_mode.get()
            else "MOVE"
        )

        if not messagebox.askyesno(
            "Confirm Organization",
            (
                f"{mode} {len(planned)} files?\n\n"
                "Copy mode is recommended because it "
                "keeps your existing Serato paths intact."
            )
        ):
            return

        processed = 0

        try:
            for source, target in planned:

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                final_target = engine.unique_path(
                    target
                )

                if self.copy_mode.get():
                    shutil.copy2(
                        str(source),
                        str(final_target)
                    )
                else:
                    shutil.move(
                        str(source),
                        str(final_target)
                    )

                processed += 1

        except Exception as exc:
            messagebox.showerror(
                "Organization Error",
                str(exc)
            )
            return

        messagebox.showinfo(
            "Serato Tidy",
            (
                f"Finished.\n\n"
                f"{processed} files processed."
            )
        )

        self.status.config(
            text=f"Organization complete: {processed} files."
        )


if __name__ == "__main__":
    app = SeratoTidyApp()
    app.mainloop()
