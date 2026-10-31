"""Chatterbox Voice Studio - desktop voice cloning GUI (PySide6)."""
import os
import random
import sys
import queue
import subprocess
import tempfile
import threading
import time
import traceback

# pythonw.exe (used by the installed shortcut) has no console: send output to a log file instead of failing.
if sys.stdout is None or sys.stderr is None:
    _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QAudioSource, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

TAGS = ["[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]",
        "[sniff]", "[gasp]", "[chuckle]", "[laugh]"]
MAX_CHARS = 300
VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
BASE = "ResembleAI/chatterbox"
PATTERNS = ["*.safetensors", "*.json", "*.txt", "*.pt", "*.model"]
MTL_BASE_FILES = ["ve.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt", "Cangjie5_TC.json"]

LANGUAGES = {
    "ar": "Arabic", "da": "Danish", "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "fi": "Finnish", "fr": "French", "he": "Hebrew", "hi": "Hindi", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ms": "Malay", "nl": "Dutch", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese",
    "ru": "Russian", "sv": "Swedish", "sw": "Swahili", "tr": "Turkish", "zh": "Chinese",
}
SAMPLE_TEXT = {
    "zh": "你好，今天天气真不错，希望你有一个愉快的周末。",
    "es": "¡Hola! ¿Cómo estás? Hoy hace un día maravilloso, ¿te apetece dar un paseo?",
    "pt": "Olá! Como você está? Hoje o dia está lindo, vamos dar um passeio?",
    "hi": "नमस्ते, आप कैसे हैं? आज मौसम बहुत सुहावना है।",
    "fr": "Bonjour, comment ça va? Ceci est le modèle de synthèse vocale multilingue Chatterbox.",
    "de": "Hallo, wie geht es dir? Heute ist ein wunderschöner Tag.",
}


def _pack(model_id, label, repo, t3_file, lang):
    return dict(id=model_id, label=label, kind="pack", tags=False, lang=lang, repo=repo, t3_file=t3_file,
                sources=[(BASE, MTL_BASE_FILES), (repo, [t3_file, "s3gen_v3.pt"])],
                keys=[(BASE, "ve.pt"), (BASE, "grapheme_mtl_merged_expanded_v1.json"), (repo, t3_file), (repo, "s3gen_v3.pt")])


MODEL_LIST = [
    dict(id="turbo", label="Turbo - English, 350M, sound tags, fast (GPU recommended)", kind="turbo", tags=True,
         sources=[("ResembleAI/chatterbox-turbo", PATTERNS)],
         keys=[("ResembleAI/chatterbox-turbo", f) for f in ("ve.safetensors", "s3gen_meanflow.safetensors", "t3_turbo_v1.safetensors")]),
    dict(id="nano", label="Nano - English, 110M, sound tags, light (runs well on CPU)", kind="nano", tags=True,
         sources=[("ResembleAI/chatterbox-nano", PATTERNS)],
         keys=[("ResembleAI/chatterbox-nano", f) for f in ("ve.safetensors", "s3gen_meanflow.safetensors", "t3_nano_v1.safetensors")]),
    dict(id="orig", label="Chatterbox - English, 500M, expressive (exaggeration / CFG)", kind="orig", tags=False,
         sources=[(BASE, ["ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors", "tokenizer.json", "conds.pt"])],
         keys=[(BASE, f) for f in ("ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors", "tokenizer.json")]),
    dict(id="mtl", label="Multilingual V3 - 23 languages, 500M", kind="mtl", tags=False, lang="choice",
         sources=[(BASE, ["ve.pt", "t3_mtl23ls_v3.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt", "Cangjie5_TC.json"])],
         keys=[(BASE, f) for f in ("ve.pt", "t3_mtl23ls_v3.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json")]),
    _pack("pack_zh", "Language Pack - Chinese (Mandarin)", "ResembleAI/Chatterbox-Multilingual-zh-cmn", "t3_zh_cmn.safetensors", "zh"),
    _pack("pack_es_mx", "Language Pack - Spanish (Latin America)", "ResembleAI/Chatterbox-Multilingual-es-mx-latam", "t3_es_mx_latam.safetensors", "es"),
    _pack("pack_es_es", "Language Pack - Spanish (Spain)", "ResembleAI/Chatterbox-Multilingual-es-es", "t3_es_es.safetensors", "es"),
    _pack("pack_pt_br", "Language Pack - Portuguese (Brazil)", "ResembleAI/Chatterbox-Multilingual-pt-br", "t3_pt_br.safetensors", "pt"),
    _pack("pack_pt_pt", "Language Pack - Portuguese (Portugal)", "ResembleAI/Chatterbox-Multilingual-pt-pt", "t3_pt_pt.safetensors", "pt"),
    _pack("pack_hi", "Language Pack - Hindi", "ResembleAI/Chatterbox-Multilingual-hi", "t3_hi.safetensors", "hi"),
]
MODEL_BY_ID = {m["id"]: m for m in MODEL_LIST}
DEFAULT_TEXT = ("Oh, that's hilarious! [chuckle] Um anyway, we do have a new model in "
                "store. Would you like me to get some prices for you?")
PLAIN_TEXT = ("Oh, that's hilarious! Um anyway, we do have a new model in "
              "store. Would you like me to get some prices for you?")

STYLE = """
* { font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 10pt; color: #e6e8ee; }
QMainWindow, QWidget#root { background: #14161c; }
QFrame#card { background: #1d2029; border: 1px solid #2a2e3a; border-radius: 12px; }
QLabel#title { font-size: 20pt; font-weight: 600; }
QLabel#sub, QLabel#hint { color: #8b91a3; }
QLabel#section { font-weight: 600; font-size: 11pt; }
QPlainTextEdit { background: #14161c; border: 1px solid #2a2e3a; border-radius: 8px; padding: 8px; selection-background-color: #6366f1; }
QPlainTextEdit:focus { border-color: #6366f1; }
QPushButton { background: #2a2e3a; border: none; border-radius: 8px; padding: 8px 16px; }
QPushButton:hover { background: #343949; }
QPushButton:disabled { color: #5b6073; background: #20232d; }
QPushButton#tag { background: #262a4a; border: 1px solid #3b4080; border-radius: 14px; padding: 4px 12px; color: #c7ccff; }
QPushButton#tag:hover { background: #3b4080; }
QPushButton#primary { background: #6366f1; font-weight: 600; font-size: 11pt; padding: 12px 24px; color: white; }
QPushButton#primary:hover { background: #7578f5; }
QPushButton#primary:disabled { background: #34366b; color: #8b8fc0; }
QComboBox { background: #14161c; border: 1px solid #2a2e3a; border-radius: 6px; padding: 6px 8px; }
QComboBox QAbstractItemView { background: #1d2029; selection-background-color: #6366f1; }
QSpinBox, QDoubleSpinBox { background: #14161c; border: 1px solid #2a2e3a; border-radius: 6px; padding: 4px 6px; }
QProgressBar { background: #14161c; border: none; border-radius: 4px; height: 8px; color: #e6e8ee; }
QProgressBar::chunk { background: #6366f1; border-radius: 4px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #3b4080; background: #14161c; }
QCheckBox::indicator:checked { background: #6366f1; }
"""


class Waveform(QWidget):
    """Tiny waveform preview of the reference clip."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(56)
        self.peaks = None

    def set_audio(self, data):
        n = 300
        if data is None or len(data) == 0:
            self.peaks = None
        else:
            chunks = np.array_split(np.abs(data), n)
            p = np.array([c.max() if len(c) else 0 for c in chunks])
            self.peaks = p / (p.max() or 1)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self.peaks is None:
            p.setPen(QColor("#5b6073"))
            p.drawText(self.rect(), Qt.AlignCenter, "No reference audio loaded")
            return
        pen = QPen(QColor("#818cf8"))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        step = w / len(self.peaks)
        for i, v in enumerate(self.peaks):
            x = i * step + step / 2
            half = max(1.0, v * (h / 2 - 2))
            p.drawLine(int(x), int(h / 2 - half), int(x), int(h / 2 + half))


def model_ready(entry):
    """True when the key weight files for this model are fully in the local HF cache."""
    from huggingface_hub import try_to_load_from_cache
    return all(isinstance(try_to_load_from_cache(repo, f), str) for repo, f in entry["keys"])


def pick_device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_language_pack(entry, device):
    """Single Language Pack: the pack's own T3 + V3 S3Gen weights, with the shared voice encoder/tokenizer/conds.
    Mirrors ChatterboxMultilingualTTS.from_local, but takes each file from its own repo."""
    import torch
    import chatterbox.mtl_tts as m
    from huggingface_hub import hf_hub_download
    ml = torch.device("cpu") if device in ("cpu", "mps") else None
    ve_path = hf_hub_download(BASE, "ve.pt")
    tok_path = hf_hub_download(BASE, "grapheme_mtl_merged_expanded_v1.json")
    conds_path = hf_hub_download(BASE, "conds.pt")
    t3_path = hf_hub_download(entry["repo"], entry["t3_file"])
    s3_path = hf_hub_download(entry["repo"], "s3gen_v3.pt")

    ve = m.VoiceEncoder()
    ve.load_state_dict(torch.load(ve_path, map_location=ml, weights_only=True))
    ve.to(device).eval()
    t3 = m.T3(m.T3Config.multilingual())
    t3_state = m.load_safetensors(t3_path)
    if "model" in t3_state:
        t3_state = t3_state["model"][0]
    t3.load_state_dict(t3_state)
    t3.to(device).eval()
    s3gen = m.S3Gen()
    res = s3gen.load_state_dict(torch.load(s3_path, map_location=ml, weights_only=True), strict=False)
    # V3 checkpoints omit the tokenizer's fixed mel-filter/window tables; they are rebuilt when S3Gen is created
    missing = [k for k in res.missing_keys if not k.startswith("tokenizer.")]
    if missing or res.unexpected_keys:
        raise RuntimeError(f"Decoder weights do not match this Chatterbox version (missing {len(missing)}, "
                           f"unexpected {len(res.unexpected_keys)} tensors).")
    s3gen.to(device).eval()
    tokenizer = m.MTLTokenizer(tok_path)
    conds = m.Conditionals.load(conds_path, map_location=ml).to(device)
    return m.ChatterboxMultilingualTTS(t3, s3gen, ve, tokenizer, device, conds=conds)


def load_model(entry, device):
    kind = entry["kind"]
    if kind in ("turbo", "nano"):
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        patch_float32(ChatterboxTurboTTS)
        return ChatterboxTurboTTS.from_pretrained(device, nano=(kind == "nano"))
    if kind == "orig":
        from chatterbox.tts import ChatterboxTTS
        return ChatterboxTTS.from_pretrained(device)
    if kind == "mtl":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_pretrained(device, t3_model="v3")
    return load_language_pack(entry, device)


def patch_float32(cls):
    """Upstream's loudness normalisation returns float64 audio, which the float32 models reject
    ("expected scalar type Float but found Double"). Cast it back, so stock Chatterbox works unpatched."""
    orig = cls.norm_loudness
    if getattr(orig, "_float32_patched", False):
        return

    def norm_loudness(self, wav, sr, *args, **kwargs):
        return np.asarray(orig(self, wav, sr, *args, **kwargs), dtype=np.float32)

    norm_loudness._float32_patched = True
    cls.norm_loudness = norm_loudness


class DownloadWorker(QObject):
    progress = Signal(float, float, float)  # downloaded bytes, total bytes, bytes/sec
    finished = Signal()
    failed = Signal(str)

    def __init__(self, entry):
        super().__init__()
        self.entry = entry

    def run(self):
        import fnmatch
        import threading
        import time
        try:
            import huggingface_hub.constants as hfc
            hfc.HF_HUB_DISABLE_XET = True  # plain HTTP download gives reliable byte progress
            from huggingface_hub import HfApi, snapshot_download, try_to_load_from_cache
            from tqdm.auto import tqdm
            sources = self.entry["sources"]
            total = 0
            for repo, patterns in sources:
                info = HfApi().model_info(repo, files_metadata=True)
                for f in info.siblings:
                    if any(fnmatch.fnmatch(f.rfilename, pt) for pt in patterns):
                        if not isinstance(try_to_load_from_cache(repo, f.rfilename), str):
                            total += f.size or 0
            total = max(total, 1)
            lock = threading.Lock()
            state = {"done": 0, "t0": time.time(), "last": 0.0}
            emit = self.progress.emit

            class Bar(tqdm):
                def __init__(bar, *a, **kw):
                    super().__init__(*a, **kw)
                    # the library keeps a network-transfer bar and a disk-reconstruction bar; count one
                    bar.primary = str(kw.get("desc", "")).startswith("Downloading bytes")
                    if bar.primary:
                        with lock:
                            state["done"] += bar.n

                def update(bar, n=1):
                    r = super().update(n)
                    if getattr(bar, "primary", False) and n:
                        with lock:
                            state["done"] += n
                            now = time.time()
                            if now - state["last"] > 0.2:
                                state["last"] = now
                                emit(state["done"], total, state["done"] / max(now - state["t0"], 1e-3))
                    return r

            for repo, patterns in sources:
                snapshot_download(repo_id=repo, allow_patterns=patterns, tqdm_class=Bar,
                                  token=os.getenv("HF_TOKEN") or None)
            self.progress.emit(total, total, 0.0)
            self.finished.emit()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.failed.emit(f"Download failed: {e}")


class Worker(QObject):
    """Lives on ONE long-lived thread: the model/CUDA state must always be used from the thread that created it."""
    status = Signal(str)
    done = Signal(object, int)
    failed = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state

    def run(self, ref_path, text, params):
        self.ref_path, self.text, self.params = ref_path, text, params
        try:
            import torch
            st = self.state
            entry = MODEL_BY_ID[self.params["model"]]
            kind = entry["kind"]
            if st.get("model") is None or st.get("model_id") != entry["id"]:
                st["model"] = None
                st["cond_key"] = None
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                self.status.emit(f"Loading {entry['label'].split(' - ')[0]} into memory (about 10-30 seconds)...")
                st["model"] = load_model(entry, pick_device())
                st["model_id"] = entry["id"]
            model = st["model"]
            norm = self.params["norm_loudness"]
            key = (entry["id"], self.ref_path, os.path.getmtime(self.ref_path), norm if kind in ("turbo", "nano") else None)
            if st.get("cond_key") != key:
                self.status.emit("Analysing reference voice (done once per sample)...")
                if kind in ("turbo", "nano"):
                    model.prepare_conditionals(self.ref_path, norm_loudness=norm)
                else:
                    model.prepare_conditionals(self.ref_path, exaggeration=self.params["exaggeration"])
                st["cond_key"] = key
            seed = self.params["seed"]
            if seed == 0:
                seed = random.randint(1, 2**31 - 1)
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            random.seed(seed)
            np.random.seed(seed % (2**32))
            self.status.emit(f"Generating speech (seed {seed})...")
            p = self.params
            if kind in ("turbo", "nano"):
                wav = model.generate(self.text, temperature=p["temperature"], top_p=p["top_p"], top_k=p["top_k"],
                                     repetition_penalty=p["repetition_penalty"], norm_loudness=norm)
            elif kind == "orig":
                wav = model.generate(self.text, temperature=p["temperature"], top_p=p["top_p"], min_p=p["min_p"],
                                     repetition_penalty=p["repetition_penalty"],
                                     exaggeration=p["exaggeration"], cfg_weight=p["cfg_weight"])
            else:
                wav = model.generate(self.text, language_id=p["lang"], temperature=p["temperature"], top_p=p["top_p"],
                                     min_p=p["min_p"], repetition_penalty=p["repetition_penalty"],
                                     exaggeration=p["exaggeration"], cfg_weight=p["cfg_weight"])
            # plain NumPy copy: the torch-backed buffer must be freed on this thread, not the UI thread
            self.done.emit(np.array(wav.squeeze().cpu().numpy(), dtype=np.float32, copy=True), model.sr)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)


def card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    return f, lay


def label(text, name=None):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    return l


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chatterbox Voice Studio")
        self.resize(900, 860)
        self.state = {}
        self.ref_path = None
        self.out_audio = None
        self.out_sr = 24000
        self.out_file = os.path.join(tempfile.gettempdir(), "chatterbox_last.wav")
        self._jobs = set()

        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(24, 20, 24, 20)
        main.setSpacing(14)

        main.addWidget(label("Chatterbox Voice Studio", "title"))
        main.addWidget(label("Clone a voice from one sample, then make it speak - in English or 20+ languages.", "sub"))

        # Reference
        c1, l1 = card()
        l1.addWidget(label("1  Reference voice", "section"))
        row = QHBoxLayout()
        self.voice_box = QComboBox()
        self.voice_box.setMinimumWidth(260)
        self.voice_box.activated.connect(self.on_voice_selected)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.pick_ref)
        self.rec_btn = QPushButton("Record")
        self.rec_btn.clicked.connect(self.toggle_record)
        row.addWidget(self.voice_box, 1)
        row.addWidget(browse)
        row.addWidget(self.rec_btn)
        l1.addLayout(row)
        self.ref_label = label("Pick a saved voice, browse for a clip, or record one (more than 5 seconds, clean speech).", "hint")
        self.ref_label.setWordWrap(True)
        l1.addWidget(self.ref_label)
        self.rec_source = None
        self.rec_io = None
        self.rec_buf = bytearray()
        self.rec_secs = 0
        self.rec_timer = QTimer(self)
        self.rec_timer.timeout.connect(self.tick_record)
        self.refresh_voices()
        self.wave = Waveform()
        l1.addWidget(self.wave)
        main.addWidget(c1)

        # Model
        cm, lm = card()
        lm.addWidget(label("Model", "section"))
        self.model_box = QComboBox()
        for m in MODEL_LIST:
            self.model_box.addItem(m["label"], m["id"])
        mrow = QHBoxLayout()
        mrow.addWidget(self.model_box, 1)
        self.dl_btn = QPushButton("Download model")
        self.dl_btn.clicked.connect(self.start_download)
        mrow.addWidget(self.dl_btn)
        lm.addLayout(mrow)
        self.model_status = label("", "hint")
        lm.addWidget(self.model_status)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 1000)
        self.dl_bar.setTextVisible(True)
        self.dl_bar.setFormat("%p%")
        self.dl_bar.setAlignment(Qt.AlignCenter)
        self.dl_bar.setFixedHeight(18)
        self.dl_bar.hide()
        lm.addWidget(self.dl_bar)
        self.downloading = False
        self.lang_box = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_box.addItem(f"{name} ({code})", code)
        self.lang_box.setCurrentIndex(self.lang_box.findData("en"))
        self.lang_row = QWidget()
        lr = QHBoxLayout(self.lang_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.addWidget(label("Language", "hint"))
        lr.addWidget(self.lang_box, 1)
        lm.addWidget(self.lang_row)
        self._auto_text = DEFAULT_TEXT
        self._family = None
        self.model_box.currentIndexChanged.connect(self.on_model_changed)
        self.lang_box.currentIndexChanged.connect(self.on_language_changed)
        main.addWidget(cm)

        # Text
        c2, l2 = card()
        l2.addWidget(label("2  Text to speak", "section"))
        self.text = QPlainTextEdit(DEFAULT_TEXT)
        self.text.setMinimumHeight(120)
        self.text.textChanged.connect(self.update_count)
        l2.addWidget(self.text)
        self.tag_widget = QWidget()
        tagrow = QGridLayout(self.tag_widget)
        tagrow.setContentsMargins(0, 0, 0, 0)
        tagrow.setSpacing(6)
        for i, t in enumerate(TAGS):
            b = QPushButton(t)
            b.setObjectName("tag")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, tag=t: self.insert_tag(tag))
            tagrow.addWidget(b, 0, i)
        l2.addWidget(self.tag_widget)
        self.tag_hint = label("Sound tags like [laugh] or [sigh] only work with the Turbo and Nano models.", "hint")
        l2.addWidget(self.tag_hint)
        self.count = label("", "hint")
        l2.addWidget(self.count)
        main.addWidget(c2)

        # Advanced
        c3, l3 = card()
        l3.addWidget(label("Advanced", "section"))

        def field(name, widget):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            v.addWidget(label(name, "hint"))
            v.addWidget(widget)
            return w

        self.seed = QSpinBox(); self.seed.setRange(0, 2**31 - 1)
        self.temp = QDoubleSpinBox(); self.temp.setRange(0.05, 2.0); self.temp.setSingleStep(0.05); self.temp.setValue(0.8)
        self.top_p = QDoubleSpinBox(); self.top_p.setRange(0.0, 1.0); self.top_p.setSingleStep(0.01); self.top_p.setValue(0.95)
        self.rep = QDoubleSpinBox(); self.rep.setRange(1.0, 2.0); self.rep.setSingleStep(0.05); self.rep.setValue(1.2)
        common = QHBoxLayout()
        for name, w in (("Seed (0 = random)", self.seed), ("Temperature", self.temp), ("Top P", self.top_p),
                        ("Repetition penalty", self.rep)):
            common.addWidget(field(name, w))
        l3.addLayout(common)

        # Turbo / Nano only
        self.top_k = QSpinBox(); self.top_k.setRange(0, 1000); self.top_k.setSingleStep(10); self.top_k.setValue(1000)
        self.norm = QCheckBox("Normalize loudness (-27 LUFS)"); self.norm.setChecked(True)
        self.turbo_opts = QWidget()
        tl = QHBoxLayout(self.turbo_opts)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(field("Top K", self.top_k))
        tl.addWidget(self.norm)
        tl.addStretch(1)
        l3.addWidget(self.turbo_opts)

        # Chatterbox / Multilingual / Language Packs
        self.exag = QDoubleSpinBox(); self.exag.setRange(0.25, 2.0); self.exag.setSingleStep(0.05); self.exag.setValue(0.5)
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(0.0, 1.0); self.cfg.setSingleStep(0.05); self.cfg.setValue(0.5)
        self.min_p = QDoubleSpinBox(); self.min_p.setRange(0.0, 1.0); self.min_p.setSingleStep(0.01); self.min_p.setValue(0.05)
        self.expr_opts = QWidget()
        el = QHBoxLayout(self.expr_opts)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(field("Exaggeration (0.5 = neutral)", self.exag))
        el.addWidget(field("CFG / pace (lower = slower)", self.cfg))
        el.addWidget(field("Min P", self.min_p))
        el.addStretch(1)
        l3.addWidget(self.expr_opts)
        main.addWidget(c3)

        # Generate + output
        self.gen = QPushButton("Generate speech")
        self.gen.setObjectName("primary")
        self.gen.setCursor(Qt.PointingHandCursor)
        self.gen.clicked.connect(self.generate)
        main.addWidget(self.gen)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        main.addWidget(self.progress)
        self.status = label("Ready.", "hint")
        main.addWidget(self.status)

        out = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.stop_btn = QPushButton("Stop")
        self.save_btn = QPushButton("Save as WAV...")
        self.folder_btn = QPushButton("Open folder")
        self.clear_btn = QPushButton("Clear temp files")
        for b in (self.play_btn, self.stop_btn, self.save_btn, self.folder_btn):
            b.setEnabled(False)
            out.addWidget(b)
        out.addWidget(self.clear_btn)
        out.addStretch(1)
        self.play_btn.clicked.connect(self.play)
        self.stop_btn.clicked.connect(self.player.stop)
        self.save_btn.clicked.connect(self.save)
        self.folder_btn.clicked.connect(self.open_folder)
        self.clear_btn.clicked.connect(self.clear_temp_files)
        main.addLayout(out)
        main.addStretch(1)
        # One persistent *Python* thread owns the model. (A QThread gives every call a fresh Python thread
        # state, and PyTorch/CUDA crashes on the second generation when that happens.)
        self.jobs = queue.Queue()
        self.gen_worker = Worker(self.state)
        self.gen_worker.status.connect(self.status.setText)
        self.gen_worker.done.connect(self.on_done)
        self.gen_worker.failed.connect(self.on_fail)

        def engine_loop():
            while True:
                job = self.jobs.get()
                if job is None:
                    # release the model on the thread that created it
                    try:
                        import gc
                        import torch
                        self.state.clear()
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.synchronize()
                            torch.cuda.empty_cache()
                    except Exception:  # noqa: BLE001
                        pass
                    return
                self.gen_worker.run(*job)

        self.engine = threading.Thread(target=engine_loop, daemon=True, name="chatterbox-engine")
        self.engine.start()
        self.model_ready = False
        self.apply_model_ui()
        self.refresh_model_state()
        self.update_count()

    def update_count(self):
        n = len(self.text.toPlainText())
        self.count.setText(f"{n} / {MAX_CHARS} characters")
        self.count.setStyleSheet("color: #f87171;" if n > MAX_CHARS else "")

    def insert_tag(self, tag):
        cur = self.text.textCursor()
        full = self.text.toPlainText()
        pos = cur.position()
        pre = "" if pos == 0 or full[pos - 1] == " " else " "
        cur.insertText(pre + tag + " ")
        self.text.setTextCursor(cur)
        self.text.setFocus()

    def refresh_voices(self, select=None):
        os.makedirs(VOICES_DIR, exist_ok=True)
        self.voice_box.clear()
        self.voice_box.addItem("Select a saved voice...", None)
        for f in sorted(os.listdir(VOICES_DIR)):
            if f.lower().endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a")):
                self.voice_box.addItem(os.path.splitext(f)[0], os.path.join(VOICES_DIR, f))
        if select:
            i = self.voice_box.findData(select)
            if i < 0:
                self.voice_box.addItem(os.path.basename(select), select)
                i = self.voice_box.count() - 1
            self.voice_box.setCurrentIndex(i)

    def on_voice_selected(self, i):
        path = self.voice_box.itemData(i)
        if path:
            self.load_ref(path)

    def pick_ref(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select reference audio", "",
                                              "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)")
        if path and self.load_ref(path):
            self.refresh_voices(select=path)

    def load_ref(self, path):
        try:
            data, sr = sf.read(path, always_2d=True)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot read audio", str(e))
            return False
        secs = len(data) / sr
        self.wave.set_audio(data.mean(axis=1))
        self.ref_path = path
        msg = f"{os.path.basename(path)}  -  {secs:.1f}s"
        if secs <= 5:
            msg += "  (too short: needs more than 5 seconds)"
        self.ref_label.setText(msg)
        return True

    def toggle_record(self):
        if self.rec_source is None:
            dev = QMediaDevices.defaultAudioInput()
            if dev.isNull():
                QMessageBox.warning(self, "No microphone", "No audio input device was found.")
                return
            fmt = QAudioFormat()
            fmt.setSampleRate(44100)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not dev.isFormatSupported(fmt):
                fmt = dev.preferredFormat()
                fmt.setChannelCount(1)
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self.rec_fmt = fmt
            self.rec_buf = bytearray()
            self.rec_secs = 0
            self.rec_source = QAudioSource(dev, fmt, self)
            self.rec_io = self.rec_source.start()
            self.rec_io.readyRead.connect(lambda: self.rec_buf.extend(bytes(self.rec_io.readAll())))
            self.rec_timer.start(1000)
            self.rec_btn.setText("Stop (0s)")
            self.ref_label.setText("Recording... speak naturally for 10+ seconds.")
        else:
            self.rec_timer.stop()
            self.rec_source.stop()
            self.rec_buf.extend(bytes(self.rec_io.readAll()))
            self.rec_source = None
            self.rec_io = None
            self.rec_btn.setText("Record")
            self.save_recording()

    def tick_record(self):
        self.rec_secs += 1
        self.rec_btn.setText(f"Stop ({self.rec_secs}s)")

    def save_recording(self):
        audio = np.frombuffer(bytes(self.rec_buf), dtype=np.int16)
        sr = self.rec_fmt.sampleRate()
        if len(audio) / sr <= 5:
            QMessageBox.information(self, "Too short", "Recording must be longer than 5 seconds. Please try again.")
            self.ref_label.setText("Recording discarded (too short).")
            return
        name, ok = QInputDialog.getText(self, "Save voice", "Name for this voice:", text="my_voice")
        name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        if not ok or not name:
            self.ref_label.setText("Recording discarded.")
            return
        os.makedirs(VOICES_DIR, exist_ok=True)
        path = os.path.join(VOICES_DIR, name + ".wav")
        sf.write(path, audio, sr, subtype="PCM_16")
        self.refresh_voices(select=path)
        self.load_ref(path)

    def current_entry(self):
        return MODEL_BY_ID[self.model_box.currentData()]

    def sample_for(self, entry, lang):
        if entry["tags"]:
            return DEFAULT_TEXT
        return SAMPLE_TEXT.get(lang, PLAIN_TEXT)

    def swap_sample_text(self, entry, lang):
        """Replace the text with a fitting sample, but only if the user hasn't edited the previous sample."""
        current = self.text.toPlainText()
        if current.strip() == "" or current == self._auto_text:
            self._auto_text = self.sample_for(entry, lang)
            self.text.setPlainText(self._auto_text)

    def apply_model_ui(self):
        entry = self.current_entry()
        kind = entry["kind"]
        tagged = entry["tags"]
        self.tag_widget.setVisible(tagged)
        self.tag_hint.setVisible(not tagged)
        self.turbo_opts.setVisible(tagged)
        self.expr_opts.setVisible(not tagged)
        has_lang = kind in ("mtl", "pack")
        self.lang_row.setVisible(has_lang)
        if kind == "pack":
            self.lang_box.blockSignals(True)
            self.lang_box.setCurrentIndex(self.lang_box.findData(entry["lang"]))
            self.lang_box.blockSignals(False)
        self.lang_box.setEnabled(kind == "mtl")
        family = "tagged" if tagged else "expressive"
        if family != self._family:  # sensible defaults per model family
            self.top_p.setValue(0.95 if tagged else 1.0)
            self._family = family
        self.swap_sample_text(entry, self.lang_box.currentData() if has_lang else "en")

    def on_model_changed(self):
        self.apply_model_ui()
        self.refresh_model_state()

    def on_language_changed(self):
        entry = self.current_entry()
        if entry["kind"] == "mtl":
            self.swap_sample_text(entry, self.lang_box.currentData())

    def refresh_model_state(self):
        if self.downloading:
            return
        entry = self.current_entry()
        self.model_box.setEnabled(True)
        try:
            ready = model_ready(entry)
        except Exception:  # noqa: BLE001
            ready = False
        self.model_ready = ready
        self.dl_btn.setVisible(not ready)
        self.dl_btn.setEnabled(True)
        self.dl_bar.hide()
        if ready:
            self.model_status.setText("Downloaded and ready.")
        else:
            self.model_status.setText("Not downloaded yet. Download it once (about 3 GB) before generating.")
        self.gen.setEnabled(ready)
        self.gen.setText("Generate speech" if ready else "Download the model first")

    def remove_temp_output(self):
        """Delete the preview file of the previous generation (saved copies are never touched)."""
        f = getattr(self, "out_file", None)
        if f and os.path.dirname(f) == tempfile.gettempdir() and os.path.basename(f).startswith("chatterbox_"):
            try:
                os.remove(f)
            except OSError:
                pass

    def clear_temp_files(self):
        """Delete every Chatterbox preview file in the temp folder (saved WAVs and voices are untouched)."""
        self.player.stop()
        self.player.setSource(QUrl())
        tmp = tempfile.gettempdir()
        count = size = 0
        for name in os.listdir(tmp):
            if name.startswith("chatterbox_") and name.lower().endswith(".wav"):
                path = os.path.join(tmp, name)
                try:
                    n = os.path.getsize(path)
                    os.remove(path)
                    count += 1
                    size += n
                except OSError:
                    pass
        # the preview file is gone, but the audio is still in memory, so Save still works
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.folder_btn.setEnabled(hasattr(self, "out_file_saved"))
        self.status.setText(f"Cleared {count} temp file(s), freed {size / 1e6:.1f} MB.")

    def closeEvent(self, e):
        self.player.stop()
        self.player.setSource(QUrl())
        self.remove_temp_output()
        self.jobs.put(None)
        self.engine.join(15)
        super().closeEvent(e)

    def start_download(self):
        entry = self.current_entry()
        self.downloading = True
        self.model_box.setEnabled(False)
        self.dl_btn.setEnabled(False)
        self.gen.setEnabled(False)
        self.dl_bar.setValue(0)
        self.dl_bar.show()
        self.model_status.setText("Connecting to Hugging Face...")
        self.dl_thread = QThread()
        self.dl_worker = DownloadWorker(entry)
        self.dl_worker.moveToThread(self.dl_thread)
        self.dl_thread.started.connect(self.dl_worker.run)
        self.dl_worker.progress.connect(self.on_dl_progress)
        self.dl_worker.finished.connect(self.on_dl_done)
        self.dl_worker.failed.connect(self.on_dl_failed)
        self.dl_worker.finished.connect(self.dl_thread.quit)
        self.dl_worker.failed.connect(self.dl_thread.quit)
        self._jobs.add((self.dl_thread, self.dl_worker))
        self.dl_thread.finished.connect(lambda t=self.dl_thread, w=self.dl_worker: self._jobs.discard((t, w)))
        self.dl_thread.start()

    def on_dl_progress(self, done, total, speed):
        self.dl_bar.setValue(int(min(done / total, 1.0) * 1000))
        eta = f" - about {int((total - done) / speed)}s left" if speed > 0 else ""
        self.model_status.setText(
            f"Downloading: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB at {speed / 1e6:.1f} MB/s{eta}")

    def on_dl_done(self):
        self.downloading = False
        self.refresh_model_state()
        self.status.setText("Model downloaded. You can generate now.")

    def on_dl_failed(self, msg):
        self.downloading = False
        self.refresh_model_state()
        self.model_status.setText("Download failed - check your connection and click Download again (it resumes).")
        QMessageBox.critical(self, "Download failed", msg)

    def set_busy(self, busy):
        self.gen.setEnabled(not busy and self.model_ready)
        self.model_box.setEnabled(not busy)
        self.progress.setRange(0, 0 if busy else 1)

    def generate(self):
        text = self.text.toPlainText().strip()
        if not self.ref_path:
            QMessageBox.information(self, "Reference needed", "Please choose a reference audio clip first.")
            return
        if not text:
            QMessageBox.information(self, "Text needed", "Please enter some text.")
            return
        if len(text) > MAX_CHARS:
            QMessageBox.information(self, "Too long", f"Please keep the text under {MAX_CHARS} characters.")
            return
        entry = self.current_entry()
        params = dict(seed=self.seed.value(), temperature=self.temp.value(), top_p=self.top_p.value(),
                      top_k=self.top_k.value(), repetition_penalty=self.rep.value(),
                      norm_loudness=self.norm.isChecked(), model=entry["id"],
                      exaggeration=self.exag.value(), cfg_weight=self.cfg.value(), min_p=self.min_p.value(),
                      lang=entry.get("lang") if entry["kind"] == "pack" else self.lang_box.currentData())
        self.set_busy(True)
        self.player.stop()
        self.jobs.put((self.ref_path, text, params))

    def on_done(self, audio, sr):
        self.out_audio, self.out_sr = audio, sr
        self.player.stop()
        self.player.setSource(QUrl())  # release the previous file so Windows lets us delete it
        self.remove_temp_output()
        self.out_file = os.path.join(tempfile.gettempdir(), f"chatterbox_{int(time.time() * 1000)}.wav")
        sf.write(self.out_file, audio, sr)
        self.set_busy(False)
        self.status.setText(f"Done - {len(audio) / sr:.1f}s of audio generated.")
        for b in (self.play_btn, self.stop_btn, self.save_btn, self.folder_btn):
            b.setEnabled(True)
        self.play()

    def on_fail(self, msg):
        self.set_busy(False)
        self.status.setText("Failed.")
        QMessageBox.critical(self, "Generation failed", msg)

    def play(self):
        self.player.setSource(QUrl.fromLocalFile(self.out_file))
        self.player.play()

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save audio", "output.wav", "WAV (*.wav)")
        if path:
            sf.write(path, self.out_audio, self.out_sr)
            self.out_file_saved = path
            self.status.setText(f"Saved to {path}")

    def open_folder(self):
        target = getattr(self, "out_file_saved", self.out_file)
        folder = os.path.dirname(target)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])


def install_excepthook():
    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")

    def hook(et, ev, tb):
        text = "".join(traceback.format_exception(et, ev, tb))
        with open(log, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        traceback.print_exception(et, ev, tb)
        try:
            QMessageBox.critical(None, "Unexpected error", f"{ev}\n\nDetails saved to {log}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main():
    install_excepthook()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    code = app.exec()
    sys.stdout.flush()
    if sys.platform == "win32":
        # Skip interpreter and DLL teardown: PyTorch/CUDA access-violates while unloading.
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k32.TerminateProcess(k32.GetCurrentProcess(), code)
    sys.exit(code)

if __name__ == "__main__":
    main()
