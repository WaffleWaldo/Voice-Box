# Voice Box

Linux voice-to-text daemon for Wayland — record, transcribe, refine, and inject text hands-free.

## How It Works

Voice Box runs as a background daemon and follows a simple pipeline:

1. **Record** — captures audio from your microphone via PipeWire/sounddevice
2. **Detect speech** — Silero VAD detects when you start and stop talking
3. **Transcribe** — faster-whisper (Whisper) converts speech to text on your GPU
4. **Refine** (optional) — Ollama cleans up filler words, fixes punctuation and grammar
5. **Inject** — pastes the result into your focused window via clipboard (`wl-copy`/`wl-paste`) or typing (`wtype`)

A GTK4 overlay (via gtk4-layer-shell) shows a recording waveform, processing spinner, and done/error status.

## Requirements

- Arch Linux / CachyOS (or similar)
- Wayland compositor (niri, sway, Hyprland)
- NVIDIA GPU with CUDA (for Whisper)
- PipeWire (for audio capture)
- Ollama (optional, for text refinement)

## Installation

### 1. System packages

```sh
sudo pacman -S python gtk4 gtk4-layer-shell python-gobject \
               python-numpy python-httpx wl-clipboard wtype pipewire
```

Install `faster-whisper` from the AUR:

```sh
yay -S python-faster-whisper
```

### 2. Clone and install

```sh
git clone https://github.com/WaffleWaldo/Voice-Box.git
cd Voice-Box
make install
```

This creates a venv with `--system-site-packages` (needed for PyGObject/GTK4 bindings),
installs pip-only dependencies (`sounddevice`, `silero-vad`), and symlinks the `voicebox`
binary into `~/.local/bin/`.

### 3. Configure

```sh
mkdir -p ~/.config/voicebox
cp config.example.toml ~/.config/voicebox/config.toml
# Edit config.toml — set audio device, STT model, Ollama URL, etc.
```

### 4. Start

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
| `[vad]` | `silence_threshold_sec`, `min_speech_sec` |
| `[stt]` | `model`, `device` (`"cuda"`), `compute_type`, `language` |
| `[refiner]` | `enabled`, `ollama_url`, `model`, `temperature`, `system_prompt` |
| `[injector]` | `type_delay_ms`, `clipboard_threshold` |
| `[overlay]` | `enabled` — set to `false` to disable the GTK4 overlay UI |
| `[notifications]` | `enabled` — desktop notifications |
| `[dictionary]` | `path` — custom word list for domain-specific terms |

## License

[MIT](LICENSE)
