# Voice Box

Linux voice-to-text daemon for Wayland — record, transcribe, refine, and inject text hands-free.

## How It Works

Voice Box runs as a background daemon and follows a simple pipeline:

1. **Record** — captures audio from your microphone via PipeWire/sounddevice
2. **Transcribe** — faster-whisper (Whisper) converts speech to text on your GPU
3. **Refine** (optional) — Ollama cleans up filler words, fixes punctuation and grammar
4. **Inject** — pastes the result into your focused window via clipboard (`wl-copy`/`wl-paste`) or typing (`wtype`)

A GTK4 overlay (via gtk4-layer-shell) shows a recording waveform, processing spinner, and done/error status.

## Requirements

- Arch Linux / CachyOS (or similar)
- Wayland compositor (niri, sway, Hyprland)
- NVIDIA GPU with CUDA (for Whisper)
- PipeWire (for audio capture)
- Ollama (optional, for text refinement)

## Installation

### 1. Clone and install dependencies

```sh
git clone https://github.com/WaffleWaldo/Voice-Box.git
cd Voice-Box
./contrib/install-deps.sh
```

This installs all system packages via pacman and the AUR dependency (`faster-whisper`)
via paru or yay. Or install them manually:

```sh
sudo pacman -S python gtk4 gtk4-layer-shell python-gobject \
               python-numpy python-httpx wl-clipboard wtype pipewire
yay -S python-faster-whisper
```

### 2. Install Voice Box

```sh
make install
```

This creates a venv with `--system-site-packages` (needed for PyGObject/GTK4 bindings),
installs pip-only dependencies (`sounddevice`), and symlinks the `voicebox`
binary into `~/.local/bin/`.

### 3. Build the refiner model

If you have a trained LoRA adapter (see [Fine-tuning](#fine-tuning-the-refiner) below):

```sh
make model
```

This creates a custom Ollama model (`voicebox-refiner`) that loads the fine-tuned
LoRA adapter on top of `llama3.1:8b`, with a system prompt and few-shot examples.

### 4. Configure

```sh
mkdir -p ~/.config/voicebox
cp config.example.toml ~/.config/voicebox/config.toml
# Edit config.toml — set audio device, STT model, Ollama URL, etc.
```

### 5. Start

```sh
# One-time manual start:
voicebox daemon &

# Or enable the systemd service:
systemctl --user enable --now voicebox

# View logs:
journalctl --user -u voicebox -f
```

## Usage

```sh
voicebox toggle    # start/stop recording (bind this to a key)
voicebox status    # check daemon state
voicebox stop      # stop the daemon
```

## Keybind Examples

### niri

In `~/.config/niri/config.kdl`:

```kdl
binds {
    Mod+V { spawn "voicebox" "toggle"; }
}
```

### sway

In `~/.config/sway/config`:

```
bindsym $mod+v exec voicebox toggle
```

### Hyprland

In `~/.config/hypr/hyprland.conf`:

```
bind = $mainMod, V, exec, voicebox toggle
```

## Configuration

The configuration file lives at `~/.config/voicebox/config.toml`. See `config.example.toml` for all options.

| Section | Key options |
|---|---|
| `[audio]` | `device`, `sample_rate`, `mode` (`"toggle"` or `"push_to_talk"`) |
| `[stt]` | `model`, `device` (`"cuda"`), `compute_type`, `language` |
| `[refiner]` | `enabled`, `ollama_url`, `model`, `temperature` |
| `[injector]` | `type_delay_ms`, `clipboard_threshold` |
| `[overlay]` | `enabled` — set to `false` to disable the GTK4 overlay UI |
| `[dictionary]` | `path` — custom word list for domain-specific terms |

## Fine-tuning the Refiner

The refiner uses a LoRA-fine-tuned `llama3.1:8b` to clean speech-to-text transcripts.
The base model is trained as a chatbot and tends to follow instruction-like transcripts
instead of cleaning them literally. Fine-tuning on transcript cleanup data fixes this.

### Requirements

- NVIDIA GPU with 16GB VRAM (tested on RTX 4060 Ti)
- [Ollama](https://ollama.com/) with `llama3.1:8b` pulled
- [Unsloth](https://unsloth.ai/) for LoRA training

```sh
pip install unsloth    # pulls torch, transformers, peft, trl, etc.
ollama pull llama3.1:8b
```

### Training

```sh
make train    # ~5 min on RTX 4060 Ti 16GB
```

This runs `benchmarks/refiner/train.py` which:

1. Loads `llama3.1:8b-instruct` in 4-bit quantization (~8GB VRAM)
2. Applies LoRA adapters (rank=16, all linear layers)
3. Trains for 3 epochs on 350 transcript cleanup examples (`train.jsonl`)
4. Saves the adapter to `benchmarks/refiner/output/adapter/`
5. Registers the model with Ollama as `voicebox-refiner`

### Benchmarking

```sh
make bench-baseline    # save current results as baseline
make bench             # compare against saved baseline
```

The benchmark suite (`benchmarks/refiner/run.py`) tests 15 cases across categories
like filler removal, instruction-like inputs, multi-sentence formatting, and edge cases.

### Training data

`benchmarks/refiner/train.jsonl` contains 350 (input, output) pairs across 8 categories:
filler removal, false starts, instruction-like content, multi-sentence, lists, technical
jargon, short phrases, and edge cases. The 15 benchmark cases in `cases.jsonl` are kept
separate as the test set — no data leakage between training and evaluation.

## License

[MIT](LICENSE)
