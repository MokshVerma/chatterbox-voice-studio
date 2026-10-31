# Chatterbox Voice Studio

A desktop GUI (PySide6 / Qt) for [Resemble AI's Chatterbox Turbo](https://github.com/resemble-ai/chatterbox)
voice cloning. Give it one reference clip and some text, and it speaks the text in that voice - including
paralinguistic tags like `[chuckle]`, `[sigh]` and `[laugh]`.

## Features
- Reference voice from a file (Browse), **in-app recording**, or a saved-voices dropdown
- One-click tag buttons: `[clear throat] [sigh] [shush] [cough] [groan] [sniff] [gasp] [chuckle] [laugh]`
- Choose **Turbo** (350M) or **Nano** (110M); models download on demand with a live progress bar
- Seed, temperature, top-p, top-k, repetition penalty, loudness normalisation
- Play, save as WAV, and a button to clear temporary preview files
- Windows, macOS (Apple GPU via MPS) and Linux; NVIDIA GPU via CUDA

## Install
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
```
Install PyTorch for your hardware first (https://pytorch.org/get-started/locally/), e.g. an NVIDIA GPU needs a CUDA
build, otherwise generation runs on the CPU. Then:
```bash
pip install -r requirements.txt
```

## Run
- Windows: double-click `run_app.bat`
- macOS: `chmod +x run_app.command`, then double-click `run_app.command`
- Or: `python chatterbox_app.py`

Click **Download model** on first use (about 3 GB per model), pick or record a clear reference clip longer than
5 seconds, enter text (max 300 characters), and click **Generate speech**.

## Notes
- Recordings are stored in `voices/` next to the app (git-ignored).
- Upstream Chatterbox returns float64 audio after loudness normalisation, which its float32 models reject; the app
  patches that at runtime, so stock Chatterbox works unmodified.
- Generated audio carries Chatterbox's built-in Perth watermark. Only clone voices you have permission to use.
- macOS/Apple GPU support is untested by the author; please open an issue with any errors.

## Credits
Built on [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI (MIT).
