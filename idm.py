import os
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any
from urllib.parse import urlparse

import imageio_ffmpeg
import yt_dlp
from yt_dlp.utils import DownloadCancelled

VIDEO_FILE_EXTENSIONS = {
	"3gp", "avi", "flv", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "webm", "wmv"
}


class VideoDownloaderApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("Video İndirici")
		self.root.geometry("760x640")
		self.root.minsize(680, 580)

		self.url_var = tk.StringVar()
		self.folder_var = tk.StringVar(
			value=os.path.join(os.path.expanduser("~"), "Downloads")
		)
		self.quality_var = tk.StringVar()
		self.status_var = tk.StringVar(value="Video bağlantısını yapıştırıp çözünürlükleri listeleyin.")
		self.inspected_url = ""
		self.quality_by_label: dict[str, int | None] = {}
		self.download_cancel_event = threading.Event()
		self.ffmpeg_cancel_event = threading.Event()
		self.ffmpeg_process: Any = None
		self.ffmpeg_busy = False

		self._build_ui()

	def _build_ui(self) -> None:
		self.root.configure(bg="#f3f5f4")
		style = ttk.Style(self.root)
		style.theme_use("clam")
		style.configure("TFrame", background="#f3f5f4")
		style.configure("TLabel", background="#f3f5f4", foreground="#26332e", font=("Segoe UI", 10))
		style.configure("Heading.TLabel", font=("Segoe UI", 19, "bold"), foreground="#173b32")
		style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
		style.configure("Accent.TButton", background="#19735a", foreground="white")
		style.map("Accent.TButton", background=[("active", "#135b47"), ("disabled", "#a9b8b2")])
		style.configure("TEntry", padding=8)
		style.configure("TCombobox", padding=7)
		style.configure("Horizontal.TProgressbar", troughcolor="#dce5e0", background="#19735a")

		content = ttk.Frame(self.root, padding=22)
		content.pack(fill="both", expand=True)

		ttk.Label(content, text="Video Araçları", style="Heading.TLabel").pack(anchor="w")
		self.notebook = ttk.Notebook(content)
		self.notebook.pack(fill="both", expand=True, pady=(16, 0))

		self.download_tab = ttk.Frame(self.notebook, padding=20)
		self.convert_tab = ttk.Frame(self.notebook, padding=20)
		self.compress_tab = ttk.Frame(self.notebook, padding=20)
		self.notebook.add(self.download_tab, text="İndir")
		self.notebook.add(self.convert_tab, text="Dönüştür")
		self.notebook.add(self.compress_tab, text="Sıkıştır")
		self._build_download_tab(self.download_tab)
		self._build_converter_tab(self.convert_tab)
		self._build_compress_tab(self.compress_tab)

	def _build_download_tab(self, content: ttk.Frame) -> None:
		ttk.Label(content, text="Bağlantıyı çözümleyin, kaliteyi seçin ve indirin.").pack(
			anchor="w", pady=(0, 18)
		)
		ttk.Label(content, text="Video bağlantısı").pack(anchor="w", pady=(0, 6))
		url_row = ttk.Frame(content)
		url_row.pack(fill="x")
		self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
		self.url_entry.pack(side="left", fill="x", expand=True)
		self.inspect_button = ttk.Button(url_row, text="Kaliteleri Bul", command=self.inspect_video)
		self.inspect_button.pack(side="left", padx=(8, 0))

		ttk.Label(content, text="Çözünürlük").pack(anchor="w", pady=(16, 6))
		self.quality_box = ttk.Combobox(
			content, textvariable=self.quality_var, state="readonly", values=()
		)
		self.quality_box.pack(fill="x")

		ttk.Label(content, text="Kayıt klasörü").pack(anchor="w", pady=(16, 6))
		folder_row = ttk.Frame(content)
		folder_row.pack(fill="x")
		ttk.Entry(folder_row, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
		ttk.Button(folder_row, text="Gözat", command=self.choose_folder).pack(side="left", padx=(8, 0))

		self.progress = ttk.Progressbar(content, mode="determinate", maximum=100)
		self.progress.pack(fill="x", pady=(22, 10))
		ttk.Label(content, textvariable=self.status_var, wraplength=590).pack(anchor="w")

		action_row = ttk.Frame(content)
		action_row.pack(fill="x", pady=(18, 0))
		self.cancel_download_button = ttk.Button(
			action_row, text="İndirmeyi İptal Et", command=self.cancel_download, state="disabled"
		)
		self.cancel_download_button.pack(side="left")
		self.download_button = ttk.Button(
			action_row,
			text="İndirmeyi Başlat",
			style="Accent.TButton",
			command=self.download_video,
			state="disabled",
		)
		self.download_button.pack(side="right")

	def _build_converter_tab(self, content: ttk.Frame) -> None:
		self.convert_input_var = tk.StringVar()
		self.convert_mode_var = tk.StringVar(value="Video")
		self.convert_format_var = tk.StringVar(value="MP4")
		self.convert_output_var = tk.StringVar(value="Çıktı dosyası kaynak dosyanın yanına kaydedilir.")
		self.convert_status_var = tk.StringVar(value="Dönüştürülecek video veya ses dosyasını seçin.")

		ttk.Label(content, text="Video veya ses dosyasını başka bir biçime dönüştürün.").pack(
			anchor="w", pady=(0, 18)
		)
		ttk.Label(content, text="Kaynak dosya").pack(anchor="w", pady=(0, 6))
		input_row = ttk.Frame(content)
		input_row.pack(fill="x")
		ttk.Entry(input_row, textvariable=self.convert_input_var).pack(side="left", fill="x", expand=True)
		ttk.Button(input_row, text="Dosya Seç", command=self._choose_convert_input).pack(side="left", padx=(8, 0))

		format_row = ttk.Frame(content)
		format_row.pack(fill="x", pady=(18, 0))
		ttk.Label(format_row, text="Tür").pack(side="left", padx=(0, 8))
		self.convert_mode_box = ttk.Combobox(
			format_row, textvariable=self.convert_mode_var, state="readonly", values=("Video", "Ses"), width=12
		)
		self.convert_mode_box.pack(side="left")
		self.convert_mode_box.bind("<<ComboboxSelected>>", self._update_convert_formats)
		ttk.Label(format_row, text="Hedef biçim").pack(side="left", padx=(18, 8))
		self.convert_format_box = ttk.Combobox(
			format_row, textvariable=self.convert_format_var, state="readonly", values=(), width=14
		)
		self.convert_format_box.pack(side="left")
		self.convert_format_box.bind("<<ComboboxSelected>>", self._update_convert_output)

		ttk.Label(content, textvariable=self.convert_output_var, wraplength=650).pack(anchor="w", pady=(16, 0))
		self.convert_progress = ttk.Progressbar(content, mode="indeterminate")
		self.convert_progress.pack(fill="x", pady=(22, 10))
		ttk.Label(content, textvariable=self.convert_status_var, wraplength=650).pack(anchor="w")
		action_row = ttk.Frame(content)
		action_row.pack(fill="x", pady=(18, 0))
		self.convert_cancel_button = ttk.Button(
			action_row, text="İşlemi İptal Et", command=self.cancel_ffmpeg, state="disabled"
		)
		self.convert_cancel_button.pack(side="left")
		self.convert_start_button = ttk.Button(
			action_row, text="Dönüştür", style="Accent.TButton", command=self.convert_file
		)
		self.convert_start_button.pack(side="right")
		self._update_convert_formats()

	def _build_compress_tab(self, content: ttk.Frame) -> None:
		self.compress_input_var = tk.StringVar()
		self.compress_crf_var = tk.IntVar(value=27)
		self.compress_crf_label_var = tk.StringVar(value="27")
		self.compress_preset_var = tk.StringVar(value="medium")
		self.compress_output_var = tk.StringVar(value="Çıktı dosyası kaynak dosyanın yanına kaydedilir.")
		self.compress_status_var = tk.StringVar(value="Sıkıştırılacak video dosyasını seçin.")

		ttk.Label(content, text="Çözünürlüğü değiştirmeden video boyutunu azaltın.").pack(
			anchor="w", pady=(0, 18)
		)
		ttk.Label(content, text="Video dosyası").pack(anchor="w", pady=(0, 6))
		input_row = ttk.Frame(content)
		input_row.pack(fill="x")
		ttk.Entry(input_row, textvariable=self.compress_input_var).pack(side="left", fill="x", expand=True)
		ttk.Button(input_row, text="Dosya Seç", command=self._choose_compress_input).pack(side="left", padx=(8, 0))

		quality_row = ttk.Frame(content)
		quality_row.pack(fill="x", pady=(22, 0))
		ttk.Label(quality_row, text="Kalite / boyut").pack(side="left")
		ttk.Scale(
			quality_row,
			from_=18,
			to=35,
			orient="horizontal",
			variable=self.compress_crf_var,
			command=self._update_compress_crf_label,
		).pack(side="left", fill="x", expand=True, padx=12)
		tk.Label(quality_row, textvariable=self.compress_crf_label_var, width=3).pack(side="left")

		preset_row = ttk.Frame(content)
		preset_row.pack(fill="x", pady=(12, 0))
		ttk.Label(preset_row, text="Kodlama hızı").pack(side="left", padx=(0, 10))
		ttk.Combobox(
			preset_row,
			textvariable=self.compress_preset_var,
			state="readonly",
			values=("fast", "medium", "slow"),
			width=14,
		).pack(side="left")
		ttk.Label(
			content,
			text="Daha yüksek CRF genellikle daha küçük dosya ve daha düşük görüntü kalitesi verir. Çözünürlük korunur.",
			wraplength=650,
		).pack(anchor="w", pady=(12, 0))
		ttk.Label(content, textvariable=self.compress_output_var, wraplength=650).pack(anchor="w", pady=(14, 0))
		self.compress_progress = ttk.Progressbar(content, mode="indeterminate")
		self.compress_progress.pack(fill="x", pady=(18, 10))
		ttk.Label(content, textvariable=self.compress_status_var, wraplength=650).pack(anchor="w")
		action_row = ttk.Frame(content)
		action_row.pack(fill="x", pady=(18, 0))
		self.compress_cancel_button = ttk.Button(
			action_row, text="İşlemi İptal Et", command=self.cancel_ffmpeg, state="disabled"
		)
		self.compress_cancel_button.pack(side="left")
		self.compress_start_button = ttk.Button(
			action_row, text="Sıkıştır", style="Accent.TButton", command=self.compress_file
		)
		self.compress_start_button.pack(side="right")

	def _choose_convert_input(self) -> None:
		selected = filedialog.askopenfilename(
			filetypes=(("Video ve ses", "*.mp4 *.mkv *.mov *.webm *.avi *.mp3 *.wav *.flac *.ogg *.m4a"), ("Tüm dosyalar", "*.*"))
		)
		if selected:
			self.convert_input_var.set(selected)
			self._update_convert_output()

	def _choose_compress_input(self) -> None:
		selected = filedialog.askopenfilename(
			filetypes=(("Video", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v"), ("Tüm dosyalar", "*.*"))
		)
		if selected:
			self.compress_input_var.set(selected)
			self._update_compress_output()

	def _update_convert_formats(self, _event: Any = None) -> None:
		formats = ("MP4", "MKV", "MOV", "WebM") if self.convert_mode_var.get() == "Video" else ("MP3", "AAC", "WAV", "FLAC", "OGG")
		self.convert_format_box.configure(values=formats)
		self.convert_format_var.set(formats[0])
		self._update_convert_output()

	def _update_convert_output(self, _event: Any = None) -> None:
		input_path = self.convert_input_var.get().strip()
		if not input_path:
			self.convert_output_var.set("Çıktı dosyası kaynak dosyanın yanına kaydedilir.")
			return
		extension = self.convert_format_var.get().lower()
		base_path = os.path.splitext(input_path)[0]
		self.convert_output_var.set(f"Çıktı: {base_path}_converted.{extension}")

	def _update_compress_output(self) -> None:
		input_path = self.compress_input_var.get().strip()
		if not input_path:
			self.compress_output_var.set("Çıktı dosyası kaynak dosyanın yanına kaydedilir.")
			return
		base_path = os.path.splitext(input_path)[0]
		self.compress_output_var.set(f"Çıktı: {base_path}_compressed.mp4")

	def _update_compress_crf_label(self, value: str) -> None:
		self.compress_crf_label_var.set(str(round(float(value))))

	def convert_file(self) -> None:
		input_path = self.convert_input_var.get().strip()
		if not os.path.isfile(input_path):
			messagebox.showerror("Dosya bulunamadı", "Dönüştürülecek geçerli bir dosya seçin.")
			return

		mode = self.convert_mode_var.get()
		extension = self.convert_format_var.get().lower()
		output_path = f"{os.path.splitext(input_path)[0]}_converted.{extension}"
		if mode == "Video":
			if extension == "webm":
				arguments = ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus", "-b:a", "160k"]
			else:
				arguments = ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
		else:
			codecs = {
				"mp3": ("libmp3lame", "192k"),
				"aac": ("aac", "192k"),
				"wav": ("pcm_s16le", None),
				"flac": ("flac", None),
				"ogg": ("libvorbis", "192k"),
			}
			codec, bitrate = codecs[extension]
			arguments = ["-map", "0:a:0", "-vn", "-c:a", codec]
			if bitrate:
				arguments.extend(("-b:a", bitrate))

		self._start_ffmpeg_job(
			input_path,
			output_path,
			arguments,
			self.convert_status_var,
			self.convert_progress,
		)

	def compress_file(self) -> None:
		input_path = self.compress_input_var.get().strip()
		if not os.path.isfile(input_path):
			messagebox.showerror("Dosya bulunamadı", "Sıkıştırılacak geçerli bir video seçin.")
			return

		output_path = f"{os.path.splitext(input_path)[0]}_compressed.mp4"
		crf = round(self.compress_crf_var.get())
		preset = self.compress_preset_var.get()
		arguments = [
			"-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
			"-preset", preset, "-crf", str(crf), "-c:a", "aac", "-b:a", "128k",
			"-movflags", "+faststart",
		]
		self._start_ffmpeg_job(
			input_path,
			output_path,
			arguments,
			self.compress_status_var,
			self.compress_progress,
		)

	def _start_ffmpeg_job(
		self,
		input_path: str,
		output_path: str,
		arguments: list[str],
		status_var: tk.StringVar,
		progress: ttk.Progressbar,
	) -> None:
		if self.ffmpeg_busy:
			messagebox.showinfo("İşlem sürüyor", "Önce devam eden FFmpeg işleminin bitmesini bekleyin.")
			return
		if os.path.exists(output_path) and not messagebox.askyesno(
			"Dosya var", f"{os.path.basename(output_path)} zaten var. Üzerine yazılsın mı?"
		):
			return

		try:
			with tempfile.NamedTemporaryFile(
				prefix=".video-islem-", suffix=os.path.splitext(output_path)[1],
				dir=os.path.dirname(output_path), delete=False
			) as temporary_file:
				temporary_path = temporary_file.name
		except OSError as error:
			messagebox.showerror("Çıktı oluşturulamadı", str(error))
			return

		command = [
			imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
			"-y", "-i", input_path, *arguments, temporary_path,
		]
		self.ffmpeg_cancel_event.clear()
		self.ffmpeg_busy = True
		self.convert_start_button.configure(state="disabled")
		self.compress_start_button.configure(state="disabled")
		self.convert_cancel_button.configure(state="normal")
		self.compress_cancel_button.configure(state="normal")
		progress.configure(mode="indeterminate")
		progress.start(12)
		status_var.set("FFmpeg işlemi çalışıyor...")
		threading.Thread(
			target=self._ffmpeg_worker,
			args=(command, temporary_path, output_path, status_var),
			daemon=True,
		).start()

	def _ffmpeg_worker(
		self, command: list[str], temporary_path: str, output_path: str, status_var: tk.StringVar
	) -> None:
		was_cancelled = False
		error_message = ""
		try:
			self.ffmpeg_process = subprocess.Popen(
				command,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.PIPE,
				text=True,
				encoding="utf-8",
				errors="replace",
			)
			while self.ffmpeg_process.poll() is None:
				if self.ffmpeg_cancel_event.wait(0.2):
					self.ffmpeg_process.terminate()
					break
			stderr = self.ffmpeg_process.communicate()[1] or ""
			was_cancelled = self.ffmpeg_cancel_event.is_set()
			if was_cancelled:
				pass
			elif self.ffmpeg_process.returncode != 0:
				error_message = stderr.strip() or "FFmpeg dönüştürme işlemini tamamlayamadı."
			else:
				os.replace(temporary_path, output_path)
		except Exception as error:
			error_message = str(error)
		finally:
			self.ffmpeg_process = None
			if os.path.exists(temporary_path):
				os.remove(temporary_path)
			self.root.after(0, self._ffmpeg_finished, was_cancelled, error_message, output_path, status_var)

	def cancel_ffmpeg(self) -> None:
		if not self.ffmpeg_busy:
			return
		self.ffmpeg_cancel_event.set()
		if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
			self.ffmpeg_process.terminate()
		self.convert_status_var.set("İptal ediliyor...")
		self.compress_status_var.set("İptal ediliyor...")

	def _ffmpeg_finished(
		self, was_cancelled: bool, error: str, output_path: str, status_var: tk.StringVar
	) -> None:
		self.ffmpeg_busy = False
		for progress in (self.convert_progress, self.compress_progress):
			progress.stop()
			progress.configure(mode="indeterminate")
		self.convert_start_button.configure(state="normal")
		self.compress_start_button.configure(state="normal")
		self.convert_cancel_button.configure(state="disabled")
		self.compress_cancel_button.configure(state="disabled")
		if was_cancelled:
			status_var.set("İşlem iptal edildi; tamamlanmamış çıktı silindi.")
		elif error:
			status_var.set("İşlem başarısız oldu.")
			messagebox.showerror("FFmpeg hatası", error)
		else:
			status_var.set(f"Tamamlandı: {output_path}")

	def cancel_download(self) -> None:
		self.download_cancel_event.set()
		self.cancel_download_button.configure(state="disabled")
		self.status_var.set("İndirme iptal ediliyor...")

	def choose_folder(self) -> None:
		selected = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser("~"))
		if selected:
			self.folder_var.set(selected)

	def inspect_video(self) -> None:
		url = self.url_var.get().strip()
		parsed_url = urlparse(url)
		if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
			messagebox.showerror("Geçersiz bağlantı", "http:// veya https:// ile başlayan geçerli bir bağlantı girin.")
			return

		self.inspected_url = ""
		self.quality_by_label.clear()
		self.quality_box.configure(values=())
		self.quality_var.set("")
		self.download_button.configure(state="disabled")
		self.inspect_button.configure(state="disabled")
		self.status_var.set("Video ve kullanılabilir çözünürlükler aranıyor...")

		threading.Thread(target=self._inspect_worker, args=(url,), daemon=True).start()

	def _inspect_worker(self, url: str) -> None:
		try:
			options: dict[str, Any] = {"quiet": True, "no_warnings": True, "noplaylist": True}
			with yt_dlp.YoutubeDL(options) as downloader:
				info = downloader.extract_info(url, download=False)

			heights = sorted(
				{
					int(video_format["height"])
					for video_format in info.get("formats", [])
					if video_format.get("height")
					and video_format.get("vcodec") != "none"
				},
				reverse=True,
			)
			quality_by_label: dict[str, int | None]
			if heights:
				labels = [f"{height}p" for height in heights]
				quality_by_label = dict(zip(labels, heights))
			else:
				is_direct_video = (
					info.get("extractor_key") in {"Generic", "Http"}
					and (
						(info.get("url") and info.get("ext") in VIDEO_FILE_EXTENSIONS)
						or any(
							video_format.get("url")
							and video_format.get("ext") in VIDEO_FILE_EXTENSIONS
							and video_format.get("vcodec") != "none"
							for video_format in info.get("formats", [])
						)
					)
				)
				if not is_direct_video:
					raise ValueError("Bu bağlantıda indirilebilir bir video çözünürlüğü bulunamadı.")
				labels = ["Orijinal dosya (çözünürlük bilgisi yok)"]
				quality_by_label = {labels[0]: None}

			self.quality_by_label = quality_by_label
			title = info.get("title") or "Video"
			self.root.after(0, self._inspection_complete, url, labels, title)
		except Exception as error:
			self.root.after(0, self._inspection_failed, str(error))

	def _inspection_complete(self, url: str, labels: list[str], title: str) -> None:
		self.inspected_url = url
		self.quality_box.configure(values=labels)
		self.quality_var.set(labels[0])
		self.download_button.configure(state="normal")
		self.inspect_button.configure(state="normal")
		self.status_var.set(f"{title} için {len(labels)} çözünürlük bulundu.")

	def _inspection_failed(self, error: str) -> None:
		self.inspect_button.configure(state="normal")
		self.status_var.set("Bağlantı çözümlenemedi.")
		messagebox.showerror("Video bulunamadı", error)

	def download_video(self) -> None:
		url = self.url_var.get().strip()
		if url != self.inspected_url:
			messagebox.showerror("Bağlantı değişti", "İndirmeden önce bağlantı için kaliteleri yeniden bulun.")
			return

		quality_label = self.quality_var.get()
		if quality_label not in self.quality_by_label:
			messagebox.showerror("Çözünürlük seçilmedi", "Listeden bir çözünürlük seçin.")
			return
		height = self.quality_by_label[quality_label]
		folder = os.path.expanduser(self.folder_var.get().strip())
		if not folder or not os.path.isdir(folder):
			messagebox.showerror("Klasör bulunamadı", "Geçerli bir kayıt klasörü seçin.")
			return

		self.download_button.configure(state="disabled")
		self.inspect_button.configure(state="disabled")
		self.cancel_download_button.configure(state="normal")
		self.download_cancel_event.clear()
		self.progress.configure(value=0)
		quality_text = f"{height}p video" if height else "Orijinal video"
		self.status_var.set(f"{quality_text} indiriliyor...")
		threading.Thread(target=self._download_worker, args=(url, height, folder), daemon=True).start()

	def _download_worker(self, url: str, height: int | None, folder: str) -> None:
		def report_progress(data: dict[str, Any]) -> None:
			if self.download_cancel_event.is_set():
				raise DownloadCancelled("İndirme kullanıcı tarafından iptal edildi.")
			if data.get("status") == "downloading":
				downloaded = data.get("downloaded_bytes", 0)
				total = data.get("total_bytes") or data.get("total_bytes_estimate")
				if total:
					percent = downloaded * 100 / total
					text = f"İndiriliyor: %{percent:.1f}"
					self.root.after(0, self._update_progress, percent, text)
				else:
					self.root.after(0, self._update_progress, 0, "Video indiriliyor...")
			elif data.get("status") == "finished":
				self.root.after(0, self._update_progress, 100, "Dosya birleştiriliyor...")

		options: dict[str, Any] = {
			"format": (
				f"bestvideo[height={height}]+bestaudio/best[height={height}]"
				if height
				else "best"
			),
			"outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
			"ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
			"noplaylist": True,
			"progress_hooks": [report_progress],
		}
		try:
			with yt_dlp.YoutubeDL(options) as downloader:
				downloader.download([url])
			self.root.after(0, self._download_complete)
		except DownloadCancelled:
			self.root.after(0, self._download_cancelled)
		except Exception as error:
			self.root.after(0, self._download_failed, str(error))

	def _update_progress(self, percent: float, text: str) -> None:
		self.progress.configure(value=percent)
		self.status_var.set(text)

	def _download_complete(self) -> None:
		self.progress.configure(value=100)
		self.status_var.set("İndirme tamamlandı.")
		self.download_button.configure(state="normal")
		self.inspect_button.configure(state="normal")
		self.cancel_download_button.configure(state="disabled")

	def _download_cancelled(self) -> None:
		self.status_var.set("İndirme iptal edildi.")
		self.download_button.configure(state="normal")
		self.inspect_button.configure(state="normal")
		self.cancel_download_button.configure(state="disabled")

	def _download_failed(self, error: str) -> None:
		self.status_var.set("İndirme başarısız oldu.")
		self.download_button.configure(state="normal")
		self.inspect_button.configure(state="normal")
		self.cancel_download_button.configure(state="disabled")
		messagebox.showerror("İndirme hatası", error)


if __name__ == "__main__":
	app_root = tk.Tk()
	VideoDownloaderApp(app_root)
	app_root.mainloop()
