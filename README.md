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

```sh
make model
```

This creates a custom Ollama model (`voicebox-refiner`) with baked-in system prompt
and few-shot examples for reliable transcript cleaning.

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

## License

[MIT](LICENSE)
